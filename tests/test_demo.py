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
