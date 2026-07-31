"""Phase 8.5 — the cross-bank blind spot, quantified, and what co-operation buys.

THE RESEARCH QUESTION (PROJECT.md thesis #3): a mule chain hops through several
banks. Each bank sees one hop and no crime, and privacy law blocks naive data
sharing. How much does that cost, in detection terms — and how much of it can a
privacy-preserving protocol buy back? Central banks run this experiment behind
closed doors (BIS Project Aurora); there is no open version, which is the whole
reason this phase exists.

WHY SEPARATE LEDGER FILES, NOT A `WHERE` CLAUSE. A bank's solo view is written to
its own DuckDB containing only its own customers, accounts and transactions. A
filter parameter would have worked and been faster, but every detector in this
project (`detect.rules`, `graph.build`, `graph.motifs`) would then have to
remember to honour it, and one that forgot would silently give a bank sight of
another bank's rows — inventing detection ability that does not exist and
inflating the headline number this phase is built to measure. With separate
files the other bank's rows are simply absent, every existing detector runs
completely unmodified, and the isolation is structural rather than a convention.

WHAT THE BLIND SPOT ACTUALLY IS, and it is narrower and more interesting than
"banks see nothing". An account's OWN history lives entirely at its own bank, so
a bank can still flag an individual mule account locally — `rapid_pass_through`
fires perfectly well on "money arrived, money left within the day". What a bank
structurally cannot do is RECONSTRUCT THE CHAIN: `graph.build` pairs the two legs
of a transfer by the reference they share, and when the counterparty banks
elsewhere the second leg is not in this ledger at all, so no edge forms. So the
loss is not detection of accounts, it is detection of the NETWORK — which is
precisely the thing that turns three unrelated alerts into one laundering case.

THE CO-OPERATION PROTOCOL, and what it does and does not protect. Each bank runs
its own local rules, and for accounts it has ALREADY FLAGGED ITSELF it publishes
one fingerprint per leg: `HMAC(shared_secret, payment_reference)` plus direction,
amount and timestamp. Never a customer name, never an account id, never a
balance, never anything about an account it did not already flag. Two banks whose
fingerprints match on the same hashed reference have found the two ends of one
payment, and the cross-bank edge is reconstructed without either learning who the
other's customer is.

Its limits are measured, not asserted — see `PrivacyNotes` and the report:
  * A link only appears if BOTH banks flagged their own side. Co-operation lift
    is therefore bounded above by local recall, and the report prints that bound
    rather than letting the lift look like free money.
  * A hashed reference is a deterministic pseudonym. A bank that already knows a
    reference can confirm another bank was in that payment — but it already knew
    that, because it was the counterparty. What it still cannot learn is the
    identity behind the other leg.
  * The coordinator learns the SHAPE of the inter-bank graph (who links to whom,
    and volumes) even without identities. That is a real residual disclosure and
    the honest reason this is a prototype rather than a proposal.

    python -m launderlab multibank
"""

from __future__ import annotations

import hashlib
import hmac
import random
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

from launderlab.db.ledger import connect
from launderlab.detect import rules
from launderlab.graph import build as graph_build
from launderlab.graph import motifs
from launderlab.typology import mule_network
from launderlab.world.generate import load

# Four synthetic banks, matching the master plan. Real IFSC-shaped codes so the
# `accounts.ifsc` column keeps meaning what it says it means.
BANK_CODES = ("LLAB", "SBIN", "HDFC", "ICIC")

WINDOW_START = date(2026, 7, 3)

# The reference number both legs of a transfer share, and the field the whole
# cross-bank reconstruction hangs on. Same one `graph/build.py` joins within a
# single bank -- this phase is that join, stretched across a trust boundary.
_REF_FIELD = 3


@dataclass(frozen=True)
class Fingerprint:
    """What one bank is willing to publish about one leg of one flagged payment.

    Deliberately NOT a dataclass containing an account id or a customer name --
    the type itself is the privacy boundary, so a future edit that tries to share
    more has to change this definition and trip its test.
    """
    bank: str
    ref_token: str        # HMAC(secret, reference) -- a pseudonym, never the ref
    direction: str        # 'DR' (we sent) or 'CR' (we received)
    amount: float
    ts: datetime


