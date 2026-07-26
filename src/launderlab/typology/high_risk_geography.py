"""High-risk geography: a remittance tied to a FATF-style high-risk jurisdiction.

Unlike the other six typologies, the "tell" here isn't a pattern of many
transactions — it's purely geographic. A single, otherwise completely ordinary
international transfer becomes notable because of *which country* the counterparty
is in. This is really a screening signal (see FCC-PRIMER.md, Phase 4) surfaced here
as an injectable typology so it carries the same ground truth the others do.

Country lists are illustrative/synthetic but mirror the real FATF category
structure (Call for Action / high-risk vs. Increased Monitoring) — see the
project's ethics note in README.md. Ground truth is recorded in scheme_labels —
detection code (Phase 3+) must never read that table.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import duckdb

from launderlab.db.ledger import (
    account_opening_balance,
    account_true_minimum,
    recompute_account_balances,
    safe_debit_ceiling,
)

# Illustrative, synthetic list mirroring FATF's real category structure.
HIGH_RISK_COUNTRIES = [
    ("Iran", "IR", "blacklist"), ("North Korea", "KP", "blacklist"),
    ("Myanmar", "MM", "blacklist"), ("Syria", "SY", "greylist"),
    ("Yemen", "YE", "greylist"), ("South Sudan", "SS", "greylist"),
    ("Turkey", "TR", "greylist"), ("Nigeria", "NG", "greylist"),
    ("Philippines", "PH", "greylist"),
]


def inject(conn: duckdb.DuckDBPyConnection, scheme_id: str, account_id: str,
           window_start: date, rng: random.Random, window_days: int = 25,
           n_transactions: int | None = None,
           amount_range: tuple[int, int] = (100000, 900000)) -> int:
    """Inject `n_transactions` (default 1-3) remittances tied to a high-risk
    jurisdiction into `account_id`'s existing history — a mix of inbound (money
    arriving from) and outbound (money wired to). Outbound legs are capped by
    `ledger.safe_debit_ceiling()` so they can never overdraw. Returns rows injected.
    """
    opening_balance = account_opening_balance(conn, account_id)
    if opening_balance is None:
        raise ValueError(f"account {account_id} has no transactions to inject into")
    min_balance = account_true_minimum(conn, account_id)
    safe_ceiling = safe_debit_ceiling(min_balance)

    if n_transactions is None:
        n_transactions = rng.randrange(1, 4)

    # A running budget, not a per-row cap: if several legs in this call land as
    # outbound (DR), each capped independently at the same ceiling could still sum
    # past it. Spending down one shared budget keeps the COMBINED effect bounded,
    # the same class of bug round_tripping hit on Day 10, just across rows within
    # one call instead of across separate calls.
    remaining_safe = safe_ceiling
    new_rows = []
    for _ in range(n_transactions):
        country, iso, category = rng.choice(HIGH_RISK_COUNTRIES)
        d = rng.randrange(0, window_days)
        ts = datetime.combine(window_start + timedelta(days=d),
                               time(rng.randrange(9, 20), rng.randrange(60)))
        ref = str(rng.randrange(100000, 1000000))
        counterparty = f"REMITTANCE {country.upper()} {iso}"
        amount = rng.randrange(*amount_range)

        if rng.random() < 0.5:
            new_rows.append((ts, account_id, "CR", "INT", amount, counterparty, ref,
                             f"INT/CR/{ref}/{counterparty}", 0, category))
        else:
            amount = max(min(amount, remaining_safe), 1)
            remaining_safe -= amount
            new_rows.append((ts, account_id, "DR", "INT", amount, counterparty, ref,
                             f"INT/DR/{ref}/{counterparty}", 0, category))

    before_max = conn.execute("SELECT coalesce(max(txn_id), 0) FROM transactions").fetchone()[0]
    conn.executemany(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " counterparty_name, counterparty_ref, narration, balance_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [row[:-1] for row in new_rows],
    )
    recompute_account_balances(conn, account_id, opening_balance)

    # executemany inserts in list order and txn_id's sequence increments per row in
    # that same order, so ORDER BY txn_id lines up positionally with new_rows —
    # safe here because every row in this call targets the same account_id (unlike
    # mule_network, which needs cross-account correlation and can't rely on this).
    new_ids = conn.execute(
        "SELECT txn_id FROM transactions WHERE txn_id > ? AND account_id = ?"
        " ORDER BY txn_id",
        [before_max, account_id],
    ).fetchall()
    labels = [(txn_id, scheme_id, "high_risk_geography", new_rows[i][-1])
              for i, (txn_id,) in enumerate(new_ids)]
    conn.executemany("INSERT INTO scheme_labels VALUES (?, ?, ?, ?)", labels)
    return len(new_ids)
