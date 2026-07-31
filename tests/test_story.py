import inspect
import random
import re
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import mule_network, structuring
from launderlab.workbench import cases, risk
from launderlab.world.generate import load

story = pytest.importorskip("launderlab.story")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """A small world with both typologies the replay can actually see fire.

    Structuring and layering on purpose: one is caught by a rule that needs
    deposits to *accumulate* (so its latency is non-zero and meaningful), the
    other by the graph as soon as two hops exist (so latency is near-instant).
    A world with only one of them could not show that the measurement
    discriminates.
    """
    path = tmp_path_factory.mktemp("story") / "w.duckdb"
    conn = connect(path)
    load(conn, n=250, days=21, seed=17)
    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    retail = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id").fetchall()]
    rng = random.Random(4)
    for i in range(2):
        structuring.inject(conn, f"S{i}", rng.choice(biz), date(2026, 7, 3), rng,
                           target_total=2_600_000)
        mule_network.inject(conn, f"M{i}", rng.sample(retail, 4), date(2026, 7, 3), rng)
    cases.open_from_queue(conn, risk.score_accounts(conn), actor="system")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def stories(world):
    return story.build_stories(world)


# ------------------------------------------------------------- the mechanism

def test_replay_actually_truncates_the_ledger(world):
    """The load-bearing mechanism, pinned directly.

    Every latency number rests on `transactions` really being shadowed by a
    truncated view. If `search_path` ever stopped shadowing it, the detectors
    would silently run against the FULL world on every day of the replay and
    report that every scheme was detected on day one — a flattering number, with
    nothing failing. So assert the row count through the view, not the effect.
    """
    full = world.execute("SELECT count(*) FROM transactions").fetchone()[0]
    cutoff = date(2026, 7, 5)
    expected = world.execute(
        "SELECT count(*) FROM transactions WHERE ts < DATE '2026-07-06'").fetchone()[0]

    with story.replay(world) as set_day:
        set_day(cutoff)
        seen = world.execute("SELECT count(*) FROM transactions").fetchone()[0]

    assert seen == expected
    assert seen < full, "the truncated view must be a strict subset of the ledger"


def test_replay_restores_the_real_table_even_when_the_body_raises(world):
    """Leaving `search_path` on the replay schema would give every later query in
    the process a quietly truncated world — including the scorers that produce
    the project's published numbers."""
    full = world.execute("SELECT count(*) FROM transactions").fetchone()[0]

    with pytest.raises(RuntimeError):
        with story.replay(world) as set_day:
            set_day(date(2026, 7, 2))
            raise RuntimeError("boom")

    assert world.execute("SELECT count(*) FROM transactions").fetchone()[0] == full


def test_a_detector_fires_no_earlier_than_the_evidence_exists(world, stories):
    """Latency can under-report but must never over-report.

    A detection dated before the scheme's own first transaction would mean the
    replay leaked future rows into an earlier day.
    """
    for s in stories:
        for hit in s.detections:
            assert hit.day >= s.started, (
                f"{s.scheme_id}: {hit.detector} fired on {hit.day}, before the "
                f"scheme's first transaction on {s.started}")


# --------------------------------------------------------------- the honesty

def test_detection_comes_from_the_detectors_not_the_answer_key(world):
    """THE load-bearing invariant of this module.

    Story Mode is allowed to read `scheme_labels` — narrating what really
    happened is the whole point. What it must never do is derive the *caught*
    side from them: an account lit up because it appears in the answer key would
    animate a detection that never occurred, which is precisely the class of
    flattering artefact this project keeps finding and correcting.

    Checked two ways, because either alone is weak: the caught side must come
    from the real detector modules, and a scheme every detector misses must
    report exactly nothing despite being fully present in ground truth.
    """
    source = inspect.getsource(story)
    fired = inspect.getsource(story.first_fired)

    # the only place labels may be read is the answer-key reader itself
    label_reads = re.findall(r"\b(?:FROM|JOIN)\s+scheme_labels\b", source, re.IGNORECASE)
    assert len(label_reads) == 1, "scheme_labels should be read in exactly one place"
    assert "scheme_labels" not in fired, "the caught side must never consult ground truth"
    assert "rules.run_all" in fired and "motifs.find_chains" in fired

    # and empirically: ground truth present, detectors silent -> no detections
    missed = [s for s in story.build_stories(world) if not s.detections]
    for s in missed:
        assert s.txns, "a scheme with no transactions is not evidence of anything"
        assert s.latency_days is None
        assert s.caught_on is None


