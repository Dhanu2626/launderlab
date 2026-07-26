"""Structuring/smurfing: break a large cash sum into many deposits under a
reporting-style ceiling, injected into an already-generated account's history.

Placement-stage crime (see ledger/FCC-PRIMER.md). Ground truth is recorded in
scheme_labels — detection code (Phase 3+) must never read that table.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import duckdb

from launderlab.db.ledger import account_opening_balance, recompute_account_balances


def inject(conn: duckdb.DuckDBPyConnection, scheme_id: str, account_id: str,
           window_start: date, rng: random.Random, window_days: int = 20,
           target_total: int | None = None, deposit_ceiling: int = 95000) -> int:
    """Inject a structuring scheme into `account_id`'s existing history.

    Splits `target_total` (default: a random Rs 8-20 lakh) into many CASH deposits,
    each under `deposit_ceiling`, spread across `window_days` days starting at
    `window_start`. Every transaction on this account is then replayed in time
    order and its balance_after rewritten, since an injected deposit shifts every
    later row's running balance. Returns the number of injected transactions.
    """
    if target_total is None:
        target_total = rng.randrange(800000, 2000001, 5000)

    opening = account_opening_balance(conn, account_id)
    if opening is None:
        raise ValueError(f"account {account_id} has no transactions to inject into")

    new_rows = []
    for amt in _split_amounts(rng, target_total, deposit_ceiling):
        d = rng.randrange(0, window_days)
        ts = datetime.combine(window_start + timedelta(days=d),
                               time(rng.randrange(9, 19), rng.randrange(60)))
        ref = str(rng.randrange(100000, 1000000))
        branch = f"BR-{rng.randrange(10, 99)}"
        new_rows.append((ts, account_id, "CR", "CASH", amt, None, None,
                         f"CASH DEP/CR/{ref}/{branch}", 0))

    before_max = conn.execute("SELECT coalesce(max(txn_id), 0) FROM transactions").fetchone()[0]
    conn.executemany(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " counterparty_name, counterparty_ref, narration, balance_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        new_rows,
    )
    recompute_account_balances(conn, account_id, opening)

    new_ids = conn.execute(
        "SELECT txn_id FROM transactions WHERE txn_id > ? AND account_id = ?",
        [before_max, account_id],
    ).fetchall()
    conn.executemany(
        "INSERT INTO scheme_labels VALUES (?, ?, 'structuring', 'placement')",
        [(txn_id, scheme_id) for (txn_id,) in new_ids],
    )
    return len(new_ids)


def _split_amounts(rng: random.Random, total: int, ceiling: int) -> list[int]:
    """Break `total` into pieces each under `ceiling` — plausible cash deposits,
    not round numbers, comfortably clear of the ceiling so no single piece looks
    like an obviously-tuned amount."""
    floor = int(ceiling * 0.35)
    amounts = []
    remaining = total
    while remaining > ceiling:
        amt = rng.randrange(floor, ceiling)
        amounts.append(amt)
        remaining -= amt
    if remaining > 0:
        amounts.append(remaining)
    return amounts
