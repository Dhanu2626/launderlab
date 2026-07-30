"""Does adverse media belong in the laundering risk score? Measure, then decide.

Adverse media is the one screening leg that never reached a case. The obvious move
is to give it a weight and ship it. This module exists so that decision is made
from numbers, because there is a specific reason to expect it to FAIL and the
reason is not about implementation quality:

**Adverse media answers a different question from the one the score asks.** It
asks "is there negative news about this person?"; the risk score asks "is this
account laundering money?". Slice 7.1 already measured the same mismatch for
entity screening -- 0.250 precision for laundering risk, from a leg with 100%
recall at its own job. Media should be worse: Phase 4 measured 15.8% precision on
identity, and identity is the easier half.

So the experiment reports two different accuracies and refuses to conflate them:

  * **identity accuracy** -- is the article really about this customer?
    Scored against `media_labels` by `screening/scoring.py`. This is media's own
    job and it can be good at it.
  * **laundering accuracy** -- is the flagged account actually running a scheme?
    Scored against `scheme_labels`. This is what earning a weight requires.

WHAT DECIDES IT is not precision but the marginal trade: how many extra reviews an
analyst does per extra true positive found. A weighting that adds 14 reviews and
zero true positives is not "slightly worse precision", it is pure cost. That is
the false-positive economics thesis, measured on the one signal where the answer
was not obvious in advance.

Scorer-side module: allowed to read ground truth, like `evaluate.py`.

    python -m launderlab media-experiment [db]
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from launderlab.screening import engine as screening_engine
from launderlab.screening import scoring as screening_scoring
from launderlab.workbench import risk
from launderlab.workbench.evaluate import dirty_accounts

# Swept rather than guessed. 0.0 is the baseline (media collected but weightless)
# and doubles as a control: it must reproduce the shipped numbers exactly.
CANDIDATE_WEIGHTS = (0.05, 0.10, 0.15, 0.20)


@dataclass(frozen=True)
class Outcome:
    """One configuration's cost and benefit, at the alert budget an analyst has."""
    label: str
    media_weight: float
    threshold: float
    window_ok: bool          # did the case-opening threshold stay satisfiable?
    queue: int               # cases an analyst is asked to work
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    media_cases: int         # cases where media contributed any evidence
    media_only_cases: int    # cases NO other layer flagged -- media's real reach

    @property
    def reviews_per_true_positive(self) -> float:
        """Analyst workload: how many files opened to find one real case."""
        return self.queue / self.true_positives if self.true_positives else float("inf")


def _queue_for(scored: list[risk.RiskScore], threshold: float, budget: int) -> list[risk.RiskScore]:
    """The cases that would open: over threshold, capped by what a team can work."""
    return [entry for entry in scored if entry.score >= threshold][:budget]


def measure(conn: duckdb.DuckDBPyConnection, *, media_weight: float,
            signals: dict[str, list[risk.RiskSignal]], truth: set[str],
            budget: int, label: str | None = None) -> Outcome:
    """Score one configuration end to end and count what it costs."""
    if media_weight <= 0:
        weights = dict(risk.DEFAULT_WEIGHTS)
        threshold, quietest, ceiling = (risk.MIN_CASE_SCORE, None, None)
        window_ok = True
        if label is None:
            # baseline: drop media signals entirely rather than weighting them
            # zero, so the control is the shipped pipeline, not a near-miss of it
            active = {account: [s for s in sigs if s.source != risk.MEDIA_SOURCE]
                      for account, sigs in signals.items()}
            active = {a: v for a, v in active.items() if v}
            label = "baseline (no media)"
        else:
            # folded arm: media already rides the screening source, weights and
            # threshold both untouched
            active = signals
    else:
        weights = risk.weights_with_media(media_weight)
        threshold, quietest, ceiling = risk.derive_min_case_score(weights)
        window_ok = ceiling < threshold <= quietest
        active = signals
        label = f"media weight {media_weight:.2f}"

    scored = risk.aggregate(active, weights=weights)
    queue = _queue_for(scored, threshold, budget)
    queued_accounts = {entry.account_id for entry in queue}

    caught = queued_accounts & truth
    # In the folded arm media rides the screening source, so identify it by its
    # own wording rather than by source name -- otherwise the arm that matters
    # most would report zero media involvement and look like the baseline.
    def _is_media(signal) -> bool:
        return (signal.source == risk.MEDIA_SOURCE
                or signal.detail.startswith("adverse media"))

    media_cases = sum(1 for entry in queue if any(_is_media(s) for s in entry.signals))
    media_only = sum(1 for entry in queue if all(_is_media(s) for s in entry.signals))

    return Outcome(
        label=label, media_weight=media_weight, threshold=threshold, window_ok=window_ok,
        queue=len(queue), true_positives=len(caught),
        false_positives=len(queued_accounts) - len(caught),
        false_negatives=len(truth) - len(caught),
        precision=len(caught) / len(queue) if queue else 0.0,
        recall=len(caught) / len(truth) if truth else 0.0,
        media_cases=media_cases, media_only_cases=media_only,
    )


