"""The rules engine — six tunable scenarios, each aimed at one Phase 2 typology's
actual transaction signature.

CRITICAL BOUNDARY: nothing in this module may read scheme_labels. A rule earns its
alert from the transaction data alone, the same way a real analyst would — ground
truth is for scoring.py to grade against afterward, never for detection to peek at.
See PROJECT.md's quality bar.

Each rule is a plain function with named, tunable parameters — the "scenario DSL"
in spirit: a scenario is just a rule plus the specific parameter values you chose
for it. A textual parser would be unrequested complexity for a solo project; a
Python function with keyword defaults IS a declarative, tunable configuration
surface without inventing a language nobody else will ever write in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb

HIGH_RISK_WATCHLIST = ["IRAN", "NORTH KOREA", "MYANMAR", "SYRIA", "YEMEN",
                        "SOUTH SUDAN", "TURKEY", "NIGERIA", "PHILIPPINES"]


@dataclass(frozen=True)
class Alert:
    account_id: str
    rule: str
    reason: str
    ts: datetime
    amount: float


def structuring_burst(conn: duckdb.DuckDBPyConnection, ceiling: int = 100000,
                       min_count: int = 5, min_total: int = 500000) -> list[Alert]:
    """Many CASH deposits, each under `ceiling`, summing past `min_total` — the
    classic structuring/smurfing signature."""
    rows = conn.execute(
        "SELECT account_id, count(*), sum(amount)::DOUBLE, max(ts) FROM transactions"
        " WHERE direction = 'CR' AND channel = 'CASH' AND amount < ?"
        " GROUP BY account_id HAVING count(*) >= ? AND sum(amount) >= ?",
        [ceiling, min_count, min_total],
    ).fetchall()
    return [Alert(acct, "structuring_burst",
                  f"{n} cash deposits under Rs {ceiling:,} totaling Rs {total:,.0f}", ts, total)
            for acct, n, total, ts in rows]


def rapid_pass_through(conn: duckdb.DuckDBPyConnection, min_amount: int = 300000,
                        hop_hours: int = 48, min_ratio: float = 0.85) -> list[Alert]:
    """A large credit followed within `hop_hours` by a debit for most of it — money
    that didn't stay. Catches each mule hop in a layering chain individually (the
    chain as a whole is Phase 5's job)."""
    rows = conn.execute(
        """
        SELECT cr.account_id, min(cr.ts) AS cr_ts, min(cr.amount)::DOUBLE AS cr_amt
        FROM transactions cr
        JOIN transactions dr
          ON dr.account_id = cr.account_id
         AND dr.direction = 'DR' AND cr.direction = 'CR'
         AND dr.ts > cr.ts AND dr.ts <= cr.ts + INTERVAL (?) HOUR
         AND dr.amount >= cr.amount * ?
        WHERE cr.amount >= ?
        GROUP BY cr.account_id
        """,
        [hop_hours, min_ratio, min_amount],
    ).fetchall()
    return [Alert(acct, "rapid_pass_through",
                  f"Rs {amt:,.0f} in, most of it out within {hop_hours}h", ts, amt)
            for acct, ts, amt in rows]


def round_trip(conn: duckdb.DuckDBPyConnection, min_amount: int = 1000,
               hop_days: int = 12, min_return_ratio: float = 0.95,
               channel: str = "RTGS") -> list[Alert]:
    """A debit followed within `hop_days` by a comparable-or-larger credit on the
    SAME high-value channel — money that left and came back. The channel filter,
    not the amount, is what makes this precise: normal business AP/AR cycles look
    similar in aggregate (a purchase debit followed by an unrelated receipt credit
    within days is completely routine), but they run over NEFT/IMPS. RTGS never
    appears as a debit anywhere in a legitimate account's history in this world
    (only as a single NRI-remittance credit) — restricting to it cut false
    positives from 24 to 0 on a clean 300-customer world without losing a single
    true positive, which is also why `min_amount` stays low: the channel already
    carries the precision, so a higher amount floor would only cost recall on
    smaller businesses whose round-trip safety cap is naturally modest
    (see FIELD-NOTES Phase 3)."""
    rows = conn.execute(
        """
        SELECT dr.account_id, min(dr.ts) AS dr_ts, min(dr.amount)::DOUBLE AS dr_amt
        FROM transactions dr
        JOIN transactions cr
          ON cr.account_id = dr.account_id
         AND cr.direction = 'CR' AND dr.direction = 'DR'
         AND cr.channel = ? AND dr.channel = ?
         AND cr.ts > dr.ts AND cr.ts <= dr.ts + INTERVAL (?) DAY
         AND cr.amount >= dr.amount * ?
        WHERE dr.amount >= ?
        GROUP BY dr.account_id
        """,
        [channel, channel, hop_days, min_return_ratio, min_amount],
    ).fetchall()
    return [Alert(acct, "round_trip", f"Rs {amt:,.0f} left and came back within {hop_days}d",
                  ts, amt) for acct, ts, amt in rows]


