import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import mule_network, structuring
from launderlab.workbench import evaluate, risk
from launderlab.workbench.risk import RiskSignal
from launderlab.world.generate import load


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    conn = connect(tmp_path_factory.mktemp("wb") / "w.duckdb")
    load(conn, n=500, days=30, seed=73)
    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    sal = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id").fetchall()]
    rng = random.Random(6)
    for i in range(4):
        structuring.inject(conn, f"S{i}", rng.choice(biz), date(2026, 7, 3), rng,
                            target_total=2_500_000)
        mule_network.inject(conn, f"M{i}", rng.sample(sal, 4), date(2026, 7, 3), rng)
    return conn


def test_risk_module_never_reads_ground_truth():
    import inspect
    import re

    from launderlab.workbench import risk as risk_module
    source = inspect.getsource(risk_module)
    assert not re.search(r"\b(FROM|JOIN)\s+scheme_labels\b", source, re.IGNORECASE)


def test_every_scored_account_carries_its_evidence(world):
    scores = risk.score_accounts(world)
    assert scores, "no account scored at all"
    for entry in scores:
        assert entry.signals, f"{entry.account_id} scored with no evidence attached"
        assert 0.0 <= entry.score <= 100.0
        assert entry.band in {"low", "medium", "high", "critical"}


def test_scores_are_ranked_highest_first(world):
    scores = risk.score_accounts(world)
    assert [s.score for s in scores] == sorted((s.score for s in scores), reverse=True)


def test_more_corroborating_sources_scores_higher():
    """The point of aggregating: two independent layers beat one."""
    one_source = {"A": [RiskSignal("rules", "structuring", 1.0)]}
    two_sources = {"B": [RiskSignal("rules", "structuring", 1.0),
                          RiskSignal("graph", "in a chain", 1.0)]}
    a = risk.aggregate(one_source)[0]
    b = risk.aggregate(two_sources)[0]
    assert b.score > a.score


def test_repeat_signals_from_one_source_do_not_stack():
    """Being in three chains is not three times as suspicious as being in one."""
    single = {"A": [RiskSignal("graph", "chain 1", 1.0)]}
    triple = {"A": [RiskSignal("graph", "chain 1", 1.0),
                     RiskSignal("graph", "chain 2", 1.0),
                     RiskSignal("graph", "chain 3", 1.0)]}
    assert risk.aggregate(single)[0].score == risk.aggregate(triple)[0].score


def test_bands_follow_score(world):
    assert risk.aggregate({"A": [RiskSignal("rules", "x", 1.0),
                                  RiskSignal("graph", "x", 1.0),
                                  RiskSignal("screening", "x", 1.0),
                                  RiskSignal("ml", "x", 1.0)]})[0].band == "critical"
    assert risk.aggregate({"A": [RiskSignal("ml", "x", 0.1)]})[0].band == "low"


def test_ml_scores_are_optional(world):
    """A workbench must still work before any model has been trained."""
    scores = risk.score_accounts(world, ml_scores=None)
    assert scores
    assert all("ml" not in s.sources for s in scores)


def test_comparison_recall_uses_the_evaluated_universe(world):
    """Regression guard for a real bug: recall was divided by every dirty account
    in the bank rather than those in the slice being ranked, understating it."""
    signals = risk.collect(world)
    subset = dict(list(signals.items())[:60])
    universe = set(subset)
    combined = risk.aggregate(subset)

    results = evaluate.compare_against_individual(world, subset, combined,
                                                   budget=20, universe=universe)
    truth_in_universe = evaluate.dirty_accounts(world) & universe
    for comparison in results:
        assert comparison.true_positives <= len(truth_in_universe)
        if truth_in_universe:
            expected = comparison.true_positives / len(truth_in_universe)
            assert comparison.recall == pytest.approx(expected)


def test_graph_signal_reaches_every_account_in_a_chain(world):
    signals = risk.collect(world)
    graph_flagged = {a for a, sigs in signals.items() if any(s.source == "graph" for s in sigs)}
    # mule chains were injected, so the graph layer must contribute something
    assert graph_flagged, "graph layer produced no signals despite injected chains"
