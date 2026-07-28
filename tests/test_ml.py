import random
from datetime import date

import numpy as np
import pytest

from launderlab.db.ledger import connect
from launderlab.ml import dataset, features, models, tournament
from launderlab.typology import (
    dormant_reactivation,
    high_risk_geography,
    mule_network,
    round_tripping,
    shell_company,
    structuring,
)
from launderlab.world.generate import load


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    conn = connect(tmp_path_factory.mktemp("ml") / "w.duckdb")
    load(conn, n=800, days=30, seed=61)
    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    sal = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id").fetchall()]
    stu = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'student' ORDER BY account_id").fetchall()]
    rng = random.Random(4)
    for i in range(5):
        structuring.inject(conn, f"S{i}", rng.choice(biz), date(2026, 7, 3), rng)
        mule_network.inject(conn, f"M{i}", rng.sample(sal, 4), date(2026, 7, 3), rng)
        shell_company.inject(conn, f"H{i}", rng.choice(biz), date(2026, 7, 3), rng)
        round_tripping.inject(conn, f"R{i}", rng.choice(biz), date(2026, 7, 1), rng)
        dormant_reactivation.inject(conn, f"D{i}", rng.choice(stu), rng)
        high_risk_geography.inject(conn, f"G{i}", rng.choice(biz), date(2026, 7, 3), rng)
    return conn


def test_features_never_read_ground_truth():
    # same boundary as every other detection layer: features describe behaviour,
    # they must not encode the answer
    import inspect
    import re

    from launderlab.ml import features as features_module
    source = inspect.getsource(features_module)
    assert not re.search(r"\b(FROM|JOIN)\s+scheme_labels\b", source, re.IGNORECASE)


def test_every_account_gets_a_complete_feature_vector(world):
    ids, names, X = features.extract(world)
    accounts = world.execute("SELECT count(DISTINCT account_id) FROM transactions").fetchone()[0]
    assert len(ids) == accounts
    assert all(len(row) == len(names) for row in X)
    assert all(all(np.isfinite(v) for v in row) for row in X), "NaN/inf would break every model"


def test_dataset_labels_match_ground_truth(world):
    data = dataset.build(world)
    dirty = {r[0] for r in world.execute(
        "SELECT DISTINCT t.account_id FROM scheme_labels l JOIN transactions t USING (txn_id)"
    ).fetchall()}
    labelled = {a for a, y in zip(data.account_ids, data.y) if y == 1}
    assert labelled == dirty
    assert 0 < data.positives < len(data), "need both classes to learn anything"


def test_split_is_stratified_and_disjoint(world):
    data = dataset.build(world)
    train, test = dataset.split(data, test_fraction=0.3, seed=0)

    assert set(train.account_ids).isdisjoint(test.account_ids)
    assert len(train) + len(test) == len(data)
    # both sides must carry positives, or the score is an artefact of the split
    assert train.positives > 0 and test.positives > 0
    train_rate = train.positives / len(train)
    test_rate = test.positives / len(test)
    assert abs(train_rate - test_rate) < 0.02


def test_split_is_deterministic(world):
    data = dataset.build(world)
    a, _ = dataset.split(data, seed=7)
    b, _ = dataset.split(data, seed=7)
    assert a.account_ids == b.account_ids


def test_unsupervised_models_never_use_labels(world):
    """The claim "these need no labelled history" has to be literally true."""
    data = dataset.build(world)
    train, test = dataset.split(data, seed=0)
    X_train = np.asarray(train.X, dtype=float)
    X_test = np.asarray(test.X, dtype=float)

    for model in (models.Isolation(), models.OneClass(), models.Autoencoder()):
        assert model.needs_labels is False
        # fitting with labels withheld entirely must still work
        model.fit(X_train, None)
        scores = model.score(X_test)
        assert len(scores) == len(test)
        assert all(np.isfinite(s) for s in scores)


def test_every_model_produces_a_usable_ranking(world):
    data = dataset.build(world)
    train, test = dataset.split(data, seed=0)
    results = tournament.run(train, test, budget=40,
                              typologies=dataset.typology_map(world))

    assert len(results) == len(models.default_zoo())
    for r in results:
        assert 0.0 <= r.average_precision <= 1.0
        assert 0.0 <= r.roc_auc <= 1.0
        assert 0 <= r.true_positives_at_budget <= r.budget
        # a ranking worse than chance means the score is inverted somewhere
        assert r.roc_auc > 0.5, f"{r.model} ranks worse than random"


def test_leaderboard_is_sorted_by_average_precision(world):
    data = dataset.build(world)
    train, test = dataset.split(data, seed=0)
    results = tournament.run(train, test, budget=40)
    scores = [r.average_precision for r in results]
    assert scores == sorted(scores, reverse=True)


def test_supervised_model_beats_unsupervised_on_this_data(world):
    """Not a law of nature — a sanity check that labels are worth something.

    If a supervised model trained on labelled history could not beat detectors
    that never saw a label, something would be wrong with the features or the
    split rather than with the models.
    """
    data = dataset.build(world)
    train, test = dataset.split(data, seed=0)
    results = {r.model: r for r in tournament.run(train, test, budget=40)}
    supervised = results["gradient_boosting"].average_precision
    best_unsupervised = max(r.average_precision for r in results.values()
                            if r.paradigm == "unsupervised")
    assert supervised > best_unsupervised
