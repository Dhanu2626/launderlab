import pytest

from launderlab.screening.matcher import (
    DEFAULT_THRESHOLD,
    Match,
    normalise,
    screen,
    similarity,
)

# Real transliteration/variant pairs a screening engine must catch.
TRUE_PAIRS = [
    ("Farhan Ali", "Farhaan Ali"),
    ("Imran Sheikh", "Imraan Shaikh"),
    ("Mohammed Ali", "Muhammad Ali"),          # phonetic: JW alone scores only 0.85
    ("Ali Farhaan", "Farhaan Ali"),            # word order
    ("S K Gupta", "Suresh Kumar Gupta"),       # initials
    ("Nguyen Tran", "Nuyen Tran"),             # every phonetic algorithm misses this
    ("Hassan Abdullah Al-Amri", "Hassan Abdulla Al Amri"),
]

# Different people. These are the pairs that make precision hard, and the reason
# whole-string Jaro-Winkler was dropped: its prefix bonus scored 'Suresh Kumar'
# vs 'Suresh Gupta' at 0.900, above any usable threshold.
TRAP_PAIRS = [
    ("Suresh Kumar", "Suresh Gupta"),
    ("Rahul Gupta", "Suresh Gupta"),
    ("Rohit Sharma", "Farhaan Ali"),
    ("Priya Singh", "Suresh Gupta"),
]


@pytest.mark.parametrize(("a", "b"), TRUE_PAIRS)
def test_variants_score_above_threshold(a, b):
    assert similarity(a, b) >= DEFAULT_THRESHOLD


@pytest.mark.parametrize(("a", "b"), TRAP_PAIRS)
def test_different_people_score_below_threshold(a, b):
    assert similarity(a, b) < DEFAULT_THRESHOLD


def test_true_positives_and_traps_are_cleanly_separated():
    # the margin is the whole ballgame: if the worst real variant scored below the
    # best impostor there would be no threshold that works at all
    worst_true = min(similarity(a, b) for a, b in TRUE_PAIRS)
    best_trap = max(similarity(a, b) for a, b in TRAP_PAIRS)
    assert best_trap < DEFAULT_THRESHOLD <= worst_true


def test_exact_match_is_one_and_unrelated_is_low():
    assert similarity("Suresh Gupta", "Suresh Gupta") == 1.0
    assert similarity("Rohit Sharma", "Zhang Wei Ming") < 0.6


def test_normalise_strips_case_accents_and_punctuation():
    assert normalise("  Farhaan   ALI.  ") == "farhaan ali"
    assert normalise("José Muñoz") == "jose munoz"


def test_empty_names_never_match():
    assert similarity("", "Suresh Gupta") == 0.0
    assert similarity("!!!", "Suresh Gupta") == 0.0


def test_phonetic_signal_lifts_a_pair_jaro_winkler_alone_would_miss():
    # mohammed/muhammad is the case that justifies carrying Metaphone at all
    import jellyfish
    assert jellyfish.jaro_winkler_similarity("mohammed", "muhammad") < DEFAULT_THRESHOLD
    assert jellyfish.metaphone("mohammed") == jellyfish.metaphone("muhammad")
    assert similarity("Mohammed Ali", "Muhammad Ali") >= DEFAULT_THRESHOLD


def test_screen_returns_sorted_matches_above_threshold():
    watchlist = [
        {"name": "Farhaan Ali", "type": "sanctions", "program": "SDGT", "country": "Syria"},
        {"name": "Suresh Gupta", "type": "pep", "program": "Domestic PEP", "country": "India"},
        {"name": "Zhang Wei Ming", "type": "sanctions", "program": "CMIC", "country": "China"},
    ]
    matches = screen("Farhan Ali", watchlist)
    assert matches and isinstance(matches[0], Match)
    assert matches[0].name == "Farhaan Ali"
    assert matches[0].list_type == "sanctions"
    assert all(m.score >= DEFAULT_THRESHOLD for m in matches)
    assert matches == sorted(matches, key=lambda m: m.score, reverse=True)


def test_screen_returns_nothing_for_an_unrelated_name():
    watchlist = [{"name": "Farhaan Ali", "type": "sanctions", "program": "", "country": ""}]
    assert screen("Rohit Sharma", watchlist) == []
