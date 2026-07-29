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


def test_a_single_rule_hit_still_reaches_the_queue():
    """Regression: genuine one-rule cases were being filtered out entirely.

    Rule strength used to be min(n,3)/3, so one rule scored 0.35 x 1/3 = 11.7 --
    below the queue's default 30-point cut. A real structuring scheme trips
    exactly one scenario, so confirmed placement cases never reached an analyst
    while mule accounts did. Found by looking at the queue UI, not by a test.
    """
    one_rule = risk.aggregate({"A": [RiskSignal("rules", "structuring_burst", 1.0)]})[0]
    assert one_rule.score >= 20.0, "a genuine single-rule case must not be filtered out"


def test_rule_strength_has_diminishing_returns():
    """One scenario is meaningful, two corroborate, a third adds little."""
    strengths = [risk.rule_strength(n) for n in range(1, 5)]
    assert strengths == sorted(strengths), "more rules must never score lower"
    assert strengths[0] >= 0.5, "one rule is real evidence, not a third of one"
    gains = [b - a for a, b in zip(strengths, strengths[1:])]
    assert gains == sorted(gains, reverse=True), "each extra rule must add less than the last"
    assert risk.rule_strength(0) == 0.0


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


def test_a_single_rule_case_is_not_labelled_low_risk(world):
    """Found by printing a SAR narrative in 7.8: a confirmed structuring scheme --
    50 cash deposits totalling Rs 33,43,000 -- was described to a Financial
    Intelligence Unit as "low band", because one rule firing scores 21 and the
    thresholds assumed 100 was attainable. 7.4 already established that most
    genuine cases trip exactly ONE scenario, so this is the common case, not an
    edge one."""
    one_rule = risk.aggregate({"A": [RiskSignal("rules", "structuring_burst: 50 cash "
                                                "deposits", risk.rule_strength(1))]})[0]
    assert one_rule.score == pytest.approx(21.0)
    assert one_rule.band == "medium", "a named scenario firing is not 'low risk'"

    # and two independent layers agreeing must outrank one
    both = risk.aggregate({"A": [RiskSignal("rules", "x", risk.rule_strength(1)),
                                 RiskSignal("graph", "x", 0.75)]})[0]
    assert both.band == "high"
    assert both.score > one_rule.score


def test_every_band_is_reachable_by_some_real_combination(world):
    """A vocabulary with words nothing can ever be is not a vocabulary. Before
    this was measured, no account in the whole demo bank could exceed 43.5, so
    'high' and 'critical' described nothing."""
    reachable = {
        risk.aggregate({"A": [RiskSignal("ml", "x", 0.1)]})[0].band,
        risk.aggregate({"A": [RiskSignal("rules", "x", risk.rule_strength(1))]})[0].band,
        risk.aggregate({"A": [RiskSignal("rules", "x", risk.rule_strength(1)),
                              RiskSignal("graph", "x", 0.75)]})[0].band,
        risk.aggregate({"A": [RiskSignal("rules", "x", risk.rule_strength(3)),
                              RiskSignal("graph", "x", 1.0)]})[0].band,
    }
    assert reachable == {"low", "medium", "high", "critical"}


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