@dataclass(frozen=True)
class CrossBankEdge:
    """A transfer reconstructed from two banks' fingerprints, pseudonymously."""
    src_bank: str
    dst_bank: str
    ref_token: str
    amount: float
    ts: datetime


@dataclass
class ChainOutcome:
    """One planted cross-bank chain, and who could see it."""
    scheme_id: str
    accounts: list[str]
    banks: list[str]
    spans_banks: int
    pooled_hops_seen: int          # a hypothetical central view
    best_solo_hops_seen: int       # the luckiest individual bank
    accounts_locally_flagged: int  # individual mule accounts any bank did flag
    cooperative_hops_seen: int = 0  # after the privacy-preserving protocol
    # Why a solo bank saw what it saw. `graph.motifs` needs DEFAULT_MIN_HOPS
    # consecutive hops before it reports a chain at all, so a lone intra-bank hop
    # is invisible even though the bank holds both its legs. Counting the
    # OPPORTUNITIES a solo bank had turns "0%" from an assertion into a
    # measurement with a stated mechanism.
    same_bank_hops: int = 0            # hops whose two ends share a bank
    solo_reconstructable_runs: int = 0  # runs long enough for motifs to report

    @property
    def cooperative_total_hops(self) -> int:
        """Every hop the co-operating system knows the link for.

        `cooperative_hops_seen` counts only hops recovered ACROSS a boundary,
        because that is all the protocol has to do. An intra-bank hop needs no
        protocol at all -- the bank already holds both legs. Scoring the
        co-operative view on cross-bank recoveries alone therefore penalised the
        naive arm for hops it could already see, and made a chain deliberately
        spread across banks look BETTER covered than a careless one, which is
        backwards. No double counting: a recovered hop is cross-bank by
        construction, so the two sets are disjoint.
        """
        return self.cooperative_hops_seen + self.same_bank_hops


@dataclass
class PrivacyNotes:
    """Measured facts about what the protocol did and did not disclose."""
    fingerprints_published: int = 0
    banks_participating: int = 0
    fields_shared: tuple[str, ...] = ()
    never_shared: tuple[str, ...] = ()
    links_needing_both_sides_flagged: int = 0
    links_lost_to_one_sided_flagging: int = 0
    residual_disclosures: tuple[str, ...] = ()


def assign_banks(conn: duckdb.DuckDBPyConnection, n_banks: int = 4,
                 seed: int = 5) -> dict[str, str]:
    """Spread existing accounts across `n_banks`, writing the code into `ifsc`.

    Applied to an ALREADY GENERATED world rather than changing `world/generate.py`:
    partitioning is a property of who banks where, not of how the money moved, and
    regenerating would have invalidated every number the earlier phases published
    against the single-bank generator.
    """
    codes = list(BANK_CODES[:n_banks])
    accounts = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts ORDER BY account_id").fetchall()]
    rng = random.Random(seed)
    mapping = {account: rng.choice(codes) for account in accounts}
    conn.executemany("UPDATE accounts SET ifsc = ? WHERE account_id = ?",
                     [(f"{bank}0000001", account) for account, bank in mapping.items()])
    return mapping


def bank_of(mapping: dict[str, str], account_id: str) -> str:
    return mapping[account_id]


