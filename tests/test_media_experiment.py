import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.screening import inject as screening_inject
from launderlab.typology import mule_network, structuring
from launderlab.workbench import media_experiment as mx
from launderlab.workbench import risk
from launderlab.world.generate import load


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "w.duckdb"
    conn = connect(path)
    load(conn, n=300, days=21, seed=23)
    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    retail = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id").fetchall()]
    rng = random.Random(9)
    for i in range(2):
        structuring.inject(conn, f"S{i}", rng.choice(biz), date(2026, 7, 3), rng,
                           target_total=2_600_000)
        mule_network.inject(conn, f"M{i}", rng.sample(retail, 4), date(2026, 7, 3), rng)
    screening_inject.inject_entities(conn, rng, n=8)
    screening_inject.inject_adverse_media(conn, rng)
    yield conn
    conn.close()


def test_media_is_off_by_default_so_the_benchmark_cannot_move(world):
    """The whole point of a measurement slice: turning a candidate signal on must
    be a deliberate act, or every figure the earlier phases published shifts
    underneath them without anyone choosing that."""
    default = risk.score_accounts(world)
    explicit_off = risk.score_accounts(world, media_mode="off")
    assert [(s.account_id, s.score) for s in default] \
        == [(s.account_id, s.score) for s in explicit_off]
    assert risk.MEDIA_SOURCE not in risk.DEFAULT_WEIGHTS
    assert all(s.source != risk.MEDIA_SOURCE
               for entry in default for s in entry.signals)


def test_media_modes_place_the_signal_where_they_claim(world):
    separate = risk.collect(world, None, media_mode="separate")
    folded = risk.collect(world, None, media_mode="folded")

    assert any(s.source == risk.MEDIA_SOURCE
               for sigs in separate.values() for s in sigs)
    # folded: media rides the screening source so the two identity legs cannot
    # stack -- `aggregate` keeps only the strongest signal within a source
    assert not any(s.source == risk.MEDIA_SOURCE
                   for sigs in folded.values() for s in sigs)
    assert any(s.source == "screening" and s.detail.startswith("adverse media")
               for sigs in folded.values() for s in sigs)

    with pytest.raises(ValueError, match="media_mode"):
        risk.collect(world, None, media_mode="sometimes")


def test_ranking_is_deterministic_so_a_capped_queue_is_reproducible(world):
    """45 accounts tie at exactly 21.00 on the demo world and the alert budget's
    cut lands inside that cluster, so before ties broke on account id the queue's
    membership -- and this experiment's own baseline -- moved between identical
    runs. That is how the flaw was found."""
    first = [s.account_id for s in risk.score_accounts(world)]
    second = [s.account_id for s in risk.score_accounts(world)]
    assert first == second

    scored = risk.score_accounts(world)
    for earlier, later in zip(scored, scored[1:]):
        assert (earlier.score > later.score
                or (earlier.score == later.score
                    and earlier.account_id < later.account_id))


def test_renormalised_candidate_weights_still_sum_to_one(world):
    for weight in mx.CANDIDATE_WEIGHTS:
        weights = risk.weights_with_media(weight)
        assert sum(weights.values()) == pytest.approx(1.0)
        assert weights[risk.MEDIA_SOURCE] > 0
        # every other layer shrinks, which is exactly why the threshold has to be
        # re-derived rather than assumed to still be 17.5
        assert weights["screening"] < risk.DEFAULT_WEIGHTS["screening"]
        threshold, quietest, ceiling = risk.derive_min_case_score(weights)
        assert threshold <= quietest
        assert ceiling == pytest.approx(weights["ml"] * 100, abs=0.01)  # reported to 2dp


def test_the_experiment_reports_a_baseline_and_every_candidate(world):
    outcomes, identity = mx.run(world, budget=20)
    labels = [o.label for o in outcomes]
    assert labels[0] == "baseline (no media)"
    assert labels[-1] == "folded into screening"
    assert len(outcomes) == len(mx.CANDIDATE_WEIGHTS) + 2
    assert identity["pairs"] >= 0

    text = mx.report(outcomes, identity, 20, reach=mx.unique_reach(world),
                     ties=mx.tie_noise(world, 20))
    assert "UNIQUE REACH" in text and "MARGINAL TRADE" in text


def test_unique_reach_is_what_the_recommendation_rests_on(world):
    """A signal adds recall only through accounts it alone reaches. This is the
    one measurement that does not depend on the weighting, the alert budget or the
    tie-break -- so it is the one the decision is made from."""
    reach = mx.unique_reach(world)
    assert reach["dirty_total"] > 0
    assert reach["media_flagged"] > 0, "fixture should plant media that matches someone"
    assert isinstance(reach["only_media_finds"], list)
    # measured on the demo world as empty; if a world ever makes it non-empty the
    # recommendation genuinely changes and this test should be read, not deleted
    assert reach["dirty_reachable_without_media"] <= reach["dirty_total"]


def test_media_never_reaches_the_score_through_a_case(world):
    """The production decision: surfaced on the entity screen, absent from ranking."""
    for entry in risk.score_accounts(world):
        for signal in entry.signals:
            assert signal.source != risk.MEDIA_SOURCE
            assert not signal.detail.startswith("adverse media")