def test_alerts_that_predate_a_scheme_are_not_counted_as_catching_it():
    """A scheme is injected into an account that already has a life. Crediting a
    pre-existing alert to the scheme would report detection the scheme did not
    cause, and could even produce a negative latency.

    Tested on hand-built detections rather than on the fixture, deliberately.
    Both this world and the demo world inject on day 3 of the ledger, so almost
    no pre-scheme history exists and every scheme happens to have zero prior
    hits — an assertion over the fixture would pass just as happily against a
    `_split_prior` that returned everything as caused. Same reason
    `test_multibank` builds its bank sequences by hand.
    """
    started = date(2026, 7, 10)
    before = story.Detection("rules", "counterparty_concentration", "A1",
                             date(2026, 7, 4), "already alerting")
    same_day = story.Detection("rules", "structuring_burst", "A1", started, "on the day")
    after = story.Detection("graph", story.GRAPH_DETECTOR, "A2",
                            date(2026, 7, 12), "chain")

    caused, prior = story._split_prior([after, before, same_day], started)

    assert prior == (before,), "an alert predating the scheme is not a catch"
    assert caused == (same_day, after), "and everything from day zero on is"
    assert all(d.day >= started for d in caused)


def test_no_scheme_reports_a_detection_before_its_own_first_transaction(world):
    """The same property, end to end on real data."""
    for s in story.build_stories(world):
        assert all(hit.day < s.started for hit in s.prior)
        assert all(hit.day >= s.started for hit in s.detections)
        assert s.latency_days is None or s.latency_days >= 0


def test_latency_discriminates_between_layers(stories):
    """The measurement has to be able to tell fast detection from slow, or it is
    not measuring anything. The graph sees a chain as soon as two hops exist;
    `structuring_burst` cannot fire until enough deposits have accumulated."""
    caught = [s for s in stories if s.latency_days is not None]
    assert caught, "no scheme was detected at all — the fixture proves nothing"

    graph_hits = [d for s in stories for d in s.detections if d.layer == "graph"]
    rule_hits = [d for s in stories for d in s.detections if d.layer == "rules"]
    assert graph_hits and rule_hits, "both layers must be exercised"
    assert {d.detector for d in graph_hits} == {story.GRAPH_DETECTOR}


def test_a_fast_catch_is_not_reported_as_a_good_one(stories):
    """Latency alone flatters three of the six rules. `round_trip` cannot fire
    until the return leg posts and `dormancy_burst` cannot fire until the
    cash-out does, so both alert only after their scheme has completed — a low
    day count that means nothing was stoppable. The exposure share is what makes
    that visible, so it has to exist wherever latency does."""
    report = story.latency_report(stories)
    for typology, days in report.by_typology.items():
        assert len(report.moved.get(typology, [])) == len(days), (
            f"{typology}: every caught scheme needs an exposure share alongside "
            "its latency, or the fast-but-useless case reads as a success")

    for s in stories:
        if s.latency_days is None:
            assert s.moved_before_alert is None
        else:
            assert 0.0 < s.moved_before_alert <= 1.0
            # the scheme's own first day always counts as moved
            assert s.moved_before_alert > 0


def test_never_caught_is_reported_as_never_not_as_zero(stories):
    """A zero-day latency and "never detected" are opposite findings. Collapsing
    them into the same number would turn the project's worst results into its
    best ones."""
    report = story.latency_report(stories)
    for typology, values in report.by_typology.items():
        assert len(values) + report.never_caught[typology] == report.totals[typology]
    assert all(v >= 0 for values in report.by_typology.values() for v in values)


# ------------------------------------------------------------------ the page

