from pathlib import Path

import pytest

publish = pytest.importorskip("launderlab.publish")
web = pytest.importorskip("launderlab.web")

ALL_PAGES = ["story.html", "results.html", "redteam.html", "multibank.html"]


def _fake_charts(tmp_path, names):
    src = tmp_path / "charts"
    src.mkdir()
    for name in names:
        # a marker unique per file, so a mix-up between them is detectable
        (src / name).write_text(f"<h1>MARKER {name}</h1>", encoding="utf-8")
    return src


def test_every_page_survives_the_copy_with_its_own_content(tmp_path):
    """The landing page owns `index.html`, so no generated page may claim it.

    An earlier layout had the results page publish as `index.html` too, so
    copying it and then writing the landing page over it silently destroyed one
    of the four artifacts — with a green run and a working link that led to the
    wrong page.
    """
    src = _fake_charts(tmp_path, ALL_PAGES)
    docs = tmp_path / "docs"
    copied, missing = publish.publish(src, docs)

    assert not missing
    assert set(copied) == set(ALL_PAGES)
    for name in ALL_PAGES:
        assert f"MARKER {name}" in (docs / name).read_text(encoding="utf-8")

    # and the landing page is its own thing, not a copy of anything
    landing = (docs / "index.html").read_text(encoding="utf-8")
    assert "MARKER" not in landing
    assert "LaunderLab" in landing
    assert "index.html" not in [n for n, _t, _a, _b in publish.PAGES], (
        "no generated page may publish as index.html — the landing page owns it")


def test_the_landing_page_body_never_links_to_a_page_that_is_not_there(tmp_path):
    """A dead link on the one page a reader opens is worse than a missing entry.

    Scoped to the page BODY, deliberately. The persistent top navigation is the
    product's spine: it carries the same five entries in the same order on every
    page, because a nav that changes shape as you move through a site is worse
    than one entry that 404s in a partial build. So the nav is excluded here and
    the caveat is recorded rather than hidden — `publish` prints the missing
    pages, and a full build (the only state that is ever committed) has none.

    Everything below the nav routes through one availability check, and this
    test is what forced it: the research-question cards and both start-here
    cards originally linked unconditionally.
    """
    src = _fake_charts(tmp_path, ["story.html"])
    docs = tmp_path / "docs"
    copied, missing = publish.publish(src, docs)

    assert copied == ["story.html"]
    assert set(missing) == {"results.html", "redteam.html", "multibank.html"}

    landing = (docs / "index.html").read_text(encoding="utf-8")
    body = landing.split("</header>", 1)[1]

    assert 'href="story.html"' in body
    for absent in ("results.html", "redteam.html", "multibank.html"):
        assert f'href="{absent}"' not in body, (
            f"the landing page body links to {absent}, which was not generated")
    assert body.count("Not generated yet") >= 3, (
        "an ungenerated page must say so rather than vanish from the page")


def test_an_incomplete_publish_reports_what_is_missing(tmp_path, capsys):
    """The nav caveat above is only acceptable if an incomplete build is loud."""
    src = _fake_charts(tmp_path, ["story.html"])
    _copied, missing = publish.publish(src, tmp_path / "docs")
    assert missing, "fixture must be incomplete for this to mean anything"
    # the CLI is what a human sees; it must name the gap, not just succeed
    import inspect
    cli = inspect.getsource(publish.main)
    assert "missing" in cli and "generate these first" in cli


def test_publishing_copies_bytes_and_invents_no_figures(tmp_path):
    """Re-rendering a page from a second entry point would let a published
    number drift from the one the scorers grade — the failure this project has
    already corrected four separate times."""
    src = _fake_charts(tmp_path, ["story.html"])
    original = (src / "story.html").read_bytes()
    publish.publish(src, tmp_path / "docs")

    assert (tmp_path / "docs" / "story.html").read_bytes() == original


def test_publishing_writes_files_and_nothing_else(tmp_path):
    """It must never commit, push, or touch repository settings — going public
    is a human's decision, and the command only stages the bytes for it."""
    import ast
    import inspect

    # Checked against the module's actual imports, not its prose. A substring
    # scan matched "gh " inside the word "enough" in the page copy — a test that
    # fails on English is a test nobody will keep.
    tree = ast.parse(inspect.getsource(publish))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for forbidden in ("subprocess", "os", "requests", "urllib", "http", "socket"):
        assert forbidden not in imported, (
            f"publish must not reach outside the working tree: imports {forbidden}")

    src = _fake_charts(tmp_path, ["story.html"])
    publish.publish(src, tmp_path / "docs")
    assert sorted(p.name for p in (tmp_path / "docs").iterdir()) == [
        "index.html", "story.html"]


