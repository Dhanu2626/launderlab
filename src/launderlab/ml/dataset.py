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


def build_sequences(conn: duckdb.DuckDBPyConnection, account_ids: list[str],
                    length: int = 32):
    """Last `length` transactions per account, in order, as a 3-D array.

    Five channels per step: amount, direction (+1 credit / -1 debit), hours since
    the previous transaction, balance after, and whether it was cash. Shorter
    histories are left-padded with zeros so every account is the same shape.
    This is the input the flat feature vector throws away — the *order*.
    """
    import numpy as np

    rows = conn.execute(
        "SELECT account_id, ts, amount::DOUBLE, direction, balance_after::DOUBLE, channel"
        " FROM transactions ORDER BY account_id, ts, txn_id"
    ).fetchall()

    per_account: dict[str, list] = {}
    for account_id, ts, amount, direction, balance, channel in rows:
        per_account.setdefault(account_id, []).append((ts, amount, direction, balance, channel))

    index = {a: i for i, a in enumerate(account_ids)}
    out = np.zeros((len(account_ids), length, 5), dtype=np.float32)
    for account_id, history in per_account.items():
        i = index.get(account_id)
        if i is None:
            continue
        recent = history[-length:]
        for step, (ts, amount, direction, balance, channel) in enumerate(recent):
            gap = 0.0
            if step > 0:
                gap = (ts - recent[step - 1][0]).total_seconds() / 3600.0
            slot = length - len(recent) + step  # left-pad
            out[i, slot] = (amount, 1.0 if direction == "CR" else -1.0,
                            gap, balance, 1.0 if channel == "CASH" else 0.0)
    return out


def build_adjacency(conn: duckdb.DuckDBPyConnection, account_ids: list[str]):
    """Row-normalised neighbour matrix over the given accounts.

    Restricted to edges where BOTH ends are in this split, so a test account can
    never aggregate features from a training account. That costs the model some
    context — a genuinely inductive setup rather than the transductive full-graph
    one GNN papers usually assume — but it keeps train and test properly sealed.
    """
    import numpy as np

    from launderlab.graph.build import load_transfers

    index = {a: i for i, a in enumerate(account_ids)}
    adjacency = np.zeros((len(account_ids), len(account_ids)), dtype=np.float32)
    for transfer in load_transfers(conn):
        i, j = index.get(transfer.src), index.get(transfer.dst)
        if i is None or j is None:
            continue
        adjacency[i, j] = 1.0
        adjacency[j, i] = 1.0  # undirected: association matters both ways here

    degree = adjacency.sum(axis=1, keepdims=True)
    degree[degree == 0] = 1.0
    return adjacency / degree


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