def identity_accuracy(conn: duckdb.DuckDBPyConnection) -> dict:
    """Media's accuracy at its OWN question, via the screening scorer.

    Reported next to the risk numbers so a bad result cannot be misread as "the
    media matcher is broken". It is usually right about the article and still
    useless for ranking laundering risk, and those are different sentences.
    """
    hits = screening_engine.screen_media(conn)
    report = screening_scoring.score_media(conn, hits)
    return {
        "hits": len(hits),
        "pairs": report.flagged_pairs,
        "precision": report.precision,
        "recall": report.recall,
        "true_positives": report.true_positives,
        "false_positives": report.false_positives,
    }


def tie_noise(conn: duckdb.DuckDBPyConnection, budget: int,
              ml_scores: dict[str, float] | None = None) -> dict:
    """How much of the queue's membership is decided by a coin toss.

    Every single-rule case scores exactly 0.35 x 0.60 = 21.00, so they pile onto
    one value -- and if the alert budget's cut lands inside that pile, which cases
    get worked is settled by the tie-break rather than by evidence. Measured and
    reported because it bounds how much any queue-level comparison can be trusted:
    it moved this experiment's own baseline by two true positives before ties were
    made deterministic, which is how it was found.
    """
    scored = risk.aggregate(risk.collect(conn, ml_scores, media_mode="off"))
    if len(scored) <= budget:
        return {"cut_score": None, "tied_at_cut": 0, "seats_at_cut": 0}
    cut = scored[budget - 1].score
    tied = [entry for entry in scored if entry.score == cut]
    above = sum(1 for entry in scored if entry.score > cut)
    return {"cut_score": cut, "tied_at_cut": len(tied), "seats_at_cut": budget - above}


def unique_reach(conn: duckdb.DuckDBPyConnection,
                 ml_scores: dict[str, float] | None = None) -> dict:
    """The set that decides the whole question, independent of any weighting.

    A signal can only add RECALL through accounts it flags that are genuinely
    dirty AND that no other layer already reaches. If that set is empty, no weight
    and no aggregation shape can extract value: the signal can only reorder the
    queue, and reordering a budget-capped queue can only displace. Worth computing
    directly rather than inferring it from four arms of a sweep.
    """
    signals = risk.collect(conn, ml_scores, media_mode="separate")
    truth = dirty_accounts(conn)
    with_media = {account for account, sigs in signals.items()
                  if any(s.source == risk.MEDIA_SOURCE for s in sigs)}
    without_media = {account for account, sigs in signals.items()
                     if any(s.source != risk.MEDIA_SOURCE for s in sigs)}
    return {
        "media_flagged": len(with_media),
        "media_flagged_and_dirty": len(with_media & truth),
        "only_media_finds": sorted(with_media & truth - without_media),
        "dirty_total": len(truth),
        "dirty_reachable_without_media": len(truth & without_media),
    }


def run(conn: duckdb.DuckDBPyConnection, budget: int = 50,
        ml_scores: dict[str, float] | None = None) -> tuple[list[Outcome], dict]:
    """Collect signals ONCE, then re-weight. Returns (outcomes, identity report).

    Collecting once matters: every configuration must see the identical evidence,
    or the comparison measures detector noise instead of the weighting.
    """
    separate = risk.collect(conn, ml_scores, media_mode="separate")
    folded = risk.collect(conn, ml_scores, media_mode="folded")
    truth = dirty_accounts(conn)

    outcomes = [measure(conn, media_weight=0.0, signals=separate, truth=truth,
                        budget=budget)]
    for weight in CANDIDATE_WEIGHTS:
        outcomes.append(measure(conn, media_weight=weight, signals=separate,
                                truth=truth, budget=budget))

    # The structural alternative: media under the screening source, so the two
    # identity legs cannot stack and the weights table is untouched. No weight to
    # sweep -- that is the point of it.
    outcomes.append(measure(conn, media_weight=0.0, signals=folded, truth=truth,
                            budget=budget, label="folded into screening"))
    return outcomes, identity_accuracy(conn)


