import inspect
import re

import pytest

from launderlab import multibank as mb
from launderlab.db.ledger import connect


def test_multibank_never_reads_ground_truth():
    """The blind-spot number is a detection measurement, so the experiment's own
    plumbing must earn it the same way every detector does. Only the SCORER side
    (`measure`) knows which chains were planted, and it knows because it planted
    them -- never from `scheme_labels`."""
    source = inspect.getsource(mb)
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert not re.search(rf"\b(FROM|JOIN)\s+{table}\b", source, re.IGNORECASE)


# --------------------------------------------------------- the privacy boundary

def test_a_fingerprint_cannot_carry_identity():
    """The type IS the privacy boundary. If someone later adds an account id or a
    customer name to what banks publish, this fails -- which is the point of
    asserting on the dataclass's fields rather than on a docstring promise."""
    fields = set(mb.Fingerprint.__dataclass_fields__)
    assert fields == {"bank", "ref_token", "direction", "amount", "ts"}
    for forbidden in ("account_id", "customer_id", "customer_name", "name",
                      "balance", "narration"):
        assert forbidden not in fields


def test_the_shared_token_is_keyed_not_a_bare_hash():
    """A plain SHA of a short numeric reference is trivially brute-forced back to
    the reference, which would hand every participant a lookup table for payments
    they were never party to. Two different secrets must produce different tokens
    for the same reference, and the token must never contain the reference."""
    reference = "519377"
    a = mb._token(b"secret-one", reference)
    b = mb._token(b"secret-two", reference)
    assert a != b
    assert reference not in a
    assert a == mb._token(b"secret-one", reference)  # deterministic within a scheme


def test_reconstruction_only_links_two_different_banks():
    """Matching a bank's own DR to its own CR would invent a 'cross-bank' edge
    out of a purely internal transfer and inflate the co-operation lift."""
    from datetime import datetime
    ts = datetime(2026, 7, 4, 10, 0)
    same_bank = [
        mb.Fingerprint("LLAB", "tok", "DR", 100.0, ts),
        mb.Fingerprint("LLAB", "tok", "CR", 100.0, ts),
    ]
    assert mb.reconstruct_cross_bank_edges(same_bank) == []

    across = [
        mb.Fingerprint("LLAB", "tok", "DR", 100.0, ts),
        mb.Fingerprint("HDFC", "tok", "CR", 100.0, ts),
    ]
    edges = mb.reconstruct_cross_bank_edges(across)
    assert len(edges) == 1
    assert (edges[0].src_bank, edges[0].dst_bank) == ("LLAB", "HDFC")


# ------------------------------------------------ the mechanism behind the 0%

def test_solo_reconstructable_runs_counts_stretches_long_enough_to_report():
    """The whole "solo banks see 0%" result rests on this, so a version that just
    returned 0 would fake the finding. It must count a genuine same-bank run and
    reject one that is too short for `motifs` to report."""
    from launderlab.graph import motifs
    assert motifs.DEFAULT_MIN_HOPS == 2, "this test's cases assume a 2-hop minimum"

    # 3 accounts at one bank = 2 hops = exactly reportable
    assert mb._solo_reconstructable_runs(["A", "A", "A", "B"]) == 1
    # 2 accounts at one bank = 1 hop = below the minimum, invisible to its own bank
    assert mb._solo_reconstructable_runs(["A", "A", "B", "C"]) == 0
    # strictly alternating = nothing anywhere
    assert mb._solo_reconstructable_runs(["A", "B", "C", "D"]) == 0
    # two separate qualifying runs
    assert mb._solo_reconstructable_runs(["A", "A", "A", "B", "B", "B"]) == 2
    # a run that ends the list still counts
    assert mb._solo_reconstructable_runs(["B", "A", "A", "A"]) == 1


def test_deliberate_placement_leaves_no_same_bank_hops():
    assert mb._solo_reconstructable_runs(["A", "B", "C", "D", "A"]) == 0


# ------------------------------------------------------------- the experiment

@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    """A real, small run of one arm -- the plumbing (separate ledger files,
    ATTACH, fingerprints) is exactly what could break, so it is exercised for
    real rather than mocked."""
    return mb.run_arm("naive", customers=200, days=14, seed=19, n_schemes=3, hops=3,
                      work_dir=tmp_path_factory.mktemp("multibank"))


def test_each_bank_ledger_holds_only_its_own_accounts(tmp_path):
    """The isolation this phase depends on. If a bank's file contained another
    bank's rows, its 'solo' detection would silently include data it does not
    have, and the headline blind-spot number would be invented."""
    path = tmp_path / "pooled.duckdb"
    conn = connect(path)
    from launderlab.world.generate import load
    load(conn, n=120, days=7, seed=3)
    mapping = mb.assign_banks(conn, n_banks=4, seed=3)
    conn.close()

    bank_paths = mb.split_into_banks(path, mapping, tmp_path / "banks")
    assert len(bank_paths) == 4

    for bank, bank_path in bank_paths.items():
        bank_conn = connect(bank_path)
        try:
            accounts = {r[0] for r in bank_conn.execute(
                "SELECT account_id FROM accounts").fetchall()}
            txn_accounts = {r[0] for r in bank_conn.execute(
                "SELECT DISTINCT account_id FROM transactions").fetchall()}
            customers = {r[0] for r in bank_conn.execute(
                "SELECT customer_id FROM customers").fetchall()}
        finally:
            bank_conn.close()

        assert accounts, f"{bank} got no accounts at all"
        for account in accounts:
            assert mapping[account] == bank, f"{bank} holds {account}, which banks elsewhere"
        assert txn_accounts <= accounts, f"{bank} holds transactions for foreign accounts"
        # a bank does not hold KYC records for another bank's customers
        assert len(customers) == len(accounts)


