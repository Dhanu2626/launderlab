import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import mule_network, structuring
from launderlab.workbench import cases, risk
from launderlab.world.generate import load

viz = pytest.importorskip("launderlab.viz")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    path = tmp_path_factory.mktemp("viz") / "w.duckdb"
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


def test_every_chart_draws_without_falling_back_to_an_error(world, tmp_path):
    """The quality bar says every phase ships a visual artifact, and until this
    module existed no code in the repo could draw one — PROJECT.md claimed a
    "detection-rate-per-typology bar chart" that nothing could regenerate."""
    path = viz.render(world, tmp_path / "charts")
    page = path.read_text(encoding="utf-8")

    assert path.name == "index.html"
    assert page.count("<svg") == 3, "expected one chart per phase section"
    assert "Could not draw this chart" not in page, page[:500]


def test_charts_are_self_contained(world, tmp_path):
    """A portfolio artifact that needs a CDN reachable is one that fails in the
    room. Same rule the workbench page follows."""
    page = viz.render(world, tmp_path / "charts").read_text(encoding="utf-8")
    assert "http://" not in page and "https://" not in page
    assert "<img" not in page, "charts must be inline SVG, not linked images"


def test_charts_come_from_the_scorers_not_their_own_queries(world):
    """Charts about detection quality legitimately read ground truth — but only
    through `*/scoring.py`, so there stays exactly ONE place per layer where the
    answer key is consulted. A chart with its own label query could drift away
    from the published precision and recall and nobody would notice."""
    import inspect
    import re

    source = inspect.getsource(viz)
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert not re.search(rf"\b(FROM|JOIN)\s+{table}\b", source, re.IGNORECASE)
    assert "scoring" in source, "the charts must be built on the scoring modules"


def test_recall_chart_matches_what_the_scorer_reports(world):
    """The number on the chart has to be the number the scorer grades. If these
    can disagree, the visual becomes a second source of truth."""
    from launderlab.detect import rules
    from launderlab.detect import scoring as rules_scoring

    report = rules_scoring.score(world, rules.run_all(world))
    svg, note = viz.rules_recall_by_typology(world)

    assert f"{report.overall_recall:.1%}" in note
    for typology, (detected, total) in report.by_typology.items():
        assert f"{typology}  {detected}/{total}" in svg


def test_a_zero_value_still_renders_its_label(world):
    """Phase 5's headline is five typologies at 0% — a chart that silently drops
    empty bars would hide the entire cross-bank blind-spot finding."""
    svg, _note = viz.graph_visibility(world)
    assert "0/" in svg and "0%" in svg


def test_bar_chart_survives_no_data_and_an_all_zero_series():
    assert "No data" in viz.bar_chart([])
    svg = viz.bar_chart([("a", 0.0), ("b", 0.0)], maximum=1.0)
    assert "a" in svg and "b" in svg  # labels present even with nothing to draw
