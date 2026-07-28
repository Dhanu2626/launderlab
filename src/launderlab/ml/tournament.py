"""Run every model against the same data and rank them.

SCORED AT AN ALERT BUDGET, not at an arbitrary threshold. A bank does not ask
"what is your F1 at 0.5"; it asks "we can investigate 100 accounts this month —
how many of them are real?" That framing is also the only fair way to compare a
supervised classifier's calibrated probability against an autoencoder's
reconstruction error, since the two live on completely different scales. Ranking
is all they have in common, so ranking is what gets measured.

Threshold-free metrics are reported alongside: average precision (PR-AUC) rather
than ROC-AUC as the headline, because with a 2-3% positive rate ROC-AUC flatters
everything — a model can look excellent while its top alerts are mostly noise.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from launderlab.ml.dataset import Dataset
from launderlab.ml.models import Model, default_zoo

DEFAULT_BUDGET = 100


@dataclass(frozen=True)
class Result:
    model: str
    paradigm: str
    average_precision: float
    roc_auc: float
    precision_at_budget: float
    recall_at_budget: float
    true_positives_at_budget: int
    budget: int
    fit_seconds: float
    by_typology: dict = field(default_factory=dict)  # typology -> (caught, total)


def _at_budget(scores: np.ndarray, y: np.ndarray, budget: int) -> tuple[int, np.ndarray]:
    """Indices of the `budget` highest-scoring accounts, and how many are real."""
    budget = min(budget, len(scores))
    top = np.argsort(-scores)[:budget]
    return int(y[top].sum()), top


def evaluate(model: Model, train: Dataset, test: Dataset,
             budget: int = DEFAULT_BUDGET,
             typologies: dict[str, set[str]] | None = None) -> Result:
    """Fit on train, score test, measure. Test labels are touched only after fitting."""
    X_train = np.asarray(train.X, dtype=float)
    y_train = np.asarray(train.y, dtype=int)
    X_test = np.asarray(test.X, dtype=float)
    y_test = np.asarray(test.y, dtype=int)

    started = time.perf_counter()
    model.fit(X_train, y_train)
    fit_seconds = time.perf_counter() - started

    scores = np.asarray(model.score(X_test), dtype=float)
    caught, top_idx = _at_budget(scores, y_test, budget)
    total_positive = int(y_test.sum())

    by_typology: dict[str, tuple[int, int]] = {}
    if typologies:
        flagged = {test.account_ids[i] for i in top_idx}
        totals: dict[str, int] = {}
        hits: dict[str, int] = {}
        for account_id, label in zip(test.account_ids, y_test):
            if not label:
                continue
            for typology in typologies.get(account_id, set()):
                totals[typology] = totals.get(typology, 0) + 1
                if account_id in flagged:
                    hits[typology] = hits.get(typology, 0) + 1
        by_typology = {t: (hits.get(t, 0), n) for t, n in sorted(totals.items())}

    return Result(
        model=model.name,
        paradigm=model.paradigm,
        average_precision=float(average_precision_score(y_test, scores)),
        roc_auc=float(roc_auc_score(y_test, scores)),
        precision_at_budget=caught / min(budget, len(scores)),
        recall_at_budget=caught / total_positive if total_positive else 0.0,
        true_positives_at_budget=caught,
        budget=min(budget, len(scores)),
        fit_seconds=fit_seconds,
        by_typology=by_typology,
    )


def run(train: Dataset, test: Dataset, models: list[Model] | None = None,
        budget: int = DEFAULT_BUDGET,
        typologies: dict[str, set[str]] | None = None) -> list[Result]:
    """Full leaderboard, best average precision first."""
    models = models if models is not None else default_zoo()
    results = [evaluate(m, train, test, budget, typologies) for m in models]
    return sorted(results, key=lambda r: r.average_precision, reverse=True)


def evaluate_prepared(model: Model, X_train, y_train, X_test, test: Dataset,
                      budget: int = DEFAULT_BUDGET,
                      typologies: dict[str, set[str]] | None = None) -> Result:
    """Score a model whose inputs are already shaped for it.

    The LSTM takes a 3-D sequence tensor and GraphSAGE needs its adjacency set
    beforehand, so neither can go through `evaluate()`'s flat-matrix path. The
    measurement afterwards is identical, which is what keeps the leaderboard
    comparable across all six families.
    """
    started = time.perf_counter()
    model.fit(X_train, y_train)
    fit_seconds = time.perf_counter() - started

    scores = np.asarray(model.score(X_test), dtype=float)
    y_test = np.asarray(test.y, dtype=int)
    caught, top_idx = _at_budget(scores, y_test, budget)
    total_positive = int(y_test.sum())

    by_typology: dict[str, tuple[int, int]] = {}
    if typologies:
        flagged = {test.account_ids[i] for i in top_idx}
        totals: dict[str, int] = {}
        hits: dict[str, int] = {}
        for account_id, label in zip(test.account_ids, y_test):
            if not label:
                continue
            for typology in typologies.get(account_id, set()):
                totals[typology] = totals.get(typology, 0) + 1
                if account_id in flagged:
                    hits[typology] = hits.get(typology, 0) + 1
        by_typology = {t: (hits.get(t, 0), n) for t, n in sorted(totals.items())}

    return Result(
        model=model.name, paradigm=model.paradigm,
        average_precision=float(average_precision_score(y_test, scores)),
        roc_auc=float(roc_auc_score(y_test, scores)),
        precision_at_budget=caught / min(budget, len(scores)),
        recall_at_budget=caught / total_positive if total_positive else 0.0,
        true_positives_at_budget=caught, budget=min(budget, len(scores)),
        fit_seconds=fit_seconds, by_typology=by_typology,
    )
