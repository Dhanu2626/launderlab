"""Does aggregating actually beat the best single detector?

Scorer-side: the only module in the workbench allowed to read `scheme_labels`.

Aggregation is usually assumed to help. It does not have to. If combining four
layers ranks no better than whichever layer was already best, the combination is
adding a formula, a weights table and an explanation burden for nothing — and it
is worth finding that out with a measurement rather than an assumption.

Scored at an alert budget, matching Phase 6: a bank asks "of the N accounts we
can investigate, how many are real?", not "what is your AUC".
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from launderlab.workbench.risk import RiskScore, RiskSignal, aggregate


@dataclass(frozen=True)
class Comparison:
    strategy: str
    flagged: int
    true_positives: int
    precision: float
    recall: float


def dirty_accounts(conn: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT DISTINCT t.account_id FROM scheme_labels l"
            " JOIN transactions t USING (txn_id)"
        ).fetchall()
    }


def _measure(strategy: str, ranked: list[str], truth: set[str], budget: int) -> Comparison:
    top = ranked[:budget]
    caught = len(set(top) & truth)
    return Comparison(
        strategy=strategy,
        flagged=len(top),
        true_positives=caught,
        precision=caught / len(top) if top else 0.0,
        recall=caught / len(truth) if truth else 0.0,
    )


def compare_against_individual(conn: duckdb.DuckDBPyConnection,
                               signals: dict[str, list[RiskSignal]],
                               combined: list[RiskScore],
                               budget: int = 100,
                               universe: set[str] | None = None) -> list[Comparison]:
    """Rank by the combined score, and by each source alone, then compare.

    Each single-source ranking uses only that source's strongest signal per
    account — exactly what a bank running just that one layer would see.

    `universe` restricts the recall denominator to the accounts actually being
    ranked. Without it, evaluating a held-out slice divides by every dirty
    account in the whole bank and reports a recall far below the truth — a bug
    this function had until it was measured against a known-26-positive split.
    """
    truth = dirty_accounts(conn)
    if universe is not None:
        truth &= universe
    results = [_measure("combined", [r.account_id for r in combined], truth, budget)]

    sources = {s.source for account_signals in signals.values() for s in account_signals}
    for source in sorted(sources):
        single = {
            account_id: [s for s in account_signals if s.source == source]
            for account_id, account_signals in signals.items()
        }
        single = {a: v for a, v in single.items() if v}
        ranked = [r.account_id for r in aggregate(single, weights={source: 1.0})]
        results.append(_measure(source, ranked, truth, budget))

    return sorted(results, key=lambda c: c.precision, reverse=True)
