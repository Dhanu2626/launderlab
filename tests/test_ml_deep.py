import random
from datetime import date

import numpy as np
import pytest

from launderlab.db.ledger import connect
from launderlab.ml import dataset, tournament
from launderlab.typology import dormant_reactivation, mule_network, shell_company, structuring
from launderlab.world.generate import load

deep = pytest.importorskip("launderlab.ml.deep",
                            reason="PyTorch not installed (pip install torch)")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    conn = connect(tmp_path_factory.mktemp("deep") / "w.duckdb")
    load(conn, n=600, days=30, seed=63)
    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    sal = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id").fetchall()]
    stu = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'student' ORDER BY account_id").fetchall()]
    rng = random.Random(5)
    for i in range(6):
        structuring.inject(conn, f"S{i}", rng.choice(biz), date(2026, 7, 3), rng)
        mule_network.inject(conn, f"M{i}", rng.sample(sal, 4), date(2026, 7, 3), rng)
        shell_company.inject(conn, f"H{i}", rng.choice(biz), date(2026, 7, 3), rng)
        dormant_reactivation.inject(conn, f"D{i}", rng.choice(stu), rng)
    return conn


@pytest.fixture(scope="module")
def splits(world):
    data = dataset.build(world)
    return dataset.split(data, seed=0)


def test_sequences_have_the_right_shape_and_are_ordered(world, splits):
    train, _ = splits
    seq = dataset.build_sequences(world, train.account_ids, length=32)
    assert seq.shape == (len(train), 32, deep.SEQUENCE_FEATURES)
    assert np.isfinite(seq).all()
    # direction channel must only ever be -1, 0 (padding) or +1
    assert set(np.unique(seq[:, :, 1])) <= {-1.0, 0.0, 1.0}


def test_sequences_are_left_padded_not_right_padded(world, splits):
    """Padding must sit BEFORE the history, so the final timestep is always the
    account's most recent transaction — that is the step the LSTM reads from."""
    train, _ = splits
    seq = dataset.build_sequences(world, train.account_ids, length=32)
    active = [i for i in range(len(train)) if seq[i].any()]
    assert active, "no account had any transactions"
    for i in active[:20]:
        assert seq[i, -1].any(), "last timestep is padding — history is right-padded"


def test_adjacency_is_row_normalised_over_a_symmetric_structure(world, splits):
    """Structure is undirected; the WEIGHTS deliberately are not.

    Row-normalising by degree is what turns neighbour aggregation into a mean
    rather than a sum — and it necessarily breaks numeric symmetry, because two
    connected accounts rarely have the same number of counterparties. So the
    check is that the edge *structure* is mutual while the weights are not.
    """
    train, _ = splits
    adj = dataset.build_adjacency(world, train.account_ids)
    assert adj.shape == (len(train), len(train))

    structure = adj > 0
    assert np.array_equal(structure, structure.T), "edges should be mutual"

    sums = adj.sum(axis=1)
    connected = sums > 0
    assert connected.any(), "no edges at all — adjacency is empty"
    assert np.allclose(sums[connected], 1.0), "rows must average, not accumulate"


def test_adjacency_never_links_across_the_split(world, splits):
    """A test account must not be able to aggregate a training account's features."""
    train, test = splits
    adj = dataset.build_adjacency(world, test.account_ids)
    assert adj.shape == (len(test), len(test))
    # containment is structural: the matrix is indexed only by this split's ids
    assert set(test.account_ids).isdisjoint(train.account_ids)


def test_lstm_learns_something_better_than_chance(world, splits):
    train, test = splits
    seq_train = dataset.build_sequences(world, train.account_ids)
    seq_test = dataset.build_sequences(world, test.account_ids)
    result = tournament.evaluate_prepared(
        deep.SequenceLSTM(epochs=10), seq_train, np.asarray(train.y), seq_test, test, budget=40)
    assert result.model == "lstm"
    assert result.roc_auc > 0.5, "a sequence model ranking worse than random is broken"
    assert 0.0 <= result.average_precision <= 1.0


def test_graphsage_learns_something_better_than_chance(world, splits):
    train, test = splits
    model = deep.GraphSAGE(epochs=40)
    model.set_adjacency(dataset.build_adjacency(world, train.account_ids))
    model.fit(np.asarray(train.X, float), np.asarray(train.y))
    model.set_adjacency(dataset.build_adjacency(world, test.account_ids))
    scores = model.score(np.asarray(test.X, float))

    from sklearn.metrics import roc_auc_score
    assert len(scores) == len(test)
    assert np.isfinite(scores).all()
    assert roc_auc_score(test.y, scores) > 0.5


def test_deep_models_are_deterministic(world, splits):
    train, test = splits
    seq_train = dataset.build_sequences(world, train.account_ids)
    seq_test = dataset.build_sequences(world, test.account_ids)

    def run():
        model = deep.SequenceLSTM(epochs=5)
        model.fit(seq_train, np.asarray(train.y))
        return model.score(seq_test)

    assert np.allclose(run(), run()), "seeded training must reproduce exactly"
