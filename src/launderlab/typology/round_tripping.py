"""Round-tripping: money leaves an account to an offshore/shell entity and returns
to the SAME account later, slightly inflated — used both to obscure origin and to
inflate a business's apparent turnover.

Layering-stage crime, a variant that returns to its own source instead of ending
elsewhere (see ledger/FCC-PRIMER.md and typology/mule_network.py). Ground truth is
recorded in scheme_labels — detection code (Phase 3+) must never read that table.

Unlike the other typologies, the departure leg is a debit against money the account
*already has* (not freshly injected), so it must never overdraw an existing balance
trajectory. Safety: the departure amount is capped at a fraction of the account's
lowest historical balance, which guarantees no overdraft regardless of exactly when
in the timeline the departure lands (see `_safe_departure_amount`).
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import duckdb

from launderlab.db.ledger import account_opening_balance, recompute_account_balances
from launderlab.typology.mule_network import SHELL_NAMES


def inject(conn: duckdb.DuckDBPyConnection, scheme_id: str, account_id: str,
           window_start: date, rng: random.Random, window_days: int = 20,
           amount: int | None = None, hop_days: tuple[int, int] = (2, 10),
           inflation_pct: tuple[float, float] = (0.02, 0.10)) -> int:
    """Inject a round-trip: `account_id` sends money out to a shell entity, then
    receives it back `hop_days` later from a *different* shell name, inflated by
    `inflation_pct`. Best used on business accounts — realistic scale depends on
    the account already holding a substantial balance. Returns rows injected (2).
    """
    opening = _account_min_and_opening(conn, account_id)
    if opening is None:
        raise ValueError(f"account {account_id} has no transactions to inject into")
    min_balance, opening_balance = opening

    departure_amount = _safe_departure_amount(rng, min_balance, amount)

    max_hop = int(hop_days[1]) + 1
    departure_day = rng.randrange(0, max(window_days - max_hop, 1))
    departure_ts = datetime.combine(window_start + timedelta(days=departure_day),
                                     time(rng.randrange(10, 17), rng.randrange(60)))
    return_ts = departure_ts + timedelta(days=rng.uniform(*hop_days))

    depart_shell, return_shell = rng.sample(SHELL_NAMES, 2)
    return_amount = int(departure_amount * (1 + rng.uniform(*inflation_pct)))

    ref_out, ref_in = str(rng.randrange(100000, 1000000)), str(rng.randrange(100000, 1000000))
    new_rows = [
        (departure_ts, account_id, "DR", "RTGS", departure_amount, depart_shell, ref_out,
         f"RTGS/DR/{ref_out}/{depart_shell} INVESTMENT", 0),
        (return_ts, account_id, "CR", "RTGS", return_amount, return_shell, ref_in,
         f"RTGS/CR/{ref_in}/{return_shell} INVESTMENT RETURN", 0),
    ]

    before_max = conn.execute("SELECT coalesce(max(txn_id), 0) FROM transactions").fetchone()[0]
    conn.executemany(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " counterparty_name, counterparty_ref, narration, balance_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        new_rows,
    )
    recompute_account_balances(conn, account_id, opening_balance)

    new_ids = conn.execute(
        "SELECT txn_id, direction FROM transactions WHERE txn_id > ? AND account_id = ?"
        " ORDER BY ts",
        [before_max, account_id],
    ).fetchall()
    roles = {"DR": "departure", "CR": "return"}
    conn.executemany(
        "INSERT INTO scheme_labels VALUES (?, ?, 'round_tripping', ?)",
        [(txn_id, scheme_id, roles[d]) for txn_id, d in new_ids],
    )
    return len(new_ids)


def _account_min_and_opening(conn: duckdb.DuckDBPyConnection, account_id: str):
    """Returns (lowest balance the account has EVER been at, true opening balance)
    for the account, or None if it has no transactions.

    The lowest point isn't just min(balance_after) — that only covers balances
    *after* existing transactions. The balance *before* the first transaction (the
    opening balance itself) is a real point in the timeline too, and if a newly
    injected departure lands earlier than every existing row, it becomes the new
    first transaction and is computed straight against that opening balance. A
    safety cap that ignores this can pass on a bank with the minimum truly at the
    end of the month and still overdraw a departure landing on day zero.
    """
    opening = account_opening_balance(conn, account_id)
    if opening is None:
        return None
    existing_min = conn.execute(
        "SELECT min(balance_after) FROM transactions WHERE account_id = ?", [account_id]
    ).fetchone()[0]
    true_min = min(float(opening), float(existing_min))
    return true_min, opening


def _safe_departure_amount(rng: random.Random, min_balance, requested: int | None) -> int:
    """Cap the departure amount at a fraction of the account's historical minimum
    balance — since that minimum is a lower bound on the balance at ANY point in the
    account's timeline, staying under it (times a safety margin) guarantees the
    injected debit can never overdraw, no matter which day it lands on."""
    safe_ceiling = int(float(min_balance) * 0.6)
    if requested is None:
        return max(int(safe_ceiling * rng.uniform(0.4, 1.0)), 1)
    return min(requested, safe_ceiling) if safe_ceiling > 0 else 1
