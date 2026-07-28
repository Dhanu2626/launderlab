"""Assemble the labelled dataset and split it honestly.

THE BOUNDARY CHANGES HERE, AND IT IS WORTH BEING PRECISE ABOUT WHY.

Phases 3-5 held an absolute line: detection code never reads `scheme_labels`.
Supervised learning cannot hold that line — a classifier has to be shown labelled
examples or it is not a classifier. That is not cheating, and it mirrors reality:
a real bank trains its models on **historical confirmed SARs**, cases that human
investigators already adjudicated. The labels exist; they just came from the past
rather than from an oracle.

So the integrity requirement is not label-blindness, it is **no test-set leakage**:

  * labels for the TRAINING accounts may be used to fit supervised models
  * labels for the TEST accounts are used only to score, never to fit
  * unsupervised models (isolation forest, one-class SVM, autoencoder) never see
    `y` at all, not even in training — which is exactly why banks like them:
    they need no labelled history to start working

`split()` below enforces the first two by construction, returning train and test
as separate objects so a model physically cannot reach the test labels while
fitting.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import duckdb

from launderlab.ml import features


@dataclass(frozen=True)
class Dataset:
    account_ids: list[str]
    feature_names: list[str]
    X: list[list[float]]
    y: list[int]

    def __len__(self) -> int:
        return len(self.y)

    @property
    def positives(self) -> int:
        return sum(self.y)


def build(conn: duckdb.DuckDBPyConnection) -> Dataset:
    """Feature matrix plus a binary label per account.

    An account is positive when it carries at least one transaction belonging to
    any injected scheme — the question a model is being asked is "is this account
    involved in laundering", not "which typology", which keeps the target the same
    across all six model families.
    """
    account_ids, names, X = features.extract(conn)

    dirty = {
        row[0] for row in conn.execute(
            "SELECT DISTINCT t.account_id FROM scheme_labels l"
            " JOIN transactions t USING (txn_id)"
        ).fetchall()
    }
    y = [1 if account_id in dirty else 0 for account_id in account_ids]
    return Dataset(account_ids=account_ids, feature_names=names, X=X, y=y)


def split(data: Dataset, test_fraction: float = 0.3, seed: int = 0) -> tuple[Dataset, Dataset]:
    """Stratified train/test split.

    Stratified because the positive class is rare (a few percent). A plain random
    split can hand one side almost no positives, which would make the resulting
    scores an artefact of the split rather than of the models.
    """
    rng = random.Random(seed)
    positives = [i for i, label in enumerate(data.y) if label == 1]
    negatives = [i for i, label in enumerate(data.y) if label == 0]
    rng.shuffle(positives)
    rng.shuffle(negatives)

    def carve(indices: list[int]) -> tuple[list[int], list[int]]:
        cut = int(len(indices) * test_fraction)
        return indices[cut:], indices[:cut]

    train_pos, test_pos = carve(positives)
    train_neg, test_neg = carve(negatives)
    train_idx = sorted(train_pos + train_neg)
    test_idx = sorted(test_pos + test_neg)

    def subset(indices: list[int]) -> Dataset:
        return Dataset(
            account_ids=[data.account_ids[i] for i in indices],
            feature_names=data.feature_names,
            X=[data.X[i] for i in indices],
            y=[data.y[i] for i in indices],
        )

    return subset(train_idx), subset(test_idx)


def typology_map(conn: duckdb.DuckDBPyConnection) -> dict[str, set[str]]:
    """account_id -> the typologies it participates in, for per-typology recall.

    Scorer-side only: used to break a model's recall down by crime type after the
    fact, never to train.
    """
    mapping: dict[str, set[str]] = {}
    for account_id, typology in conn.execute(
        "SELECT DISTINCT t.account_id, l.typology FROM scheme_labels l"
        " JOIN transactions t USING (txn_id)"
    ).fetchall():
        mapping.setdefault(account_id, set()).add(typology)
    return mapping
