import pytest

publish = pytest.importorskip("launderlab.publish")


def _fake_charts(tmp_path, names):
    src = tmp_path / "charts"
    src.mkdir()
    for name in names:
        # a marker unique per file, so a mix-up between them is detectable
        (src / name).write_text(f"<h1>MARKER {name}</h1>", encoding="utf-8")
    return src


def test_every_page_survives_the_copy_with_its_own_content(tmp_path):
    """The landing page and the charts page both want `index.html`.

    An earlier version let both claim it, so copying the charts page and then
    writing the landing page over it silently destroyed one of the four
    artifacts — with a green run and a working link that led to the wrong page.
    """
    src = _fake_charts(tmp_path, ["story.html", "index.html", "redteam.html",
                                  "multibank.html"])
    docs = tmp_path / "docs"
    copied, missing = publish.publish(src, docs)

    assert not missing
    assert set(copied) == {"story.html", "charts.html", "redteam.html", "multibank.html"}
    assert "MARKER index.html" in (docs / "charts.html").read_text(encoding="utf-8")
    assert "MARKER story.html" in (docs / "story.html").read_text(encoding="utf-8")
    # and the landing page is its own thing, not a copy of anything
    landing = (docs / "index.html").read_text(encoding="utf-8")
    assert "MARKER" not in landing
    assert "LaunderLab" in landing


def test_the_landing_page_never_links_to_a_page_that_is_not_there(tmp_path):
    """A dead link on the one page a reader opens is worse than a missing entry.
    The page still lists what it does not have, rather than pretending the
    artifact was never part of the project."""
    src = _fake_charts(tmp_path, ["story.html"])
    docs = tmp_path / "docs"
    copied, missing = publish.publish(src, docs)

    assert copied == ["story.html"]
    assert set(missing) == {"index.html", "redteam.html", "multibank.html"}

    landing = (docs / "index.html").read_text(encoding="utf-8")
    assert 'href="story.html"' in landing
    for absent in ("charts.html", "redteam.html", "multibank.html"):
        assert f'href="{absent}"' not in landing
    assert landing.count("not generated yet") == 3


def test_publishing_copies_bytes_and_invents_no_figures(tmp_path):
    """Re-rendering a page from a second entry point would let a published
    number drift from the one the scorers grade — the failure this project has
    already corrected four separate times."""
    src = _fake_charts(tmp_path, ["story.html"])
    original = (src / "story.html").read_bytes()
    docs = tmp_path / "docs"
    publish.publish(src, docs)

    assert (docs / "story.html").read_bytes() == original


def test_publishing_writes_files_and_nothing_else(tmp_path, monkeypatch):
    """It must never commit, push, or touch repository settings — going public
    is a human's decision, and the command only stages the bytes for it."""
    import inspect

    source = inspect.getsource(publish)
    for forbidden in ("subprocess", "git ", "gh ", "requests", "urllib"):
        assert forbidden not in source, f"publish must not reach outside the tree: {forbidden}"

    src = _fake_charts(tmp_path, ["story.html"])
    publish.publish(src, tmp_path / "docs")
    assert sorted(p.name for p in (tmp_path / "docs").iterdir()) == [
        "index.html", "story.html"]
