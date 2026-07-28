import random

import pytest

from launderlab.db.ledger import connect
from launderlab.screening import engine, inject, scoring
from launderlab.world.generate import load


@pytest.fixture(scope="module")
def screened_world(tmp_path_factory):
    """One world with entities and media planted — every test here only reads."""
    conn = connect(tmp_path_factory.mktemp("scr") / "w.duckdb")
    load(conn, n=500, days=20, seed=11)
    rng = random.Random(3)
    inject.inject_entities(conn, rng, n=12)
    inject.inject_adverse_media(conn, rng, n_true=8, n_trap=8, n_benign=15)
    return conn


def test_engine_never_reads_ground_truth():
    # same boundary the rules engine has: screening earns its hits from names
    # alone. Checks real SQL references, not the word in explanatory docstrings.
    import inspect
    import re

    from launderlab.screening import engine as engine_module
    from launderlab.screening import matcher as matcher_module

    for module in (engine_module, matcher_module):
        source = inspect.getsource(module)
        assert not re.search(r"\b(FROM|JOIN)\s+entity_labels\b", source, re.IGNORECASE)
        assert not re.search(r"\b(FROM|JOIN)\s+media_labels\b", source, re.IGNORECASE)


def test_every_planted_entity_is_found(screened_world):
    hits = engine.screen_customers(screened_world)
    report = scoring.score_entities(screened_world, hits)
    assert report.false_negatives == 0
    assert report.recall == 1.0


def test_all_four_variant_kinds_are_caught(screened_world):
    # if any variant kind scored zero the matcher would be passing on a strawman
    hits = engine.screen_customers(screened_world)
    report = scoring.score_entities(screened_world, hits)
    assert set(report.by_match_kind) == {"exact", "transliteration", "initials", "reordered"}
    for kind, (detected, total) in report.by_match_kind.items():
        assert detected == total, f"{kind} missed {total - detected} of {total}"


def test_entity_false_positives_are_genuine_name_collisions(screened_world):
    """The surviving false positives must be real same-name humans, not a bug.

    Screening on names alone cannot separate a customer genuinely called
    'Suresh Gupta' from the listed PEP of that name — that is what secondary
    identifiers (DOB, nationality) exist for in a real bank.
    """
    hits = engine.screen_customers(screened_world)
    truth = {r[0] for r in screened_world.execute(
        "SELECT customer_id FROM entity_labels").fetchall()}
    for hit in hits:
        if hit.customer_id not in truth:
            # a false positive is only acceptable if the names really are that close
            assert hit.score >= 0.95, (
                f"unexplained FP: {hit.customer_name} ~ {hit.matched_name} @ {hit.score}")


def test_media_links_every_true_article(screened_world):
    hits = engine.screen_media(screened_world)
    report = scoring.score_media(screened_world, hits)
    assert report.false_negatives == 0
    assert report.recall == 1.0


def test_benign_articles_never_produce_hits(screened_world):
    hits = engine.screen_media(screened_world)
    benign_ids = {r[0] for r in screened_world.execute(
        "SELECT article_id FROM adverse_media WHERE category = 'none'").fetchall()}
    assert not ({h.article_id for h in hits} & benign_ids)


def test_media_hits_carry_an_adverse_category(screened_world):
    for hit in engine.screen_media(screened_world):
        assert hit.category != engine.BENIGN_CATEGORY
        assert hit.headline


def test_scoring_maths_is_consistent(screened_world):
    hits = engine.screen_customers(screened_world)
    report = scoring.score_entities(screened_world, hits)
    assert report.true_positives + report.false_positives == report.flagged_customers
    assert report.precision == pytest.approx(
        report.true_positives / report.flagged_customers)
    assert report.false_positive_rate == pytest.approx(1 - report.precision)


def test_injection_is_deterministic(tmp_path):
    def build():
        conn = connect(":memory:")
        load(conn, n=200, days=10, seed=5)
        inject.inject_entities(conn, random.Random(9), n=6)
        return conn.execute(
            "SELECT customer_id, list_name, match_kind FROM entity_labels"
            " ORDER BY customer_id").fetchall()

    assert build() == build()


def test_variants_differ_from_the_listed_name_except_exact():
    rng = random.Random(1)
    name = "Riyad Mahmoud Haddad"
    assert inject.make_variant(name, "exact", rng) == name
    for kind in ("transliteration", "initials", "reordered"):
        assert inject.make_variant(name, kind, rng) != name


def test_entities_are_only_planted_on_individuals(screened_world):
    segments = {r[0] for r in screened_world.execute(
        "SELECT DISTINCT c.segment FROM entity_labels l JOIN customers c USING (customer_id)"
    ).fetchall()}
    assert segments <= {"salaried", "student", "nri"}
