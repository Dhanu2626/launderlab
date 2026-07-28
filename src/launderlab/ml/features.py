"""Per-account behavioural features, computed from the ledger alone.

Every feature here is something a real bank could compute from its own core
banking data — no feature encodes "was this account part of an injected scheme".
That separation is what makes the tournament's scores meaningful rather than
circular.

Features are grouped by the question they answer about an account:
  volume     how much moves, how often
  amounts    how big, how varied, how suspiciously shaped
  network    how many counterparties, how concentrated
  timing     how bursty, how quickly money leaves again
  balance    how much sits there, how volatile
  channels   which payment rails it uses

BOUNDARY: nothing here may read `scheme_labels`. Labels are attached in
dataset.py, which is the scorer-side module.
"""

from __future__ import annotations

import duckdb

# Amounts sitting just under a reporting ceiling are the classic structuring
# tell; a legitimate account has no reason to cluster there.
SUB_THRESHOLD_LOW = 70000
SUB_THRESHOLD_HIGH = 100000

# "Money did not stay" — a credit followed by a comparable debit within a day.
RAPID_WINDOW_HOURS = 24
RAPID_RATIO = 0.70

FEATURE_SQL = f"""
WITH base AS (
    SELECT account_id,
           direction,
           channel,
           amount::DOUBLE AS amt,
           ts,
           balance_after::DOUBLE AS bal,
           coalesce(counterparty_ref, counterparty_name, 'UNKNOWN') AS cp
    FROM transactions
),
agg AS (
    SELECT account_id,
           count(*)                                                        AS txn_count,
           sum(CASE WHEN direction = 'CR' THEN amt ELSE 0 END)             AS total_in,
           sum(CASE WHEN direction = 'DR' THEN amt ELSE 0 END)             AS total_out,
           avg(amt)                                                        AS mean_amount,
           median(amt)                                                     AS median_amount,
           max(amt)                                                        AS max_amount,
           coalesce(stddev_pop(amt), 0)                                    AS std_amount,
           count(DISTINCT cp)                                              AS distinct_counterparties,
           sum(CASE WHEN direction = 'CR' THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS credit_ratio,
           count(DISTINCT date_trunc('day', ts))                           AS active_days,
           min(bal)                                                        AS balance_min,
           max(bal)                                                        AS balance_max,
           avg(bal)                                                        AS balance_mean,
           coalesce(stddev_pop(bal), 0)                                    AS balance_std,
           sum(CASE WHEN amt = round(amt, -3) THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS round_amount_ratio,
           sum(CASE WHEN amt BETWEEN {SUB_THRESHOLD_LOW} AND {SUB_THRESHOLD_HIGH}
                    THEN 1 ELSE 0 END)::DOUBLE / count(*)                  AS sub_threshold_ratio,
           sum(CASE WHEN channel = 'CASH' THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS pct_cash,
           sum(CASE WHEN channel = 'UPI'  THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS pct_upi,
           sum(CASE WHEN channel IN ('NEFT','IMPS','RTGS') THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS pct_wire,
           sum(CASE WHEN channel = 'ATM'  THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS pct_atm,
           sum(CASE WHEN channel = 'INT'  THEN 1 ELSE 0 END)::DOUBLE
               / count(*)                                                  AS pct_international
    FROM base
    GROUP BY account_id
),
cp_shares AS (
    SELECT account_id, cp,
           count(*)::DOUBLE / sum(count(*)) OVER (PARTITION BY account_id) AS p
    FROM base GROUP BY account_id, cp
),
concentration AS (
    SELECT account_id,
           -sum(p * ln(p)) AS counterparty_entropy,
           max(p)          AS top_counterparty_share
    FROM cp_shares GROUP BY account_id
),
gaps AS (
    SELECT account_id, max(gap_hours) AS max_gap_hours, avg(gap_hours) AS mean_gap_hours
    FROM (
        SELECT account_id,
               date_diff('second', lag(ts) OVER (PARTITION BY account_id ORDER BY ts, txn_id), ts)
                   / 3600.0 AS gap_hours
        FROM transactions
    ) WHERE gap_hours IS NOT NULL
    GROUP BY account_id
),
rapid AS (
    SELECT cr.account_id,
           count(*)::DOUBLE AS rapid_credits,
           sum(cr.amt)      AS rapid_amount
    FROM base cr
    WHERE cr.direction = 'CR'
      AND EXISTS (
          SELECT 1 FROM base dr
          WHERE dr.account_id = cr.account_id
            AND dr.direction = 'DR'
            AND dr.ts > cr.ts
            AND dr.ts <= cr.ts + INTERVAL {RAPID_WINDOW_HOURS} HOUR
            AND dr.amt >= cr.amt * {RAPID_RATIO}
      )
    GROUP BY cr.account_id
)
SELECT a.account_id,
       a.txn_count, a.total_in, a.total_out,
       a.total_in - a.total_out                                   AS net_flow,
       a.mean_amount, a.median_amount, a.max_amount, a.std_amount,
       a.std_amount / nullif(a.mean_amount, 0)                    AS amount_cv,
       a.distinct_counterparties,
       a.distinct_counterparties::DOUBLE / a.txn_count            AS counterparty_ratio,
       coalesce(c.counterparty_entropy, 0)                        AS counterparty_entropy,
       coalesce(c.top_counterparty_share, 1)                      AS top_counterparty_share,
       a.credit_ratio, a.active_days,
       a.txn_count::DOUBLE / nullif(a.active_days, 0)             AS txns_per_active_day,
       coalesce(g.max_gap_hours, 0)                               AS max_gap_hours,
       coalesce(g.mean_gap_hours, 0)                              AS mean_gap_hours,
       a.balance_min, a.balance_max, a.balance_mean, a.balance_std,
       a.round_amount_ratio, a.sub_threshold_ratio,
       a.pct_cash, a.pct_upi, a.pct_wire, a.pct_atm, a.pct_international,
       coalesce(r.rapid_credits, 0) / a.txn_count                 AS rapid_credit_ratio,
       coalesce(r.rapid_amount, 0) / nullif(a.total_in, 0)        AS rapid_amount_ratio
FROM agg a
LEFT JOIN concentration c USING (account_id)
LEFT JOIN gaps          g USING (account_id)
LEFT JOIN rapid         r USING (account_id)
ORDER BY a.account_id
"""


def feature_names(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Column names of the feature matrix, excluding `account_id`."""
    conn.execute(f"SELECT * FROM ({FEATURE_SQL}) LIMIT 0")
    return [d[0] for d in conn.description][1:]


def extract(conn: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str], list[list[float]]]:
    """Compute features for every account.

    Returns (account_ids, feature_names, rows). Kept as plain Python lists rather
    than a DataFrame so the module carries no pandas dependency — the tournament
    converts to numpy once, at the point it actually needs it.
    """
    rows = conn.execute(FEATURE_SQL).fetchall()
    names = feature_names(conn)
    account_ids = [r[0] for r in rows]
    matrix = [[float(v) if v is not None else 0.0 for v in r[1:]] for r in rows]
    return account_ids, names, matrix