def counterparty_concentration(conn: duckdb.DuckDBPyConnection, min_total: int = 1000000,
                                min_concentration: float = 0.5, min_count: int = 2) -> list[Alert]:
    """One counterparty accounts for most of an account's credited money — a
    business fed almost entirely by one newly-seen "customer."""
    rows = conn.execute(
        """
        WITH per_cp AS (
            SELECT account_id, counterparty_name, sum(amount)::DOUBLE cp_total,
                   count(*) n, max(ts) last_ts
            FROM transactions WHERE direction = 'CR' AND counterparty_name IS NOT NULL
            GROUP BY account_id, counterparty_name
        ), per_acct AS (
            SELECT account_id, sum(amount)::DOUBLE acct_total FROM transactions
            WHERE direction = 'CR' GROUP BY account_id
        )
        SELECT p.account_id, p.counterparty_name, p.cp_total, p.last_ts,
               p.cp_total / a.acct_total AS concentration
        FROM per_cp p JOIN per_acct a USING (account_id)
        WHERE p.cp_total >= ? AND p.n >= ? AND p.cp_total / a.acct_total >= ?
        """,
        [min_total, min_count, min_concentration],
    ).fetchall()
    return [Alert(acct, "counterparty_concentration",
                  f"{conc:.0%} of credits from one counterparty ({cp}), Rs {total:,.0f}",
                  ts, total)
            for acct, cp, total, ts, conc in rows]


def dormancy_burst(conn: duckdb.DuckDBPyConnection, min_gap_days: int = 7,
                    cashout_hours: int = 24, min_cashout_ratio: float = 0.5,
                    min_amount: int = 20000) -> list[Alert]:
    """A credit that follows an unusually long quiet stretch, followed itself within
    `cashout_hours` by debits spending down most of it — not just "a big number,"
    since a normal weekly pocket-money credit is also "big relative to average" and
    also follows a several-day gap. The real tell is what happens NEXT: legitimate
    income gets spent gradually over days; a reactivated account gets drained within
    hours. Requiring the rapid cash-out cut a false positive on a real weekly-pocket-
    money student account to zero without losing recall on the injected pattern."""
    rows = conn.execute(
        """
        WITH gaps AS (
            SELECT txn_id, account_id, ts, amount, direction,
                   ts - lag(ts) OVER (PARTITION BY account_id ORDER BY ts, txn_id) AS gap
            FROM transactions
        ), bursts AS (
            SELECT account_id, ts, amount FROM gaps
            WHERE direction = 'CR' AND gap >= INTERVAL (?) DAY AND amount >= ?
        )
        SELECT b.account_id, min(b.ts), min(b.amount)::DOUBLE
        FROM bursts b
        JOIN transactions d
          ON d.account_id = b.account_id AND d.direction = 'DR'
         AND d.ts > b.ts AND d.ts <= b.ts + INTERVAL (?) HOUR
        GROUP BY b.account_id, b.ts, b.amount
        HAVING sum(d.amount) >= min(b.amount) * ?
        """,
        [min_gap_days, min_amount, cashout_hours, min_cashout_ratio],
    ).fetchall()
    return [Alert(acct, "dormancy_burst",
                  f"Rs {amt:,.0f} after a quiet stretch, {min_cashout_ratio:.0%}+ cashed out within {cashout_hours}h",
                  ts, amt)
            for acct, ts, amt in rows]


def high_risk_geography(conn: duckdb.DuckDBPyConnection,
                         watchlist: list[str] | None = None) -> list[Alert]:
    """Any international transaction naming a FATF-style high-risk jurisdiction."""
    watchlist = watchlist or HIGH_RISK_WATCHLIST
    rows = conn.execute(
        "SELECT account_id, ts, amount::DOUBLE, counterparty_name FROM transactions"
        " WHERE channel = 'INT' AND counterparty_name IS NOT NULL"
    ).fetchall()
    alerts = []
    for acct, ts, amt, cp in rows:
        hit = next((c for c in watchlist if c in cp.upper()), None)
        if hit:
            alerts.append(Alert(acct, "high_risk_geography",
                                 f"International transfer tied to {hit.title()}", ts, amt))
    return alerts


DEFAULT_SCENARIO = [structuring_burst, rapid_pass_through, round_trip,
                    counterparty_concentration, dormancy_burst, high_risk_geography]


def run_all(conn: duckdb.DuckDBPyConnection,
            scenario: list = None) -> list[Alert]:
    """Run every rule in `scenario` (default: all six) and return the combined
    alert list. One account can appear more than once if multiple rules fire."""
    scenario = scenario or DEFAULT_SCENARIO
    alerts = []
    for rule in scenario:
        alerts.extend(rule(conn))
    return alerts