def split_into_banks(pooled_path: Path, mapping: dict[str, str],
                     out_dir: Path) -> dict[str, Path]:
    """Write one real DuckDB per bank, containing only that bank's own rows.

    Takes the pooled ledger's PATH, not an open connection: DuckDB refuses to
    ATTACH a file another connection in the same process already holds open
    ("Unique file handle conflict"), so the caller has to close the pooled
    connection first. Making that a path parameter rather than a documented
    precondition means the constraint cannot be forgotten silently.

    The customers table is filtered too: a bank does not hold KYC records for
    another bank's customers, and leaving them in would let a solo screening run
    see people it has no relationship with.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for bank in sorted(set(mapping.values())):
        owned = [account for account, code in mapping.items() if code == bank]
        path = out_dir / f"{bank}.duckdb"
        if path.exists():
            path.unlink()
        bank_conn = connect(path)
        # A temp table of this bank's account ids, then three INSERT..SELECTs --
        # DuckDB can read across attached databases, so no Python round-trip.
        bank_conn.execute("CREATE TEMP TABLE owned (account_id VARCHAR)")
        bank_conn.executemany("INSERT INTO owned VALUES (?)", [(a,) for a in owned])
        bank_conn.execute(f"ATTACH '{pooled_path}' AS src (READ_ONLY)")
        bank_conn.execute(
            "INSERT INTO customers SELECT DISTINCT c.* FROM src.customers c"
            " JOIN src.accounts a USING (customer_id) JOIN owned o USING (account_id)")
        bank_conn.execute(
            "INSERT INTO accounts SELECT a.* FROM src.accounts a JOIN owned o"
            " USING (account_id)")
        bank_conn.execute(
            "INSERT INTO transactions SELECT t.* FROM src.transactions t JOIN owned o"
            " USING (account_id)")
        bank_conn.execute("DETACH src")
        bank_conn.close()
        paths[bank] = path

    return paths


def _chain_hops_seen(chains: list, accounts: list[str]) -> int:
    """How many consecutive hops of `accounts` any reconstructed chain covers."""
    best = 0
    wanted = list(accounts)
    for chain in chains:
        found = [a for a in chain.accounts if a in wanted]
        # count consecutive pairs of the planted path this chain actually links
        hops = 0
        for a, b in zip(wanted, wanted[1:]):
            if a in chain.accounts and b in chain.accounts:
                idx_a = list(chain.accounts).index(a)
                idx_b = list(chain.accounts).index(b)
                if idx_b == idx_a + 1:
                    hops += 1
        best = max(best, hops)
        if not found:
            continue
    return best


PLACEMENTS = ("deliberate", "naive")


def plant_chains(conn: duckdb.DuckDBPyConnection, mapping: dict[str, str],
                 n_schemes: int, rng: random.Random, hops: int = 4,
                 placement: str = "deliberate",
                 prefix: str = "XB") -> list[tuple[str, list[str]]]:
    """Plant mule chains, either deliberately spread across banks or placed naively.

    TWO ARMS, because one of them would otherwise be a tautology dressed as a
    measurement. `placement="deliberate"` walks the banks in turn, so no two
    consecutive accounts share a bank -- and a solo bank then reconstructs zero
    hops BY CONSTRUCTION, which is not a finding, it is arithmetic. That arm is
    still worth running because deliberately spreading a chain across
    institutions is a real laundering tactic, not a hypothetical one.

    `placement="naive"` ignores banks entirely, which is what an unsophisticated
    launderer does. Consecutive hops then land at the same bank purely by luck,
    and what a solo bank sees becomes something actually measured. The gap
    between the two arms is the honest headline: it is what deliberately banking
    across institutions BUYS the launderer, rather than what the experiment
    assumed.
    """
    if placement not in PLACEMENTS:
        raise ValueError(f"placement must be one of {PLACEMENTS}, got {placement!r}")

    by_bank: dict[str, list[str]] = {}
    for account, bank in mapping.items():
        by_bank.setdefault(bank, []).append(account)
    for accounts in by_bank.values():
        accounts.sort()

    retail = sorted({r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student')").fetchall()})
    retail_set = set(retail)
    banks = sorted(by_bank)
    used: set[str] = set()
    planted = []

    for i in range(n_schemes):
        path = []
        for hop in range(hops):
            if placement == "deliberate":
                bank = banks[hop % len(banks)]
                candidates = [a for a in by_bank[bank]
                              if a in retail_set and a not in used]
            else:
                candidates = [a for a in retail if a not in used]
            if not candidates:
                break
            account = rng.choice(candidates)
            used.add(account)
            path.append(account)
        if len(path) < 2:
            continue
        scheme_id = f"{prefix}-{i}"
        mule_network.inject(conn, scheme_id, path, WINDOW_START, rng)
        planted.append((scheme_id, path))

    return planted


def publish_fingerprints(bank_path: Path, bank: str, secret: bytes) -> list[Fingerprint]:
    """One bank's shareable signals: hashed references for accounts IT flagged.

    The local flag is `rapid_pass_through` -- the rule that already detects "money
    arrived and left again quickly", which works fine on a single bank's view
    because an account's own history is entirely at its own bank. Nothing is
    published about an account the bank did not independently flag, which is what
    keeps this a disclosure about suspicions rather than a bulk data transfer.
    """
    conn = connect(bank_path)
    try:
        flagged = {alert.account_id for alert in rules.rapid_pass_through(conn)}
        if not flagged:
            return []
        placeholders = ",".join("?" * len(flagged))
        rows = conn.execute(
            "SELECT direction, amount::DOUBLE, ts,"
            f" split_part(narration, '/', {_REF_FIELD}) AS ref"
            f" FROM transactions WHERE account_id IN ({placeholders})"
            " AND narration LIKE '%/%/%/%'", list(flagged)).fetchall()
    finally:
        conn.close()

    return [
        Fingerprint(bank=bank, ref_token=_token(secret, ref), direction=direction,
                    amount=amount, ts=ts)
        for direction, amount, ts, ref in rows if ref
    ]


def _token(secret: bytes, reference: str) -> str:
    """HMAC rather than a bare hash: a plain SHA of a short numeric reference is
    trivially brute-forced back to the reference, which would hand every
    participant a lookup table for payments they were never party to. The shared
    secret makes the token meaningless to anyone outside the scheme."""
    return hmac.new(secret, reference.encode(), hashlib.sha256).hexdigest()


def reconstruct_cross_bank_edges(fingerprints: list[Fingerprint]) -> list[CrossBankEdge]:
    """Match DR fingerprints to CR fingerprints from a DIFFERENT bank."""
    debits = [f for f in fingerprints if f.direction == "DR"]
    credits: dict[tuple, list[Fingerprint]] = {}
    for f in fingerprints:
        if f.direction == "CR":
            credits.setdefault((f.ref_token, f.amount, f.ts), []).append(f)

    edges = []
    for debit in debits:
        for credit in credits.get((debit.ref_token, debit.amount, debit.ts), []):
            if credit.bank != debit.bank:
                edges.append(CrossBankEdge(
                    src_bank=debit.bank, dst_bank=credit.bank,
                    ref_token=debit.ref_token, amount=debit.amount, ts=debit.ts))
    return edges


def measure(conn: duckdb.DuckDBPyConnection, mapping: dict[str, str],
            planted: list[tuple[str, list[str]]], bank_paths: dict[str, Path],
            secret: bytes) -> tuple[list[ChainOutcome], PrivacyNotes]:
    """Solo view vs pooled view vs co-operation, for every planted chain."""
    pooled_chains = motifs.find_chains(graph_build.build_graph(conn))

    solo_chains: dict[str, list] = {}
    locally_flagged: set[str] = set()
    for bank, path in bank_paths.items():
        bank_conn = connect(path)
        try:
            solo_chains[bank] = motifs.find_chains(graph_build.build_graph(bank_conn))
            locally_flagged |= {a.account_id for a in rules.rapid_pass_through(bank_conn)}
        finally:
            bank_conn.close()

    # co-operation: every bank publishes, the coordinator matches
    fingerprints: list[Fingerprint] = []
    for bank, path in bank_paths.items():
        fingerprints.extend(publish_fingerprints(path, bank, secret))
    edges = reconstruct_cross_bank_edges(fingerprints)
    recovered = {(e.ref_token, e.amount, e.ts) for e in edges}

    # which planted hops the recovered edges cover: re-derive each hop's own
    # reference from the pooled ledger, hash it, and ask whether co-operation
    # found it. The coordinator never does this -- it is the SCORER's view.
    outcomes = []
    for scheme_id, accounts in planted:
        banks = [mapping[a] for a in accounts]
        hop_refs = _hop_references(conn, accounts)
        cooperative = sum(
            1 for ref, amount, ts in hop_refs
            if (_token(secret, ref), amount, ts) in recovered)
        outcomes.append(ChainOutcome(
            scheme_id=scheme_id, accounts=accounts, banks=banks,
            spans_banks=len(set(banks)),
            pooled_hops_seen=_chain_hops_seen(pooled_chains, accounts),
            best_solo_hops_seen=max(
                (_chain_hops_seen(chains, accounts) for chains in solo_chains.values()),
                default=0),
            accounts_locally_flagged=sum(1 for a in accounts if a in locally_flagged),
            cooperative_hops_seen=cooperative,
            same_bank_hops=sum(1 for a, b in zip(banks, banks[1:]) if a == b),
            solo_reconstructable_runs=_solo_reconstructable_runs(banks),
        ))

    total_hops = sum(len(a) - 1 for _s, a in planted)
    privacy = PrivacyNotes(
        fingerprints_published=len(fingerprints),
        banks_participating=len({f.bank for f in fingerprints}),
        fields_shared=("HMAC(reference)", "direction", "amount", "timestamp"),
        never_shared=("customer name", "account id", "balance", "KYC data",
                      "anything about an unflagged account"),
        links_needing_both_sides_flagged=total_hops,
        links_lost_to_one_sided_flagging=total_hops - sum(
            o.cooperative_hops_seen for o in outcomes),
        residual_disclosures=(
            "the coordinator learns the shape of the inter-bank graph (which banks "
            "transact with which, and at what volume) even without identities",
            "a bank that already knows a reference can confirm another bank was in "
            "that payment -- though it was the counterparty, so it already knew",
        ),
    )
    return outcomes, privacy


def _solo_reconstructable_runs(banks: list[str]) -> int:
    """How many stretches of this chain a single bank could even in principle report.

    `motifs.find_chains` will not report anything shorter than
    `DEFAULT_MIN_HOPS` hops, so one intra-bank hop is invisible to its own bank
    even though that bank holds both of its legs. A run of k consecutive
    same-bank accounts yields k-1 hops, and only counts if that clears the
    minimum. This is the mechanism behind the solo number, computed rather than
    asserted -- if it is 0, a solo bank had no opportunity at all, and the 0%
    that follows is explained instead of merely observed.
    """
    needed = motifs.DEFAULT_MIN_HOPS
    runs = 0
    run_len = 1  # a run of k same-bank accounts in a row yields k-1 hops
    for previous, current in zip(banks, banks[1:]):
        if current == previous:
            run_len += 1
            continue
        if run_len - 1 >= needed:
            runs += 1
        run_len = 1
    if run_len - 1 >= needed:
        runs += 1
    return runs


def _hop_references(conn: duckdb.DuckDBPyConnection,
                    accounts: list[str]) -> list[tuple[str, float, datetime]]:
    """(reference, amount, ts) for each consecutive hop of a planted chain."""
    hops = []
    for src, dst in zip(accounts, accounts[1:]):
        row = conn.execute(
            f"""
            WITH legs AS (
                SELECT account_id, direction, amount::DOUBLE AS amount, ts,
                       split_part(narration, '/', {_REF_FIELD}) AS ref
                FROM transactions WHERE narration LIKE '%/%/%/%'
            )
            SELECT dr.ref, dr.amount, dr.ts FROM legs dr JOIN legs cr
              ON dr.ref = cr.ref AND dr.amount = cr.amount AND dr.ts = cr.ts
            WHERE dr.direction = 'DR' AND cr.direction = 'CR'
              AND dr.account_id = ? AND cr.account_id = ?
            LIMIT 1
            """, [src, dst]).fetchone()
        if row:
            hops.append((row[0], row[1], row[2]))
    return hops


def run_arm(placement: str, customers: int = 600, days: int = 21, seed: int = 19,
            n_banks: int = 4, n_schemes: int = 12, hops: int = 4,
            work_dir: Path | None = None
            ) -> tuple[list[ChainOutcome], PrivacyNotes, dict[str, str]]:
    """One arm end to end: generate, split into banks, plant, measure.

    A fresh world per arm rather than two chain sets in one ledger -- sharing a
    world would let one arm's schemes sit in the other's detection input, and
    `rapid_pass_through` firing on a deliberate chain's account would be counted
    as the naive arm's local recall.
    """
    own_dir = work_dir is None
    work_dir = Path(work_dir) if work_dir else Path(
        tempfile.mkdtemp(prefix=f"multibank_{placement}_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        path = work_dir / "pooled.duckdb"
        if path.exists():
            path.unlink()
        conn = connect(path)
        load(conn, n=customers, days=days, seed=seed)
        mapping = assign_banks(conn, n_banks=n_banks, seed=seed)
        rng = random.Random(seed)
        planted = plant_chains(conn, mapping, n_schemes, rng, hops=hops,
                               placement=placement)
        conn.close()  # DuckDB will not ATTACH a file this process still holds open

        bank_paths = split_into_banks(path, mapping, work_dir / "banks")

        secret = b"launderlab-phase-8.5-demo-secret"
        conn = connect(path)
        try:
            outcomes, privacy = measure(conn, mapping, planted, bank_paths, secret)
        finally:
            conn.close()
        return outcomes, privacy, mapping
    finally:
        if own_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


def run_experiment(customers: int = 600, days: int = 21, seed: int = 19,
                   n_banks: int = 4, n_schemes: int = 12, hops: int = 4
                   ) -> dict[str, tuple[list[ChainOutcome], PrivacyNotes]]:
    """Both arms, keyed by placement. See `plant_chains` for why there are two."""
    results = {}
    for placement in PLACEMENTS:
        outcomes, privacy, _mapping = run_arm(
            placement, customers=customers, days=days, seed=seed,
            n_banks=n_banks, n_schemes=n_schemes, hops=hops)
        results[placement] = (outcomes, privacy)
    return results


@dataclass(frozen=True)
class ArmTotals:
    chains: int
    hops: int
    pooled: int
    solo: int
    coop: int              # every hop the co-operating system knows the link for
    coop_cross_bank: int   # of those, the ones the protocol actually recovered
    flagged: int
    accounts: int
    same_bank_hops: int
    solo_runs: int


def totals(outcomes: list[ChainOutcome]) -> ArmTotals:
    return ArmTotals(
        chains=len(outcomes),
        hops=sum(len(o.accounts) - 1 for o in outcomes),
        pooled=sum(o.pooled_hops_seen for o in outcomes),
        solo=sum(o.best_solo_hops_seen for o in outcomes),
        coop=sum(o.cooperative_total_hops for o in outcomes),
        coop_cross_bank=sum(o.cooperative_hops_seen for o in outcomes),
        flagged=sum(o.accounts_locally_flagged for o in outcomes),
        accounts=sum(len(o.accounts) for o in outcomes),
        same_bank_hops=sum(o.same_bank_hops for o in outcomes),
        solo_runs=sum(o.solo_reconstructable_runs for o in outcomes),
    )


def report(arms: dict[str, tuple[list[ChainOutcome], PrivacyNotes]]) -> str:
    lines = [
        "THE CROSS-BANK BLIND SPOT - quantified, and what co-operation buys back",
        "=" * 78, "",
        "Two arms, because one of them alone would be arithmetic rather than a finding:",
        "  naive       - chains placed without regard to which bank an account is at,",
        "                which is what an unsophisticated launderer does. What a solo",
        "                bank sees here is MEASURED.",
        "  deliberate  - consecutive hops always at different banks, which is a real",
        "                laundering tactic. A solo bank reconstructs nothing here BY",
        "                CONSTRUCTION, so that 0% is not evidence on its own.",
        "The gap between them is what spreading a chain across banks actually buys the",
        "launderer -- which turns out to be nearly nothing. See below.",
        "",
    ]
    if not any(outcomes for outcomes, _p in arms.values()):
        return "\n".join(lines + ["No chains were planted."])

    lines += [
        f"{'arm':<14}{'chains':>7}{'hops':>6}{'pooled':>9}{'solo':>9}"
        f"{'co-op':>9}{'accts flagged locally':>24}",
        "-" * 78,
    ]
    for placement in PLACEMENTS:
        if placement not in arms:
            continue
        t = totals(arms[placement][0])
        lines.append(
            f"{placement:<14}{t.chains:>7}{t.hops:>6}"
            f"{_pct(t.pooled, t.hops):>9}{_pct(t.solo, t.hops):>9}"
            f"{_pct(t.coop, t.hops):>9}"
            f"{f'{t.flagged}/{t.accounts} ({_pct(t.flagged, t.accounts)})':>24}")

    naive = totals(arms["naive"][0]) if "naive" in arms else None
    deliberate = totals(arms["deliberate"][0]) if "deliberate" in arms else None

    lines += ["", "THE BLIND SPOT IS THE NETWORK, NOT THE ACCOUNT", "-" * 78]
    if naive:
        lines += [
            f"  Naive placement: banks flag {_pct(naive.flagged, naive.accounts)} of the "
            f"individual mule accounts",
            f"  on their own books, and still reconstruct only "
            f"{_pct(naive.solo, naive.hops)} of the chain hops.",
        ]
    lines += [
        "  Every bank can see 'money arrived and left again' on its own customer -- an",
        "  account's whole history is at its own bank. What no bank can do alone is join",
        "  those hops into a chain: the second leg of a cross-bank transfer is not in its",
        "  ledger, so there is no edge to follow. The loss is the NETWORK, not the account.",
    ]

    if naive and deliberate:
        lines += [
            "",
            "SOPHISTICATION BUYS THE LAUNDERER ALMOST NOTHING HERE",
            "-" * 78,
            f"  solo reconstruction {_pct(naive.solo, naive.hops)} (naive) -> "
            f"{_pct(deliberate.solo, deliberate.hops)} (deliberate)",
            f"  Naive chains left {naive.solo_runs} stretch(es) long enough for a solo bank",
            f"  to report at all; deliberate ones left {deliberate.solo_runs}.",
            "",
            "  This is the opposite of what the two-arm design was set up to show, and it",
            "  is the more interesting result. Reconstructing a chain needs "
            f"{motifs.DEFAULT_MIN_HOPS} CONSECUTIVE",
            "  hops inside one bank, so with n banks the odds of even one reportable",
            f"  stretch fall off as 1/n^{motifs.DEFAULT_MIN_HOPS} per position. The blind spot",
            "  is already near-total by accident; a launderer does not have to be clever",
            "  about spreading a chain to get it, and the case for co-operation does not",
            "  rest on facing a sophisticated adversary.",
        ]

    lines += ["", "CO-OPERATION LIFT", "-" * 78]
    for placement in PLACEMENTS:
        if placement not in arms:
            continue
        t = totals(arms[placement][0])
        lines.append(
            f"  {placement:<12} {_pct(t.solo, t.hops)} -> {_pct(t.coop, t.hops)} of hops "
            f"({t.coop - t.solo:+d}); of which {t.coop_cross_bank} recovered across a "
            f"boundary, {t.same_bank_hops} already intra-bank")
    lines += [
        "  The co-operative view counts every hop whose link is known: the ones the",
        "  protocol recovered across a boundary, plus the intra-bank ones a bank already",
        "  held both legs of. Scoring cross-bank recoveries alone made a chain",
        "  deliberately spread across banks look better covered than a careless one.",
        "",
        "  Bounded above by local recall: a cross-bank link needs BOTH banks to have",
        "  flagged their own side, so co-operation multiplies existing detection rather",
        "  than replacing it. Missed hops by arm:",
    ]
    for placement in PLACEMENTS:
        if placement not in arms:
            continue
        t = totals(arms[placement][0])
        lines.append(f"    {placement:<12} {t.hops - t.coop}/{t.hops} hops still unknown")

    privacy = next(p for _o, p in arms.values())
    lines += [
        "", "WHAT WAS SHARED, AND WHAT WAS NOT", "-" * 78,
        "  Shared:       " + ", ".join(privacy.fields_shared),
        "  Never shared: " + ", ".join(privacy.never_shared),
        "",
        "  Residual disclosure, stated rather than glossed:",
    ]
    for note in privacy.residual_disclosures:
        lines.append(f"    - {note}")
    return "\n".join(lines)


def _pct(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "n/a"


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    from launderlab.viz import render_multibank

    schemes = 12
    for arg in argv:
        if arg.startswith("--schemes="):
            schemes = int(arg.split("=", 1)[1])
    arms = run_experiment(n_schemes=schemes)
    print(report(arms))
    if "--no-chart" not in argv:
        print(f"\nChart written to {render_multibank(arms)}")
