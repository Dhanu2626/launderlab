"""Score a rules engine's alerts against ground truth.

This is the ONLY module in the detection stack allowed to read scheme_labels —
rules.py must never see it. Scoring is the answer key; detection is the exam.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import duckdb

from launderlab.detect.rules import Alert


@dataclass(frozen=True)
class ScoreReport:
    total_alerts: int
    true_positive_accounts: int
    false_positive_accounts: int
    precision: float
    false_positive_rate: float
    schemes_detected: int
    schemes_total: int
    overall_recall: float
    by_typology: dict = field(default_factory=dict)  # typology -> (detected, total)


def score(conn: duckdb.DuckDBPyConnection, alerts: list[Alert]) -> ScoreReport:
    """Compare `alerts` (account-level) against every injected scheme's ground
    truth. An alert counts as a true positive if its account is involved in ANY
    injected scheme — we're scoring "did this catch something dirty," not "did it
    guess the exact typology," which matches how a real analyst reads an alert.
    """
    alert_accounts = {a.account_id for a in alerts}

    scheme_rows = conn.execute(
        "SELECT DISTINCT t.account_id, l.scheme_id, l.typology"
        " FROM scheme_labels l JOIN transactions t USING (txn_id)"
    ).fetchall()

    scheme_accounts: dict[str, set[str]] = defaultdict(set)
    scheme_typology: dict[str, str] = {}
    for account_id, scheme_id, typology in scheme_rows:
        scheme_accounts[scheme_id].add(account_id)
        scheme_typology[scheme_id] = typology

    detected_schemes = {sid for sid, accts in scheme_accounts.items() if accts & alert_accounts}

    by_typology: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for sid, typology in scheme_typology.items():
        by_typology[typology][1] += 1
        if sid in detected_schemes:
            by_typology[typology][0] += 1

    all_dirty_accounts = set().union(*scheme_accounts.values()) if scheme_accounts else set()
    true_positive_accounts = alert_accounts & all_dirty_accounts
    false_positive_accounts = alert_accounts - all_dirty_accounts

    n_alerts = len(alert_accounts)
    precision = len(true_positive_accounts) / n_alerts if n_alerts else 0.0
    fp_rate = len(false_positive_accounts) / n_alerts if n_alerts else 0.0
    recall = len(detected_schemes) / len(scheme_accounts) if scheme_accounts else 0.0

    return ScoreReport(
        total_alerts=n_alerts,
        true_positive_accounts=len(true_positive_accounts),
        false_positive_accounts=len(false_positive_accounts),
        precision=precision,
        false_positive_rate=fp_rate,
        schemes_detected=len(detected_schemes),
        schemes_total=len(scheme_accounts),
        overall_recall=recall,
        by_typology={t: (d, total) for t, (d, total) in by_typology.items()},
    )
