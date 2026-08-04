import inspect
import random
import re
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import mule_network, structuring
from launderlab.workbench import cases, risk
from launderlab.world.generate import load

metrics = pytest.importorskip("launderlab.metrics")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    path = tmp_path_factory.mktemp("metrics") / "w.duckdb"
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


def test_unworked_queue_reports_conversion_as_unmeasurable_not_zero(world):
    """THE honesty property of this module.

    "Nobody has reviewed these yet" and "everything reviewed was cleared" are
    opposite facts about a bank. A 0.0 would merge them, and the merged version
    is the one that makes a detection stack look bad for a reason that is not
    its fault. The demo world's 50 cases all sit open, so this is the live case,
    not a hypothetical.
    """
    m = metrics.collect(world)
    assert m.cases_closed == 0
    assert m.observed_conversion is None, "an unworked queue has no conversion rate"
    assert m.conversion_is_measurable is False

    text = "\n".join(metrics.summary_lines(m))
    assert "NOT MEASURABLE" in text
    assert "0.0%" not in text.split("alert-to-SAR")[1].split("\n")[0]


def test_conversion_becomes_measurable_once_a_case_is_actually_worked(world, tmp_path):
    """And when a human has worked cases, the observed rate is theirs — computed
    from dispositions, never inferred from ground truth."""
    conn = connect(tmp_path / "worked.duckdb")
    world.execute("SELECT 1")  # keep the fixture ordering explicit
    load(conn, n=120, days=14, seed=5)
    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    rng = random.Random(2)
    structuring.inject(conn, "S0", biz[0], date(2026, 7, 3), rng, target_total=2_600_000)
    opened = cases.open_from_queue(conn, risk.score_accounts(conn), actor="system")
    assert opened, "fixture must open at least one case"

    cases.close(conn, opened[0], "true_positive_sar", actor="dhanush",
                rationale="structured cash deposits, SAR filed")
    m = metrics.collect(conn)
    conn.close()

    assert m.cases_closed == 1
    assert m.sars_filed == 1
    assert m.observed_conversion == pytest.approx(1.0)
    assert m.conversion_is_measurable is True
    assert "NOT MEASURABLE" not in "\n".join(metrics.summary_lines(m))


def test_the_conversion_ceiling_is_exactly_queue_precision(world):
    """Not a coincidence worth hiding behind one field name.

    If analysts never err, every case on a laundering account becomes a SAR and
    every other is cleared — so the industry's headline *analyst* KPI reduces to
    a property of the *queue*. In production the two are inseparable because
    nobody knows which cleared alerts were mistakes. Here ground truth exists,
    so the identity can be shown.
    """
    m = metrics.collect(world)
    assert m.ceiling_conversion == m.queue_precision
    assert 0.0 <= m.ceiling_conversion <= 1.0
    assert "= queue precision" in "\n".join(metrics.summary_lines(m))


def test_workload_needs_no_assumption_and_hours_names_the_one_it_uses(world):
    """`reviews_per_true_find` is a count over a count. Hours multiply it by an
    explicit input, so a reader can reject the assumption without losing the
    measurement underneath it."""
    m = metrics.collect(world)
    for row in m.budgets:
        if row.true_finds == 0:
            assert row.reviews_per_true_find is None
            assert row.hours_per_true_find() is None
            continue
        assert row.reviews_per_true_find == pytest.approx(row.worked / row.true_finds)
        assert row.hours_per_true_find(2.0) == pytest.approx(
            row.reviews_per_true_find * 2.0)
        # the default must be visible, not silently folded in
        assert row.hours_per_true_find() == pytest.approx(
            row.reviews_per_true_find * metrics.DEFAULT_REVIEW_HOURS)

    assert "ASSUMPTION" in "\n".join(metrics.summary_lines(m))


def test_a_budget_can_never_report_more_work_than_it_allows(world):
    """A budget is a cap on analyst hours. Reporting more worked than the budget
    permits would overstate what the stack delivers for a given headcount."""
    m = metrics.collect(world)
    for row in m.budgets:
        assert row.worked <= row.budget
        assert row.true_finds <= row.worked
        assert 0.0 <= row.precision <= 1.0
    widths = [r.worked for r in m.budgets]
    assert widths == sorted(widths), "a larger budget must never work fewer alerts"


def test_metrics_read_ground_truth_only_through_the_scorers(world):
    """Same rule `viz.py` follows: one place per layer consults the answer key,
    so a KPI can never quietly disagree with a published precision figure."""
    source = inspect.getsource(metrics)
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert not re.search(rf"\b(FROM|JOIN)\s+{table}\b", source, re.IGNORECASE)
    assert "dirty_accounts" in source and "rules_scoring" in source


def test_a_crime_free_world_refuses_to_report_a_detection_rate(tmp_path):
    """Found by publishing the page and reading it, not by a test.

    `charts` called `connect()` bare while `story` and `metrics` honoured
    `LAUNDERLAB_DB`, so it drew against the 25-customer seed ledger — which has
    no schemes in it — and published "detection rate 0.0%". Arithmetically true,
    and a statement about nothing: 0 of 0 schemes caught reads as a total
    failure of the detection stack.

    The env-var fix is the root cause; this is the guard that holds whichever
    ledger someone points at it.
    """
    from launderlab import viz
    from launderlab.world.generate import load

    conn = connect(tmp_path / "clean.duckdb")
    load(conn, n=40, days=7, seed=3)
    try:
        m = metrics.collect(conn)
        assert m.schemes_total == 0
        with pytest.raises(ValueError, match="no injected schemes"):
            viz.kpi_dashboard(conn)

        # and the whole page refuses, rather than drawing four confident zeros.
        # Guarding only the KPI section left the Phase 3 chart still publishing
        # "Overall 0.0% recall at 0.0% precision across 0 schemes".
        html = viz.render(conn, tmp_path / "charts").read_text(encoding="utf-8")
        assert "no injected schemes" in html
        assert "demo-world" in html
        assert "0.0% recall" not in html, "a rate over an empty denominator is not a result"
        # chart wrappers, not raw <svg>: the theme toggle icons are SVG and
        # are page furniture, not a claim about the data
        assert 'class="chart-wrap"' not in html, (
            "no chart is better than a misleading one")
    finally:
        conn.close()


def test_every_entry_point_honours_the_selected_world(tmp_path):
    """The root cause: four call sites each wrote their own `LAUNDERLAB_DB`
    lookup and one of them forgot. There is one now."""
    import os

    from launderlab.db.ledger import connect_configured

    target = tmp_path / "chosen.duckdb"
    os.environ["LAUNDERLAB_DB"] = str(target)
    try:
        conn = connect_configured()
        conn.execute("SELECT 1")
        conn.close()
    finally:
        del os.environ["LAUNDERLAB_DB"]
    assert target.exists(), "connect_configured must open the world it was told to"

    import inspect

    from launderlab import metrics as metrics_mod
    from launderlab import story, viz
    for module in (viz, story, metrics_mod):
        source = inspect.getsource(module.main)
        assert "connect_configured" in source, (
            f"{module.__name__}.main must use the shared lookup, not its own")


def test_detection_numbers_match_the_rules_scorer_exactly(world):
    """The dashboard cannot become a second, drifting source of truth for the
    numbers PROJECT.md publishes."""
    from launderlab.detect import rules
    from launderlab.detect import scoring as rules_scoring

    report = rules_scoring.score(world, rules.run_all(world))
    m = metrics.collect(world)
    assert m.recall == report.overall_recall
    assert m.precision == report.precision
    assert m.false_positive_rate == report.false_positive_rate
    assert m.schemes_total == report.schemes_total