def test_the_published_test_count_matches_reality_and_itself(request, tmp_path):
    """One number, everywhere, and it cannot go stale silently.

    The landing page carried a hand-typed "302" that was wrong within a day. The
    fix is not to stop writing it down — it is to write it down ONCE and pin it.
    So this checks `TEST_COUNT` three ways:

    * against the suite pytest actually collected,
    * against the README badge,
    * against the README's project tree,

    which is what makes "consistent everywhere" a property rather than an
    intention. Counting `def test_` from source was the previous attempt and it
    undercounts: parametrised functions expand into several cases each, so the
    site would have published "301 functions" beside a badge reading "311
    tests", and a reader who spots two test counts stops trusting the other
    figures too.
    """
    collected = len(request.session.items)

    # Growth is the direction that actually goes stale, and it is checked on
    # every run including a partial one. Exact equality is asserted only on a
    # full run, because `pytest tests/test_publish.py` legitimately collects
    # fewer -- and a conditional assertion is not a skip, which CI forbids.
    assert collected <= publish.TEST_COUNT, (
        f"the suite has grown to {collected}; bump publish.TEST_COUNT and the "
        "two README references, or the site publishes a number that is too low")
    if collected > publish.TEST_COUNT * 0.9:
        assert collected == publish.TEST_COUNT, (
            f"full suite collected {collected}, TEST_COUNT says {publish.TEST_COUNT}")

    readme = (Path(publish.__file__).resolve().parents[2] / "README.md")
    text = readme.read_text(encoding="utf-8")
    assert f"TESTS-{publish.TEST_COUNT}_PASSING" in text, "README badge disagrees"
    assert f"{publish.TEST_COUNT} tests, 0 skips" in text, "README tree disagrees"

    src = _fake_charts(tmp_path, ALL_PAGES)
    landing = (publish.publish(src, tmp_path / "docs")
               and (tmp_path / "docs" / "index.html").read_text(encoding="utf-8"))
    assert f"<b>{publish.TEST_COUNT}</b> tests, zero skips" in landing


def test_the_landing_page_states_no_measured_result_it_cannot_source(tmp_path):
    """The landing page is the ONE page not rendered from a scorer, so it is the
    one page where a figure could silently go stale.

    Every number on it must be a fixed property of the build (how many
    typologies exist, how many detection layers) or a headline that the page it
    links to renders from the scorers itself. A measured figure invented here
    would be exactly the drift this project generates its pages to avoid.
    """
    src = _fake_charts(tmp_path, ALL_PAGES)
    landing = (publish.publish(src, tmp_path / "docs")
               and (tmp_path / "docs" / "index.html").read_text(encoding="utf-8"))

    # the headline figures it does quote must each appear on the page that owns them
    for figure, owner in (("75", "multibank.html"), ("1.25", "results.html")):
        assert figure in landing
        assert f'href="{owner}"' in landing, (
            f"the landing page quotes {figure} but does not link to the page that "
            "renders it, so a reader cannot check it against the source of truth")


# --------------------------------------------------------- the design system

def test_every_published_page_shares_one_navigation(tmp_path):
    """One product, not four documents in a folder. If the nav ever diverges per
    page, a reader loses the ability to move between experiments."""
    for href, label in web.NAV:
        assert href.endswith(".html") and label
    hrefs = [h for h, _ in web.NAV]
    assert hrefs[0] == "index.html", "the landing page must be first in the nav"
    assert len(set(hrefs)) == len(hrefs), "a duplicate nav target is a broken nav"

    src = _fake_charts(tmp_path, ALL_PAGES)
    landing = (publish.publish(src, tmp_path / "docs")
               and (tmp_path / "docs" / "index.html").read_text(encoding="utf-8"))
    for href, _label in web.NAV:
        assert f'href="{href}"' in landing


def test_pages_are_self_contained_and_need_no_network(tmp_path):
    """A portfolio artifact that needs a CDN reachable is one that fails in the
    room — and this site's whole audience is people who will never run it
    locally. GitHub Pages serves it flat, with nothing in front."""
    src = _fake_charts(tmp_path, ALL_PAGES)
    landing = (publish.publish(src, tmp_path / "docs")
               and (tmp_path / "docs" / "index.html").read_text(encoding="utf-8"))

    assert "<script src" not in landing and "<link rel=\"stylesheet\"" not in landing
    assert "@import" not in landing and "<img" not in landing
    # the only permitted external reference is the repository link itself
    for token in ("http://", "https://"):
        for hit in landing.split(token)[1:]:
            assert hit.startswith("github.com/Dhanu2626/launderlab"), (
                f"unexpected external reference: {token}{hit[:60]}")


def test_content_is_visible_without_javascript(tmp_path):
    """Reveal-on-scroll must never be load-bearing for whether the page has
    content. An earlier version hid every section at `opacity:0` unconditionally
    and relied on script to reveal it, so a failed script meant a blank page."""
    src = _fake_charts(tmp_path, ALL_PAGES)
    landing = (publish.publish(src, tmp_path / "docs")
               and (tmp_path / "docs" / "index.html").read_text(encoding="utf-8"))

    assert ".js [data-rv] { opacity:0" in landing, (
        "the hide rule must be scoped to a class only script can add")
    assert "[data-rv] { opacity:0" not in landing.replace(".js [data-rv] { opacity:0", ""), (
        "no unscoped rule may hide content when script is unavailable")
    assert 'className+=" js"' in landing


def test_motion_is_refusable(tmp_path):
    """Accessibility basics are never the thing to simplify away."""
    src = _fake_charts(tmp_path, ALL_PAGES)
    landing = (publish.publish(src, tmp_path / "docs")
               and (tmp_path / "docs" / "index.html").read_text(encoding="utf-8"))

    assert "prefers-reduced-motion" in landing
    assert "<html lang=" in landing, "a screen reader needs the document language"
    assert 'class="skip"' in landing, "keyboard users need a skip link"
    assert ":focus-visible" in landing, "keyboard focus must stay visible"
