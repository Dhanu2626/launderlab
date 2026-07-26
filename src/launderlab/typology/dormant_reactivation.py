"""Dormant-account reactivation: an account that's gone quiet suddenly receives a
large sum and spends nearly all of it within hours — the classic sign of a
recruited money mule or a taken-over dormant account.

Placement/layering-adjacent crime (see ledger/FCC-PRIMER.md) — the red flag isn't
the amount alone, it's the *departure from the account's own established baseline*,
which is exactly what Phase 6's ML tournament is built to notice. Ground truth is
recorded in scheme_labels — detection code (Phase 3+) must never read that table.

Safe by construction: the credit is always inserted before the debits that spend it
down, so — like mule_network — there's no need for the historical-minimum proof
round_tripping needed; the injected debits only ever draw against what was just
credited, never pre-existing balance.
"""

from __future__ import annotations

import random
from datetime import timedelta

import duckdb

from launderlab.db.ledger import account_opening_balance, recompute_account_balances
from launderlab.typology.shell_company import split_uneven


def inject(conn: duckdb.DuckDBPyConnection, scheme_id: str, account_id: str,
           rng: random.Random, gap_days: tuple[float, float] = (3, 10),
           burst_total: int | None = None, n_cashouts: int | None = None) -> int:
    """Find `account_id`'s last existing transaction, wait `gap_days` of quiet, then
    inject a sudden large credit followed by `n_cashouts` (default 2-4) rapid debits
    spending down ~90-97% of it within hours. Returns rows injected.
    """
    opening = account_opening_balance(conn, account_id)
    if opening is None:
        raise ValueError(f"account {account_id} has no transactions to inject into")

    last_ts = conn.execute(
        "SELECT max(ts) FROM transactions WHERE account_id = ?", [account_id]
    ).fetchone()[0]

    if burst_total is None:
        burst_total = rng.randrange(80000, 2500001, 5000)
    if n_cashouts is None:
        n_cashouts = rng.randrange(2, 5)

    reactivate_ts = last_ts + timedelta(days=rng.uniform(*gap_days),
                                         hours=rng.uniform(0, 4))
    ref_in = str(rng.randrange(100000, 1000000))
    counterparty = f"cust{rng.randrange(1000, 9999)}@ok{rng.choice(['sbi', 'hdfc', 'icici'])}"
    new_rows = [(reactivate_ts, account_id, "CR", "IMPS", burst_total, None, ref_in,
                 f"IMPS/CR/{ref_in}/{counterparty}", 0)]

    cashout_total = int(burst_total * rng.uniform(0.90, 0.97))
    ts = reactivate_ts
    for amt in split_uneven(rng, cashout_total, n_cashouts):
        ts += timedelta(minutes=rng.uniform(20, 180))
        ref = str(rng.randrange(100000, 1000000))
        if rng.random() < 0.4:
            new_rows.append((ts, account_id, "DR", "ATM", amt, None, None,
                             f"ATM-CASH/DR/{rng.randrange(10, 99)}", 0))
        else:
            cp = f"cust{rng.randrange(1000, 9999)}@ok{rng.choice(['sbi', 'hdfc', 'icici'])}"
            new_rows.append((ts, account_id, "DR", "UPI", amt, None, ref,
                             f"UPI/DR/{ref}/{cp}", 0))

    before_max = conn.execute("SELECT coalesce(max(txn_id), 0) FROM transactions").fetchone()[0]
    conn.executemany(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " counterparty_name, counterparty_ref, narration, balance_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        new_rows,
    )
    recompute_account_balances(conn, account_id, opening)

    new_ids = conn.execute(
        "SELECT txn_id, direction FROM transactions WHERE txn_id > ? AND account_id = ?"
        " ORDER BY ts",
        [before_max, account_id],
    ).fetchall()
    roles = {"CR": "reactivation", "DR": "cashout"}
    conn.executemany(
        "INSERT INTO scheme_labels VALUES (?, ?, 'dormant_reactivation', ?)",
        [(txn_id, scheme_id, roles[d]) for txn_id, d in new_ids],
    )
    return len(new_ids)
