"""The KPIs an FCC team actually argues about, computed rather than asserted.

Detection rate, false-positive rate, alert-to-SAR conversion and cost per alert
are the four numbers a financial-crime function reports upward, and until now
this project measured only the first two. The other two are operational: they
describe what the queue costs to work, not how good a detector is, and a stack
can look excellent on recall while being unaffordable to run.

    python -m launderlab metrics        # prints them; `charts` renders them

BOUNDARY: scorer-side, like `*/scoring.py` and `evaluate.py`. It reads ground
truth through `evaluate.dirty_accounts()` and the rules scorer rather than with
its own label query, so there stays one place per layer where the answer key is
consulted.

TWO HONESTY RULES BUILT INTO THE SHAPE OF THIS MODULE.

**1. Observed and hypothetical conversion never share a field.** Alert-to-SAR
conversion is the share of worked alerts that became a filing. It requires a
human to have worked them. In the demo world all 50 cases sit `open` with no
disposition, so the observed rate is *not measurable* -- and it is reported as
`None`, never as 0.0, because "nobody has reviewed these yet" and "everything
reviewed was cleared" are opposite facts that a zero would merge. What CAN be
computed is the ceiling: what conversion would be if every analyst decision were
perfect. That is a different number and carries a different name.

**2. The ceiling is exactly queue precision, and that identity is the point.**
If analysts never err, every case on a laundering account becomes a SAR and
every other case is cleared -- so conversion collapses into the precision of the
queue. Which means the KPI that FIUs track as a measure of *analyst* performance
is, at its ceiling, a measure of the *queue*. In production the two are tangled
and cannot be separated, because nobody knows which cleared alerts were mistakes.
Here ground truth exists, so the tangle can be shown rather than described.

COST. `reviews_per_true_find` needs no assumption at all -- it is a count over a
count, and it is the honest headline. Turning it into hours needs exactly one
input, `review_hours`, which is an ASSUMPTION about how long an analyst spends
on an alert and is named as one everywhere it appears. It is deliberately not
converted into money: that would need a loaded salary figure this project has no
business inventing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from launderlab.detect import rules
from launderlab.detect import scoring as rules_scoring
from launderlab.workbench import cases as case_store
from launderlab.workbench.evaluate import dirty_accounts

# An L1 alert review. An ASSUMPTION, not a measurement -- stated at every use so
# no reader mistakes it for something this project established.
DEFAULT_REVIEW_HOURS = 0.5

# "If the analyst only ever got through the top N of this queue." Reuses the
# alert-budget idea Phase 6 scored on and Phase 7 opened cases with.
DEFAULT_BUDGETS = (10, 25, 50, 100)


@dataclass(frozen=True)
class BudgetRow:
    """What the queue costs and returns if only its top `budget` are worked."""
    budget: int
    worked: int
    true_finds: int

    @property
    def precision(self) -> float:
        return self.true_finds / self.worked if self.worked else 0.0

    @property
    def reviews_per_true_find(self) -> float | None:
        """Alerts an analyst reads per real one. None if nothing real is in reach."""
        return self.worked / self.true_finds if self.true_finds else None

    def hours_per_true_find(self, review_hours: float = DEFAULT_REVIEW_HOURS
                            ) -> float | None:
        per = self.reviews_per_true_find
        return None if per is None else per * review_hours


@dataclass(frozen=True)
class Metrics:
    # --- detection quality, straight from the rules scorer
    recall: float
    precision: float
    false_positive_rate: float
    schemes_detected: int
    schemes_total: int
    by_typology: dict = field(default_factory=dict)

    # --- what reached an analyst
    cases_total: int = 0
    cases_on_dirty: int = 0

    # --- conversion. `observed_*` is None when nothing has been worked.
    cases_closed: int = 0
    sars_filed: int = 0
    observed_conversion: float | None = None

    # --- workload, at several budgets
    budgets: tuple[BudgetRow, ...] = ()

    @property
    def queue_precision(self) -> float:
        return self.cases_on_dirty / self.cases_total if self.cases_total else 0.0

    @property
    def ceiling_conversion(self) -> float:
        """Conversion if every analyst call were perfect — i.e. queue precision.

        Kept as its own property despite being identical: the equality is a
        finding, and a reader who sees only `queue_precision` will not notice
        that the industry's headline analyst KPI reduces to it.
        """
        return self.queue_precision

    @property
    def conversion_is_measurable(self) -> bool:
        return self.cases_closed > 0


def collect(conn: duckdb.DuckDBPyConnection, budgets: tuple[int, ...] = DEFAULT_BUDGETS,
            ) -> Metrics:
    """Compute every KPI from the world in `conn`."""
    report = rules_scoring.score(conn, rules.run_all(conn))
    dirty = dirty_accounts(conn)

    # Ranked exactly as the queue ranks them, so a budget here means the same
    # thing it means to an analyst working top-down.
    queue = case_store.queue(conn, status=None, limit=500)
    on_dirty = sum(1 for case in queue if case.account_id in dirty)

    closed = [c for c in queue if c.status == "closed" and c.disposition]
    sars = sum(1 for c in closed if c.disposition == "true_positive_sar")
    observed = (sars / len(closed)) if closed else None

    rows = []
    for budget in budgets:
        window = queue[:budget]
        rows.append(BudgetRow(
            budget=budget, worked=len(window),
            true_finds=sum(1 for c in window if c.account_id in dirty)))

    return Metrics(
        recall=report.overall_recall, precision=report.precision,
        false_positive_rate=report.false_positive_rate,
        schemes_detected=report.schemes_detected, schemes_total=report.schemes_total,
        by_typology=report.by_typology,
        cases_total=len(queue), cases_on_dirty=on_dirty,
        cases_closed=len(closed), sars_filed=sars, observed_conversion=observed,
        budgets=tuple(rows),
    )


def summary_lines(m: Metrics, review_hours: float = DEFAULT_REVIEW_HOURS) -> list[str]:
    """The dashboard as plain text — what the CLI prints and the page echoes."""
    out = [
        f"detection rate (schemes)   {m.recall:.1%}  "
        f"({m.schemes_detected}/{m.schemes_total} schemes)",
        f"alert precision            {m.precision:.1%}",
        f"false-positive rate        {m.false_positive_rate:.1%}",
        f"cases opened               {m.cases_total}  "
        f"({m.cases_on_dirty} on accounts genuinely in a scheme)",
        f"queue precision            {m.queue_precision:.1%}",
    ]
    if m.conversion_is_measurable:
        out.append(f"alert-to-SAR conversion    {m.observed_conversion:.1%}  "
                   f"observed, {m.sars_filed}/{m.cases_closed} closed cases")
    else:
        # Never 0.0: "unreviewed" and "reviewed and cleared" are opposite facts.
        # ASCII dash: this prints to a Windows console under cp1252, where an
        # em-dash renders as a replacement character on a launch-facing command.
        out.append("alert-to-SAR conversion    NOT MEASURABLE - no case has been "
                   "worked to a disposition")
    out.append(f"  ceiling if every call were perfect  {m.ceiling_conversion:.1%}  "
               f"(= queue precision, necessarily)")

    out.append("")
    out.append(f"workload by alert budget (review_hours={review_hours} is an ASSUMPTION):")
    for row in m.budgets:
        per = row.reviews_per_true_find
        if per is None:
            out.append(f"  top {row.budget:<4} {row.worked:>3} worked, "
                       f"no true find in reach")
            continue
        out.append(f"  top {row.budget:<4} {row.worked:>3} worked, "
                   f"{row.true_finds:>3} real  "
                   f"{per:.2f} reviews per true find  "
                   f"{row.hours_per_true_find(review_hours):.1f}h")
    return out


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    from launderlab.db.ledger import connect_configured

    conn = connect_configured()
    try:
        metrics = collect(conn)
    finally:
        conn.close()
    for line in summary_lines(metrics):
        print(line)
