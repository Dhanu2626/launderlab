"""Shell company / trade-based layering: a shell entity (no real operations, just a
name) pays a real business a handful of large "invoice" payments — dirty money
dressed up as legitimate B2B revenue.

Integration-stage crime (see ledger/FCC-PRIMER.md). Unlike structuring (many small
deposits from no one in particular) this is FEW and LARGE payments concentrated from
ONE counterparty with sequential invoice numbers — the real-world tell is a business's
revenue suddenly dominated by a single newly-seen customer. No real account backs the
shell, same "ghost counterparty" pattern as structuring's CASH deposits. Ground truth
is recorded in scheme_labels — detection code (Phase 3+) must never read that table.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import duckdb

from launderlab.db.ledger import account_opening_balance, recompute_account_balances
from launderlab.typology.mule_network import SHELL_NAMES


def inject(conn: duckdb.DuckDBPyConnection, scheme_id: str, account_id: str,
           window_start: date, rng: random.Random, window_days: int = 25,
           target_total: int | None = None, n_invoices: int | None = None) -> int:
    """Inject fake invoice payments from one shell company into `account_id`'s
    existing history. `target_total` (default: a random Rs 15-40 lakh) is split into
    `n_invoices` (default: 3-8) large, unevenly-sized payments, all from the same
    shell name with sequential invoice numbers. Returns the number of injected rows.
    """
    if target_total is None:
        target_total = rng.randrange(1500000, 4000001, 5000)
    if n_invoices is None:
        n_invoices = rng.randrange(3, 9)

    opening = account_opening_balance(conn, account_id)
    if opening is None:
        raise ValueError(f"account {account_id} has no transactions to inject into")

    shell = rng.choice(SHELL_NAMES)
    amounts = _split_uneven(rng, target_total, n_invoices)

    new_rows = []
    for invoice_no, amt in enumerate(amounts, start=1001):
        d = rng.randrange(0, window_days)
        ts = datetime.combine(window_start + timedelta(days=d),
                               time(rng.randrange(10, 18), rng.randrange(60)))
        ref = str(rng.randrange(100000, 1000000))
        channel = rng.choice(["NEFT", "IMPS"])
        new_rows.append((ts, account_id, "CR", channel, amt, shell, ref,
                         f"{channel}/CR/{ref}/{shell} INV-{invoice_no}", 0))

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
        "INSERT INTO scheme_labels VALUES (?, ?, 'shell_company', 'integration')",
        [(txn_id, scheme_id) for (txn_id,) in new_ids],
    )
    return len(new_ids)


def _split_uneven(rng: random.Random, total: int, n: int) -> list[int]:
    """Split `total` into `n` large, unevenly-sized pieces — a handful of big
    invoices, not a suspiciously round even split. Uses proportional weights (not a
    subtracted remainder) so the last piece can never go negative: each of the first
    n-1 pieces is a weighted fraction of total, always summing to less than total."""
    weights = [rng.uniform(0.7, 1.3) for _ in range(n)]
    scale = total / sum(weights)
    amounts = [int(round(w * scale, -3)) for w in weights[:-1]]
    amounts.append(int(total - sum(amounts)))
    return amounts