def test_page_is_self_contained(world, tmp_path):
    """Same rule as the charts: a portfolio artifact needing a CDN is one that
    fails in the room — and Story Mode's audience is specifically someone who
    will never run a server."""
    path = story.render(world, tmp_path / "charts")
    html = path.read_text(encoding="utf-8")

    assert path.name == "story.html"
    page = html
    # The ONE permitted external reference is the repository link in the shared
    # footer. Everything else -- styles, scripts, fonts, images -- must be inline,
    # because this page's whole audience is people who open it and nothing else.
    for token in ("http://", "https://"):
        for hit in page.split(token)[1:]:
            assert hit.startswith("github.com/Dhanu2626/launderlab"), (
                f"unexpected external reference: {token}{hit[:60]}")
    assert "<img" not in html and "<script src" not in html and "@import" not in html
    assert "const STORIES = [" in html, "scheme data must be inlined, not fetched"


def test_the_page_opens_on_a_scheme_that_can_actually_be_scrubbed(stories, world, tmp_path):
    """Caught by looking at the page, not by a test — the same way 7.4, 7.5 and
    7.8b were. Sorted by typology the first scheme is a one-day
    `dormant_reactivation`, so the page loaded with a single-position slider and
    the only feature it exists for looked broken on arrival."""
    opening = stories[story.most_illustrative(stories)]
    assert opening.ran_days > 1, "the default scheme must have days to scrub through"
    assert opening.latency_days is not None
    assert 0 < opening.latency_days < opening.ran_days, (
        "it must be caught PARTWAY through, or scrubbing shows no transition")

    html = story.render(world, tmp_path / "charts").read_text(encoding="utf-8")
    assert "const OPEN_ON =" in html and "pick(OPEN_ON)" in html


def test_the_scrubber_calendar_is_built_server_side(stories):
    """Every day the scheme ran, exactly once, in order.

    Built in Python rather than by `Date` arithmetic in the browser: `setDate`
    steps in local time while `toISOString` reads back UTC, so across a DST
    boundary a 23-hour step lands on the same UTC date twice and the scrubber
    repeats a day. The audience for this page is global; the ledger's dates are
    not.
    """
    for s in stories:
        calendar = story._story_json(s)["calendar"]
        assert len(calendar) == len(set(calendar)), f"{s.scheme_id}: duplicated day"
        assert calendar == sorted(calendar)
        assert calendar[0] == s.started.isoformat()
        assert calendar[-1] == s.ended.isoformat()
        assert all(t["day"] in calendar for t in s.txns), (
            "every labelled transaction must fall on a scrubbable day")


def test_charts_scale_to_their_container(world, tmp_path):
    """A fixed-width SVG overflowed the card and pushed the longest bar's value
    label off-screen — measured in a browser at a 717px body. The page's whole
    audience is people reading it, often on a phone."""
    html = story.render(world, tmp_path / "charts").read_text(encoding="utf-8")
    assert '<svg viewBox=' in html
    # viewBox with no fixed pixel width: the SVG scales to its container.
    # A fixed 760px overflowed the card and pushed the longest bar's value label
    # off-screen, measured in a browser at a 717px body.
    assert '<svg viewBox=' in html
    assert 'width="760"' not in html


def test_page_never_ships_ground_truth_it_does_not_render(world, tmp_path):
    """The page inlines its data, so anything put in that payload is published.
    It carries the schemes it narrates — it must not also carry the answer key
    for accounts it says nothing about."""
    html = story.render(world, tmp_path / "charts").read_text(encoding="utf-8")
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert table not in html


def test_render_survives_a_world_with_no_crime_in_it(tmp_path):
    """`charts` degrades to a visible message rather than a traceback when a
    chart cannot be drawn; a page that silently renders an empty scrubber would
    look like a bug in the detector rather than an empty ledger."""
    conn = connect(tmp_path / "empty.duckdb")
    load(conn, n=40, days=7, seed=3)
    try:
        html = story.render(conn, tmp_path / "charts").read_text(encoding="utf-8")
    finally:
        conn.close()
    assert "No story to tell" in html
    assert "demo-world" in html, "it must say how to get a world with crime in it"