def test_pooled_view_sees_chains_that_no_single_bank_can(arm):
    outcomes, _privacy, _mapping = arm
    assert outcomes, "fixture planted no chains"
    pooled = sum(o.pooled_hops_seen for o in outcomes)
    solo = sum(o.best_solo_hops_seen for o in outcomes)
    assert pooled > 0, "the central view should reconstruct the planted chains"
    assert solo <= pooled, "a solo bank cannot see more than the pooled view"


def test_the_blind_spot_is_the_network_not_the_account(arm):
    """The finding this phase exists to make precise: banks DO flag the
    individual mule accounts on their own books; what they cannot do is join
    them into a chain."""
    outcomes, _privacy, _mapping = arm
    flagged = sum(o.accounts_locally_flagged for o in outcomes)
    accounts = sum(len(o.accounts) for o in outcomes)
    solo = sum(o.best_solo_hops_seen for o in outcomes)
    hops = sum(len(o.accounts) - 1 for o in outcomes)

    assert flagged > 0, "banks should still flag individual pass-through accounts"
    assert flagged / accounts > solo / hops if hops else True, (
        "local account-level detection must outperform solo chain reconstruction -- "
        "that gap IS the blind spot")


def test_cooperation_never_beats_the_pooled_view(arm):
    """A protocol that reconstructed MORE than a central view would be a bug in
    the measurement, not a breakthrough."""
    outcomes, _privacy, _mapping = arm
    for o in outcomes:
        assert o.cooperative_hops_seen <= o.pooled_hops_seen
        assert o.cooperative_total_hops <= len(o.accounts) - 1


def test_the_cooperative_view_counts_intra_bank_hops_a_bank_already_holds():
    """Scoring co-operation on cross-boundary recoveries ALONE penalised a
    carelessly placed chain for hops its own bank could already see, and made a
    chain deliberately spread across banks look better covered than a sloppy one
    -- backwards. An intra-bank hop needs no protocol; the bank holds both legs.
    """
    spread = mb.ChainOutcome(
        scheme_id="a", accounts=["A1", "B1", "C1"], banks=["A", "B", "C"],
        spans_banks=3, pooled_hops_seen=2, best_solo_hops_seen=0,
        accounts_locally_flagged=3, cooperative_hops_seen=2, same_bank_hops=0)
    careless = mb.ChainOutcome(
        scheme_id="b", accounts=["A1", "A2", "B1"], banks=["A", "A", "B"],
        spans_banks=2, pooled_hops_seen=2, best_solo_hops_seen=0,
        accounts_locally_flagged=3, cooperative_hops_seen=1, same_bank_hops=1)

    assert spread.cooperative_total_hops == 2
    assert careless.cooperative_total_hops == 2, (
        "the intra-bank hop is known to its own bank and must count")
    # the two sets must be disjoint -- a recovered hop is cross-bank by construction
    assert careless.cooperative_total_hops <= len(careless.accounts) - 1


def test_privacy_notes_record_what_was_shared_and_what_leaked(arm):
    _outcomes, privacy, _mapping = arm
    assert "HMAC(reference)" in privacy.fields_shared
    for never in ("customer name", "account id"):
        assert never in privacy.never_shared
    assert privacy.residual_disclosures, (
        "a privacy prototype that claims no residual disclosure is not being honest")
    assert privacy.fingerprints_published > 0
    assert privacy.banks_participating > 0


def test_privacy_counts_cover_cross_bank_links_only(arm):
    """These two counted ALL hops until this was checked, including intra-bank
    ones that need no protocol and no second bank's co-operation at all -- so
    they overstated both what co-operation had to achieve and what it failed to.
    The report had stopped printing them by then, which is exactly why the wrong
    numbers survived: a number nobody looks at is a number nobody checks."""
    outcomes, privacy, _mapping = arm
    total_hops = sum(len(o.accounts) - 1 for o in outcomes)
    same_bank = sum(o.same_bank_hops for o in outcomes)
    recovered = sum(o.cooperative_hops_seen for o in outcomes)

    assert privacy.cross_bank_links_needing_both_sides == total_hops - same_bank
    assert privacy.cross_bank_links_lost_to_one_sided_flagging == (
        total_hops - same_bank - recovered)
    assert privacy.cross_bank_links_lost_to_one_sided_flagging >= 0, (
        "co-operation cannot recover more cross-bank links than exist")


def test_plant_chains_rejects_an_unknown_placement(tmp_path):
    path = tmp_path / "w.duckdb"
    conn = connect(path)
    try:
        from launderlab.world.generate import load
        load(conn, n=60, days=7, seed=1)
        mapping = mb.assign_banks(conn, n_banks=2, seed=1)
        import random
        with pytest.raises(ValueError, match="placement"):
            mb.plant_chains(conn, mapping, 1, random.Random(1), placement="sideways")
    finally:
        conn.close()


def test_report_states_both_arms_and_the_residual_disclosure(arm):
    outcomes, privacy, _mapping = arm
    text = mb.report({"naive": (outcomes, privacy)})
    assert "CROSS-BANK BLIND SPOT" in text
    assert "NETWORK, NOT THE ACCOUNT" in text
    assert "Never shared" in text
    assert "Residual disclosure" in text
