import inspect

import pytest

from launderlab import demo


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Small but real: generate, inject, detect and open cases end to end."""
    path = tmp_path_factory.mktemp("demo") / "demo.duckdb"
    # two of each typology rather than the demo's 36 schemes: a structuring
    # injection costs ~4s, and the invariant under test is that the pipeline
    # composes into a non-empty queue, not how big the queue is.
    return demo.build(path, customers=180, days=14, seed=5,
                      mix={name: 2 for name in demo.SCHEME_MIX})


def test_the_demo_world_has_traffic_crime_and_a_queue_waiting(built):
    """The gap this closes: `run_detection` and the workbench both demoed as
    empty, because the only ledger anyone could build by hand was the 25-customer
    seed world with no schemes in it. A demo that shows nothing undersells every
    phase behind it."""
    assert built["accounts"] == 180
    assert built["transactions"] > 1000
    assert built["schemes"] >= 6, "all six typologies should have landed"
    assert built["cases"] > 0, "a workbench demo with an empty queue is the whole bug"


def test_the_demo_exercises_every_detection_layer_it_claims_to_combine(built):
    """The workbench exists to combine four layers. Until this was checked the
    demo world exercised two: nothing planted watchlist entities, so Phase 4's
    weight contributed nothing, and no ml scores were passed at all."""
    layers = built["layers"]
    assert built["entities"] > 0, "no watchlist entities planted - screening cannot fire"
    assert layers["rules"] > 0 and layers["graph"] > 0
    assert layers["screening"] > 0, "screening contributes nothing to any case"
    assert layers["ml"] > 0, "the model contributes nothing to any case"


def test_the_demo_never_fits_a_labelled_model_to_its_own_world(built):
    """There is one world in a demo, so a supervised model would score the very
    accounts it was fitted on and every training account would get a flattered
    number. An unsupervised model never sees a label, so fitting and scoring the
    same population leaks nothing."""
    from launderlab.ml import models

    import launderlab.demo as demo_module
    source = inspect.getsource(demo_module.unsupervised_ml_scores)
    assert "Isolation" in source
    assert not models.Isolation().needs_labels
    for supervised in ("GradientBoosting", "LSTM", "GraphSAGE"):
        assert supervised not in source


def test_ml_scores_are_a_budget_of_top_ranked_accounts_normalised_to_0_1(built):
    """`risk.collect` expects 0-1, and a model is used at an alert budget rather
    than against every account: scoring all 1,200 gave mid-ranked accounts ~7 free
    points and let them cross the opening threshold on nothing but "the model
    mildly dislikes you". Normalisation stays against the whole population, so a
    returned score means "this unusual relative to the bank", not to the budget."""
    from launderlab.db.ledger import connect

    from launderlab import demo as demo_module
    conn = connect(built["path"])
    top = demo_module.unsupervised_ml_scores(conn, budget=10)
    everything = demo_module.unsupervised_ml_scores(conn, budget=10_000)
    total_accounts = conn.execute("SELECT count(*) FROM accounts").fetchone()[0]
    conn.close()

    assert len(top) == 10
    assert len(everything) == total_accounts, "an unbounded budget should score the bank"
    assert all(0.0 <= v <= 1.0 for v in everything.values())
    assert max(everything.values()) == pytest.approx(1.0)
    assert min(everything.values()) == pytest.approx(0.0)

    # the budget must take the HIGHEST scorers, not an arbitrary slice
    ranked = sorted(everything, key=everything.get, reverse=True)[:10]
    assert set(top) == set(ranked)
    assert min(top.values()) >= max(
        v for account, v in everything.items() if account not in top)


def test_a_model_only_case_cannot_open_at_the_default_weights(built):
    """Measured, and reported rather than papered over: the ml weight is 0.15, so
    a model-only case tops out at 15.0 while cases open at 20.0. Tier 3 of the
    queue is therefore structurally unreachable, and the UI says so instead of
    letting an empty tier imply a quiet bank. Fixing it is a deliberate
    re-weighting decision, not a bug fix — and it matters most against a red team
    that has learned to evade the rules (Phase 8)."""
    from launderlab.workbench import risk

    ml_only_ceiling = risk.DEFAULT_WEIGHTS["ml"] * 100
    assert ml_only_ceiling < 20.0
    assert built["tiers"]["ml"] == 0, (
        "a case reached the model tier, so either the weights or the opening "
        "threshold changed and the UI's explanation of the empty tier is now wrong")
    # ...while screening, which used to fall through into that same tier and get
    # labelled "model-ranked", genuinely does open cases
    assert built["tiers"]["screening"] > 0


def test_the_queue_is_not_all_one_tier(built):
    """Tier 1 is graph evidence and Tier 2 is rule alerts. A demo world that
    produces only one kind teaches the wrong thing about the stack."""
    tiers = built["tiers"]
    assert tiers["graph"] > 0 and tiers["rules"] > 0


def test_it_refuses_to_overwrite_a_world_silently(built):
    """Someone may be mid-review on it — and the file is the whole investigation."""
    with pytest.raises(FileExistsError, match="already exists"):
        demo.build(built["path"], customers=60, days=7,
                   mix={"structuring": 1})

    replaced = demo.build(built["path"], customers=60, days=7, seed=3,
                          overwrite=True, mix={"structuring": 1})
    assert replaced["accounts"] == 60