def report(outcomes: list[Outcome], identity: dict, budget: int,
           reach: dict | None = None, ties: dict | None = None) -> str:
    """A table plus the marginal trade, which is the number that decides it."""
    base = outcomes[0]
    lines = [
        "ADVERSE MEDIA IN THE RISK SCORE - measured, not assumed",
        "=" * 78,
        "",
        f"Alert budget: {budget} cases. Ground truth: accounts in any injected scheme.",
        "",
        "Media at its OWN question (is the article about this customer?)",
        f"  {identity['pairs']} article-customer pairs flagged, "
        f"{identity['true_positives']} genuinely linked, "
        f"{identity['false_positives']} same-name-different-human",
        f"  precision {identity['precision']:.1%}, recall {identity['recall']:.1%}",
        "",
        f"{'configuration':<22} {'thr':>6} {'queue':>6} {'TP':>4} {'FP':>4} {'FN':>4} "
        f"{'prec':>7} {'recall':>7} {'rev/TP':>7} {'media':>6} {'only':>5}",
        "-" * 78,
    ]
    for outcome in outcomes:
        flag = "" if outcome.window_ok else "  <- threshold window UNSATISFIABLE"
        lines.append(
            f"{outcome.label:<22} {outcome.threshold:>6.1f} {outcome.queue:>6} "
            f"{outcome.true_positives:>4} {outcome.false_positives:>4} "
            f"{outcome.false_negatives:>4} {outcome.precision:>6.1%} "
            f"{outcome.recall:>6.1%} {outcome.reviews_per_true_positive:>7.2f} "
            f"{outcome.media_cases:>6} {outcome.media_only_cases:>5}{flag}")

    if ties is not None and ties["tied_at_cut"] > ties["seats_at_cut"]:
        lines += [
            "", "TIE NOISE - how far the queue numbers above can be trusted", "-" * 78,
            f"  The budget cut lands at score {ties['cut_score']:.2f}, where "
            f"{ties['tied_at_cut']} accounts are tied for {ties['seats_at_cut']} seats.",
            "  Every single-rule case scores 0.35 x 0.60 = 21.00 exactly, so they pile onto",
            "  one value and the tie-break decides who gets worked. Queue-level precision and",
            "  recall therefore carry several true positives of arbitrary noise, in EVERY arm.",
            "  The unique-reach result below does not depend on ties, on the budget, or on the",
            "  weighting - which is why the recommendation rests on it and not on the table.",
        ]

    if reach is not None:
        only = reach["only_media_finds"]
        lines += [
            "", "UNIQUE REACH - the fact that decides it regardless of weighting", "-" * 78,
            f"  {reach['media_flagged']} accounts carry an adverse-media signal; "
            f"{reach['media_flagged_and_dirty']} of them are actually laundering.",
            f"  Laundering accounts ONLY media finds: "
            f"{len(only)}{' -> ' + ', '.join(only) if only else '  (the empty set)'}",
            f"  {reach['dirty_reachable_without_media']} of {reach['dirty_total']} "
            f"laundering accounts are already reachable without media.",
            "",
            "  A signal adds recall only through accounts it alone reaches. With that set",
            "  empty, no weight and no aggregation shape can add a single true positive -",
            "  media can only reorder, and reordering a capped queue only displaces.",
        ]

    lines += ["", "MARGINAL TRADE against the baseline - the decision number", "-" * 78]
    for outcome in outcomes[1:]:
        d_queue = outcome.queue - base.queue
        d_tp = outcome.true_positives - base.true_positives
        cost = ("no extra reviews" if d_queue == 0 else
                f"{d_queue:+d} reviews for {d_tp:+d} true positives")
        verdict = ("no change to any figure" if d_queue == 0 and d_tp == 0 else
                   f"{d_queue / d_tp:.1f} extra reviews per extra find" if d_tp > 0 else
                   "pure cost - no true positive gained" if d_queue > 0 else
                   f"{-d_tp} true positive(s) LOST to displacement")
        lines.append(f"  {outcome.label:<22} {cost:<38} {verdict}")

    return "\n".join(lines)


def budget_sweep(conn: duckdb.DuckDBPyConnection,
                 budgets: tuple[int, ...] = (25, 50, 100, 200)) -> str:
    """Is the verdict an artefact of the alert budget? Answered, not assumed.

    A saturated queue can only reorder, so a signal that displaces real cases at
    one budget might genuinely add at a larger one. Running the sweep is the
    difference between "media is harmful" and "media is harmful at the budget I
    happened to pick".
    """
    lines = ["", "BUDGET SWEEP - ruling out a cap artefact", "-" * 78,
             f"{'budget':>7} {'configuration':<22} {'queue':>6} {'TP':>4} {'prec':>7} "
             f"{'recall':>7} {'rev/TP':>7} {'media-only':>11}"]
    for budget in budgets:
        outcomes, _identity = run(conn, budget=budget)
        for outcome in (outcomes[0], outcomes[3], outcomes[-1]):
            lines.append(
                f"{budget:>7} {outcome.label:<22} {outcome.queue:>6} "
                f"{outcome.true_positives:>4} {outcome.precision:>6.1%} "
                f"{outcome.recall:>6.1%} {outcome.reviews_per_true_positive:>7.2f} "
                f"{outcome.media_only_cases:>11}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    from pathlib import Path

    from launderlab.db.ledger import DEFAULT_DB_PATH, connect

    path = Path(argv[0]) if argv and not argv[0].startswith("-") else DEFAULT_DB_PATH
    budget = 50
    for arg in argv:
        if arg.startswith("--budget="):
            budget = int(arg.split("=", 1)[1])

    conn = connect(path)
    try:
        outcomes, identity = run(conn, budget=budget)
        text = report(outcomes, identity, budget, reach=unique_reach(conn),
                      ties=tie_noise(conn, budget))
        if "--no-sweep" not in argv:
            text += "\n" + budget_sweep(conn)
    finally:
        conn.close()
    print(text)
