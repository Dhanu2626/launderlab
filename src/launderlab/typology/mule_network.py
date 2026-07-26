"""Mule network / layering: money hops through a chain of accounts fast, each
mule keeping a small cut, to bury the paper trail between source and sink.

Layering-stage crime (see ledger/FCC-PRIMER.md). No single hop looks criminal —
the crime is only visible in the pattern across hops, which is exactly why
Phase 5's graph analytics exists. Ground truth is recorded in scheme_labels —
detection code (Phase 3+) must never read that table.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import duckdb

from launderlab.db.ledger import account_opening_balance, recompute_account_balances
from launderlab.world.population import BANKS

SHELL_NAMES = ["NEXA TRADERS", "VELOCITY IMPEX", "STARCREST VENTURES", "BLUEHAVEN AGENCIES",
               "CRESTLINE OVERSEAS", "PRIME ARC ENTERPRISES"]


def _vpa(rng: random.Random, full_name: str) -> str:
    parts = full_name.lower().split()
    first, last = parts[0], parts[-1]
    return f"{first}.{last}{rng.randrange(10, 99)}@{rng.choice(BANKS)}"


def inject(conn: duckdb.DuckDBPyConnection, scheme_id: str, account_chain: list[str],
           window_start: date, rng: random.Random, total: int | None = None,
           cut_pct: tuple[float, float] = (0.03, 0.08),
           hop_hours: tuple[float, float] = (2, 30)) -> int:
    """Inject a layering scheme moving money through `account_chain` in order.

    `account_chain[0]` is the source (receives the money first), `account_chain[-1]`
    is the sink; everything between is a mule, keeping a small cut (`cut_pct`) and
    forwarding the rest `hop_hours` later. Every account in the chain has its full
    history replayed and balance_after rewritten. Returns the number of injected
    transaction legs (a two-leg DR+CR per hop, plus one entry leg into the source).
    """
    if len(account_chain) < 2:
        raise ValueError("a mule chain needs at least a source and a sink")
    if total is None:
        total = rng.randrange(500000, 1500001, 5000)

    openings = {}
    for acct in account_chain:
        opening = account_opening_balance(conn, acct)
        if opening is None:
            raise ValueError(f"account {acct} has no transactions to inject into")
        openings[acct] = opening

    placeholders = ", ".join("?" * len(account_chain))
    names = dict(conn.execute(
        f"SELECT a.account_id, c.full_name FROM accounts a"
        f" JOIN customers c USING (customer_id) WHERE a.account_id IN ({placeholders})",
        account_chain,
    ).fetchall())
    vpas = {acct: _vpa(rng, name) for acct, name in names.items()}

    new_rows = []
    ts = datetime.combine(window_start, time(rng.randrange(9, 19), rng.randrange(60)))
    entry_ref = str(rng.randrange(100000, 1000000))
    entry_source = rng.choice(SHELL_NAMES)
    new_rows.append((ts, account_chain[0], "CR", "IMPS", total, entry_source, entry_ref,
                     f"IMPS/CR/{entry_ref}/{entry_source}", 0))

    amount = total
    for i in range(len(account_chain) - 1):
        payer, payee = account_chain[i], account_chain[i + 1]
        forward = int(amount * (1 - rng.uniform(*cut_pct)))
        ts += timedelta(hours=rng.uniform(*hop_hours))
        ref = str(rng.randrange(100000, 1000000))
        channel = rng.choice(["UPI", "IMPS"])
        new_rows.append((ts, payer, "DR", channel, forward, names[payee], vpas[payee],
                         f"{channel}/DR/{ref}/{vpas[payee]}", 0))
        new_rows.append((ts, payee, "CR", channel, forward, names[payer], vpas[payer],
                         f"{channel}/CR/{ref}/{vpas[payer]}", 0))
        amount = forward

    before_max = conn.execute("SELECT coalesce(max(txn_id), 0) FROM transactions").fetchone()[0]
    conn.executemany(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " counterparty_name, counterparty_ref, narration, balance_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        new_rows,
    )
    for acct in account_chain:
        recompute_account_balances(conn, acct, openings[acct])

    roles = {account_chain[0]: "source", account_chain[-1]: "sink"}
    labels = []
    for acct in account_chain:
        role = roles.get(acct, "mule")
        new_ids = conn.execute(
            "SELECT txn_id FROM transactions WHERE txn_id > ? AND account_id = ?",
            [before_max, acct],
        ).fetchall()
        labels.extend((txn_id, scheme_id, role) for (txn_id,) in new_ids)

    conn.executemany("INSERT INTO scheme_labels VALUES (?, ?, 'layering', ?)", labels)
    return len(labels)
