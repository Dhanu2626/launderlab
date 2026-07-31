"""Charts, rendered as self-contained SVG from real scored data.

The project's quality bar says every phase ships a visual artifact rather than a
table, and until now that was honoured by generating charts in a session and
looking at them. Nothing in the repository produced one, so the claim was not
reproducible -- PROJECT.md's Phase 3 entry says "Real visual:
detection-rate-per-typology bar chart" and there was no code that could draw it
again. This module closes that gap.

WHY HAND-WRITTEN SVG AND NOT MATPLOTLIB. Three bar charts is not worth a plotting
dependency, and the repo already renders HTML without one (`statement.py`, the
workbench page). SVG in a page also stays legible in dark mode via the same CSS
variables the workbench uses, which a rasterised PNG cannot. If the whitepaper in
Phase 9 needs publication-quality figures, that is the moment to reach for a real
plotting library -- not before.

BOUNDARY, and it is the interesting one: **charts about detection quality are
scoring output, so this module is allowed to read ground truth** -- the same
exception `*/scoring.py` and `workbench/evaluate.py` hold. It reads the labels
only through those scorers, never with its own query, so there is exactly one
place per layer where the answer key is consulted.

    python -m launderlab charts             # writes to charts/ and opens the index
"""

from __future__ import annotations

import html
import webbrowser
from pathlib import Path

import duckdb

from launderlab.detect import rules
from launderlab.detect import scoring as rules_scoring
from launderlab.graph import build as graph_build
from launderlab.graph import motifs
from launderlab.graph import scoring as graph_scoring

DEFAULT_OUT = Path("charts")

# Colours come through as CSS variables so one SVG reads correctly in both
# themes; the fallbacks keep it sane if the file is opened standalone.
CSS = """
:root { --bg:#fbfbfa; --panel:#fff; --ink:#14140f; --muted:#6b6b63; --line:#e3e2da;
        --bar:#185fa5; --bar2:#0f6e56; --miss:#c9c7bd; --warn:#a32d2d;
        --l1:#185fa5; --l2:#0f6e56; --l3:#b45309; --l4:#7a3ea3; --l5:#a32d2d; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161614; --panel:#1e1e1b; --ink:#f2f1ea; --muted:#9d9c92;
          --line:#32312c; --bar:#6ea8e6; --bar2:#4fb59a; --miss:#3a3934;
          --l1:#6ea8e6; --l2:#4fb59a; --l3:#e0a458; --l4:#c398e8; --l5:#e08080; } }
* { box-sizing:border-box; }
body { margin:0; padding:30px 28px 60px; background:var(--bg); color:var(--ink);
       font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; max-width:900px; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:14px; margin:34px 0 4px; }
p.sub { color:var(--muted); font-size:13px; margin:0 0 12px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:9px;
        padding:14px 16px; overflow-x:auto; }
.bar { fill:var(--bar); } .bar.alt { fill:var(--bar2); } .bar.miss { fill:var(--miss); }
.lbl { font-size:11.5px; fill:var(--ink); }
.val { font-size:11px; fill:var(--muted); }
.axis { stroke:var(--line); stroke-width:1; }
.note { color:var(--muted); font-size:12.5px; margin:10px 0 0; }
.warn { color:var(--warn); }
.legend { display:flex; flex-wrap:wrap; gap:12px 18px; margin-top:8px; font-size:12.5px; }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.legend i { width:11px; height:11px; border-radius:2px; display:inline-block; }
"""

_ROW_H = 26
_PAD_L = 190
_PAD_R = 58
_WIDTH = 760


def page(title: str, subtitle: str, body: str, *, heading: str | None = None,
         extra_css: str = "") -> str:
    """One self-contained HTML page — no CDN, no build step, readable in both themes.

    Four pages now share this shell (the three charts and Phase 9's Story Mode),
    so the alternative is four copies of a doctype and a stylesheet drifting apart.
    `subtitle` is inserted as HTML, not escaped: every caller passes a sentence
    containing a `<code>` command, which is the point of it.
    """
    return (f'<!doctype html>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{html.escape(title)}</title>\n<style>{CSS}{extra_css}</style>\n"
            f"<h1>{html.escape(heading or title)}</h1>\n"
            + (f'<p class="sub">{subtitle}</p>\n' if subtitle else "")
            + body + "\n")


def bar_chart(rows: list[tuple[str, float]], *, maximum: float | None = None,
              fmt: str = "{:.0%}", alt: set[str] | None = None) -> str:
    """Horizontal bars. `rows` is [(label, value)]; longest label sets the gutter."""
    if not rows:
        return '<p class="note">No data.</p>'
    alt = alt or set()
    top = maximum if maximum is not None else max(v for _, v in rows)
    top = top or 1.0
    plot = _WIDTH - _PAD_L - _PAD_R
    height = len(rows) * _ROW_H + 14

    # Scales to its container instead of a fixed 760px. Measured in a browser:
    # at a 717px body the fixed width overflowed the card and pushed the LONGEST
    # bar's value label off-screen -- so the one number a reader most wants was
    # the one number they could not see, on a page whose entire job is being read
    # by someone who will not open the data.
    parts = [f'<svg viewBox="0 0 {_WIDTH} {height}" width="100%" '
             f'style="max-width:{_WIDTH}px" '
             f'role="img" aria-label="bar chart of {len(rows)} values">']
    for i, (label, value) in enumerate(rows):
        y = i * _ROW_H + 6
        width = max(1.0, (value / top) * plot) if value > 0 else 0.0
        css = "bar alt" if label in alt else ("bar miss" if value <= 0 else "bar")
        parts.append(
            f'<text class="lbl" x="{_PAD_L - 8}" y="{y + 13}" text-anchor="end">'
            f'{html.escape(label)}</text>')
        if width:
            parts.append(f'<rect class="{css}" x="{_PAD_L}" y="{y + 2}" '
                         f'width="{width:.1f}" height="{_ROW_H - 10}" rx="2"></rect>')
        parts.append(f'<text class="val" x="{_PAD_L + width + 6:.1f}" y="{y + 13}">'
                     f'{fmt.format(value)}</text>')
    parts.append(f'<line class="axis" x1="{_PAD_L}" y1="2" x2="{_PAD_L}" '
                 f'y2="{height - 6}"></line>')
    parts.append("</svg>")
    return "".join(parts)


def _share(pairs: dict) -> list[tuple[str, float]]:
    """{typology: (detected, total)} -> [(label, fraction)], strongest first.

    Both scorers report the same `(detected, total)` shape, so the label carries
    the raw counts: "9/15" is the honest thing to read next to 60%.
    """
    rows = []
    for name, (detected, total) in pairs.items():
        rows.append((f"{name}  {detected}/{total}",
                     detected / total if total else 0.0))
    return sorted(rows, key=lambda r: r[1], reverse=True)


def rules_recall_by_typology(conn: duckdb.DuckDBPyConnection) -> tuple[str, str]:
    """Phase 3's chart: what share of each typology's schemes the rules caught."""
    report = rules_scoring.score(conn, rules.run_all(conn))
    svg = bar_chart(_share(report.by_typology), maximum=1.0)
    note = (f"Recall per injected typology, scored against ground truth. Overall "
            f"{report.overall_recall:.1%} recall at {report.precision:.1%} precision "
            f"across {report.schemes_total} schemes. A short bar is a measured blind "
            f"spot, not a missing measurement.")
    return svg, note


def graph_visibility(conn: duckdb.DuckDBPyConnection) -> tuple[str, str]:
    """Phase 5's headline: how much of each typology a graph can even see."""
    report = graph_scoring.score_chains(
        conn, motifs.find_chains(graph_build.build_graph(conn)))
    rows = _share(report.schemes_with_internal_edges)
    svg = bar_chart(rows, maximum=1.0, alt={label for label, value in rows if value > 0})
    note = ("Share of each typology that leaves any internal edge to analyse. The zeros "
            "are the cross-bank blind spot, not a detection failure: those counterparties "
            "bank elsewhere, so the scheme leaves one leg and no edge. Of the chains that "
            f"do exist, the detector found {report.layering_schemes_detected}/"
            f"{report.layering_schemes_total} at {report.precision:.0%} precision.")
    return svg, note


def queue_composition(conn: duckdb.DuckDBPyConnection) -> tuple[str, str]:
    """Phase 7: which layer actually put work in front of an analyst."""
    from launderlab.workbench import cases, risk

    counts = dict.fromkeys(risk.TIER_ORDER, 0)
    layers = dict.fromkeys(risk.TIER_ORDER, 0)
    open_cases = cases.queue(conn, status="open", limit=500)
    for case in open_cases:
        sources = {s.source for s in case.signals}
        counts[next((t for t in risk.TIER_ORDER if t in sources),
                    risk.TIER_ORDER[-1])] += 1
        for source in sources:
            if source in layers:
                layers[source] += 1

    rows = [(f"tier: {name}", counts[name]) for name in risk.TIER_ORDER]
    rows += [(f"contributes: {name}", layers[name]) for name in risk.TIER_ORDER]
    svg = bar_chart(rows, fmt="{:.0f}", alt={f"contributes: {n}" for n in risk.TIER_ORDER})
    note = (f"{len(open_cases)} open cases. The top four bars are which tier a case was "
            "filed under; the lower four are how many cases each layer contributed any "
            "evidence to. A layer can carry many cases without ever owning a tier.")
    return svg, note


_LINE_COLORS = ("l1", "l2", "l3", "l4", "l5")
_LINE_W, _LINE_H = 700, 300
_LINE_PAD = 44


def line_chart(series: dict[str, list[float]], *, y_max: float = 1.0,
               y_fmt: str = "{:.0%}") -> str:
    """Multiple named series, one polyline each, sharing 0..len-1 on the x-axis.

    Generic on purpose -- Phase 8 is the first thing in this module with a
    trend over an ordered axis rather than one snapshot, so it earns its own
    primitive instead of forcing a line into `bar_chart`'s per-category shape.
    """
    if not series:
        return '<p class="note">No data.</p>'
    n_points = max(len(values) for values in series.values())
    plot_w, plot_h = _LINE_W - _LINE_PAD * 2, _LINE_H - _LINE_PAD * 2
    x_step = plot_w / max(n_points - 1, 1)

    def xy(i: int, value: float) -> tuple[float, float]:
        x = _LINE_PAD + i * x_step
        y = _LINE_PAD + plot_h * (1 - min(value / y_max, 1.0))
        return x, y

    parts = [f'<svg viewBox="0 0 {_LINE_W} {_LINE_H}" width="100%" '
             f'style="max-width:{_LINE_W}px" '
             f'role="img" aria-label="line chart, {len(series)} series over '
             f'{n_points} points">']
    # axes + y gridlines at 0/25/50/75/100%
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        _, y = xy(0, frac * y_max)
        parts.append(f'<line class="axis" x1="{_LINE_PAD}" y1="{y:.1f}" '
                     f'x2="{_LINE_W - _LINE_PAD}" y2="{y:.1f}"></line>')
        parts.append(f'<text class="val" x="{_LINE_PAD - 8}" y="{y + 4:.1f}" '
                     f'text-anchor="end">{y_fmt.format(frac * y_max)}</text>')
    for i in range(n_points):
        x, _ = xy(i, 0)
        parts.append(f'<text class="val" x="{x:.1f}" y="{_LINE_H - _LINE_PAD + 16}" '
                     f'text-anchor="middle">gen{i}</text>')

    for idx, (name, values) in enumerate(series.items()):
        color = f"var(--{_LINE_COLORS[idx % len(_LINE_COLORS)]})"
        points = [xy(i, v) for i, v in enumerate(values)]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" '
                     f'stroke-width="2.25"></polyline>')
        for x, y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"></circle>')

    parts.append("</svg>")
    legend = "".join(
        f'<span><i style="background:var(--{_LINE_COLORS[i % len(_LINE_COLORS)]})"></i>'
        f'{html.escape(name)}</span>'
        for i, name in enumerate(series))
    return "".join(parts) + f'<div class="legend">{legend}</div>'


def redteam_decay_chart(results, genomes) -> tuple[str, str]:
    """Phase 8's headline: recall per typology, generation over generation,
    against an adversary that mutates its own parameters. Takes the benchmark's
    own return values directly rather than a connection -- `run_decay_benchmark`
    builds and discards a fresh throwaway world per generation internally, so
    there is no single `conn` this chart could read from, and re-running an
    8-generation benchmark (minutes) just to draw a chart already computed in
    memory would be wasted work the CLI already avoided.
    """
    by_typology: dict[str, list] = {}
    for r in results:
        by_typology.setdefault(r.typology, []).append(r)
    series = {}
    for typology, rows in by_typology.items():
        rows = sorted(rows, key=lambda r: r.generation)
        series[typology] = [r.recall for r in rows]

    svg = line_chart(series, y_max=1.0)
    converged = [f"{t} (gen {g.converged_at})" for t, g in genomes.items()
                if g.converged_at is not None]
    note = ("Recall against a static rules engine (plus Phase 5's graph for "
            "mule_network) as the adversary mutates its own injector parameters "
            "each generation it evades detection. Converged (fully evaded at "
            "least once): " + (", ".join(converged) if converged else "none") +
            ". high_risk_geography is excluded -- no continuous evasion knob "
            "exists for it (see redteam.py).")
    return svg, note


def kpi_dashboard(conn: duckdb.DuckDBPyConnection, snapshot=None) -> tuple[str, str]:
    """The four numbers an FCC function reports upward (Phase 9.2).

    Rendered as a definition list rather than a chart: these are five unrelated
    scalars in three different units, and a bar chart comparing a percentage to
    a review count would be decoration pretending to be analysis.
    """
    from launderlab import metrics as metrics_mod

    m = metrics_mod.collect(conn) if snapshot is None else snapshot
    if not m.schemes_total:
        # The guard that would have caught the real bug regardless of which
        # ledger got opened: `charts` read the crime-free seed world and
        # published "detection rate 0.0%" -- arithmetically true, and a
        # statement about nothing. A rate over an empty denominator is not a
        # measurement of a detector, and must never be rendered as one.
        raise ValueError(
            "this ledger has no injected schemes, so detection rate, precision "
            "and conversion are undefined rather than zero. Point LAUNDERLAB_DB "
            "at a world with crime in it: python -m launderlab demo-world")
    rows = [
        ("detection rate", f"{m.recall:.1%}",
         f"{m.schemes_detected} of {m.schemes_total} injected schemes caught"),
        ("alert precision", f"{m.precision:.1%}",
         f"false-positive rate {m.false_positive_rate:.1%}"),
        ("queue precision", f"{m.queue_precision:.1%}",
         f"{m.cases_on_dirty} of {m.cases_total} opened cases sit on an account "
         "genuinely in a scheme"),
    ]
    if m.conversion_is_measurable:
        rows.append(("alert-to-SAR conversion", f"{m.observed_conversion:.1%}",
                     f"observed: {m.sars_filed} SARs from {m.cases_closed} closed cases"))
    else:
        # Never 0% -- see metrics.py. "Unreviewed" and "reviewed and cleared"
        # are opposite facts and a zero would merge them.
        rows.append(("alert-to-SAR conversion", "not measurable",
                     "no case has been worked to a disposition yet; the ceiling if "
                     f"every analyst call were perfect is {m.ceiling_conversion:.1%}, "
                     "which is queue precision by definition"))

    workload = [r for r in m.budgets if r.reviews_per_true_find is not None]
    if workload:
        row = workload[-1]
        rows.append(("reviews per true find", f"{row.reviews_per_true_find:.2f}",
                     f"at an alert budget of {row.budget}: "
                     f"{row.true_finds} real in {row.worked} worked "
                     f"(~{row.hours_per_true_find():.1f}h at "
                     f"{metrics_mod.DEFAULT_REVIEW_HOURS}h per review, an assumption)"))

    items = "".join(
        f'<div class="kpi"><b>{html.escape(value)}</b>'
        f'<span class="k">{html.escape(label)}</span>'
        f'<span class="d">{html.escape(detail)}</span></div>'
        for label, value, detail in rows)
    note = ("Detection rate and precision come from the rules scorer, so they cannot "
            "drift from the figures published elsewhere. Conversion is reported as "
            "measurable or not, never as zero: an unworked queue and a queue whose "
            "every alert was cleared are opposite facts. Its ceiling equals queue "
            "precision exactly — which means the industry's headline analyst KPI "
            "reduces, at best, to a property of the queue rather than of the analyst.")
    return f'<div class="kpis">{items}</div>', note


_KPI_CSS = """
.kpis { display:grid; gap:10px; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); }
.kpi { border:1px solid var(--line); border-radius:8px; padding:10px 12px; background:var(--bg); }
.kpi b { display:block; font-size:22px; font-variant-numeric:tabular-nums; }
.kpi .k { display:block; font-size:12.5px; font-weight:600; margin-top:2px; }
.kpi .d { display:block; font-size:12px; color:var(--muted); margin-top:4px; }
"""


def render(conn: duckdb.DuckDBPyConnection, out_dir: Path = DEFAULT_OUT) -> Path:
    """Write every chart as one self-contained page. Returns its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ONE guard, at the only point every ground-truth chart passes through.
    # Every section here divides by something ground truth supplies, so against
    # a crime-free ledger they all render a confident 0.0% -- "0 of 0 schemes
    # caught" reads as a total failure of the detection stack rather than as an
    # empty world. Guarding each builder separately would be four chances to
    # add a fifth chart that forgets.
    #
    # The count comes from the SCORER, not a label query here: viz.py is held to
    # reading ground truth only through the scoring modules, and the boundary
    # test caught the first version of this guard doing its own SELECT. Computed
    # once and handed to the KPI section, which would otherwise recompute it.
    from launderlab import metrics as metrics_mod

    snapshot = metrics_mod.collect(conn)
    if not snapshot.schemes_total:
        path = out_dir / "index.html"
        path.write_text(page(
            "LaunderLab — measured results",
            "Regenerate with <code>python -m launderlab charts</code>.",
            '<p class="note warn">This ledger has no injected schemes in it, so every '
            "figure on this page would be a rate over an empty denominator — 0 of 0 "
            "schemes caught, which reads as a failed detection stack rather than as an "
            "empty world. No chart is drawn rather than a misleading one. Build a world "
            "with crime in it and point <code>LAUNDERLAB_DB</code> at it: "
            "<code>python -m launderlab demo-world</code>.</p>"),
            encoding="utf-8")
        return path

    sections = []
    for title, builder in (
        ("Operating metrics — what the stack costs to run (Phase 9.2)",
         lambda c: kpi_dashboard(c, snapshot)),
        ("Rules engine — recall by typology (Phase 3)", rules_recall_by_typology),
        ("Graph analytics — what a single bank can see (Phase 5)", graph_visibility),
        ("Workbench queue — which layer reaches an analyst (Phase 7)", queue_composition),
    ):
        try:
            svg, note = builder(conn)
        except Exception as exc:  # a chart that cannot be drawn must say why
            svg = (f'<p class="note warn">Could not draw this chart: '
                   f'{html.escape(f"{type(exc).__name__}: {exc}")}</p>')
            note = ""
        sections.append(
            f"<h2>{html.escape(title)}</h2>"
            f'<div class="card">{svg}</div>'
            + (f'<p class="note">{html.escape(note)}</p>' if note else ""))

    path = out_dir / "index.html"
    path.write_text(page(
        "LaunderLab — measured results",
        "Drawn from the ledger this ran against, scored against ground truth. "
        "Regenerate with <code>python -m launderlab charts</code>.",
        "\n".join(sections), extra_css=_KPI_CSS), encoding="utf-8")
    return path


def multibank_chart(arms) -> tuple[str, str]:
    """Phase 8.5: what each view reconstructs, per placement arm.

    A grouped bar rather than a line: these are three distinct views of the same
    fixed set of chains, not a trend over an ordered axis, so `line_chart`'s
    shape would imply a progression that does not exist.
    """
    from launderlab import multibank

    rows, alt = [], set()
    for placement in multibank.PLACEMENTS:
        if placement not in arms:
            continue
        t = multibank.totals(arms[placement][0])
        if not t.hops:
            continue
        for label, value in (("pooled (central view)", t.pooled),
                             ("single bank alone", t.solo),
                             ("privacy-preserving co-op", t.coop)):
            row = f"{placement}: {label}"
            rows.append((row, value / t.hops))
            if label.startswith("privacy"):
                alt.add(row)

    svg = bar_chart(rows, maximum=1.0, alt=alt)
    note = ("Share of planted mule-chain hops each view can reconstruct. A single bank "
            "sees essentially none of the network no matter how the chain was placed - "
            "rebuilding a chain needs consecutive hops inside one bank, which is rare "
            "once accounts are spread across institutions. Co-operation recovers most "
            "of it while sharing only hashed payment references, never customer data.")
    return svg, note


def render_multibank(arms, out_dir: Path = DEFAULT_OUT) -> Path:
    """Write the Phase 8.5 blind-spot chart as its own self-contained page."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg, note = multibank_chart(arms)

    path = out_dir / "multibank.html"
    path.write_text(page(
        "LaunderLab — the cross-bank blind spot",
        "What one bank sees alone, what a central view would see, and what "
        "privacy-preserving co-operation buys back. Regenerate with "
        "<code>python -m launderlab multibank</code>.",
        f"<h2>Mule-chain hops reconstructed, by view</h2>"
        f'<div class="card">{svg}</div>'
        f'<p class="note">{html.escape(note)}</p>',
        heading="LaunderLab — the cross-bank blind spot (Phase 8.5)"), encoding="utf-8")
    return path


def render_redteam(results, genomes, out_dir: Path = DEFAULT_OUT) -> Path:
    """Write the Phase 8 decay chart as its own self-contained page.

    Separate from `render()`'s `charts/index.html` rather than folded into it:
    that page's three charts each cost a query against an already-open
    connection, while a red team run costs several minutes end to end. Rebuilding
    the fast charts should never force an 8-generation benchmark, and a red team
    result should never depend on which world happens to be sitting at
    `data/demo.duckdb` when someone runs `charts`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg, note = redteam_decay_chart(results, genomes)

    path = out_dir / "redteam.html"
    path.write_text(page(
        "LaunderLab — red team decay benchmark",
        "Recall of a static rules engine against an adversary that mutates its own "
        "parameters. Regenerate with <code>python -m launderlab redteam</code>.",
        f"<h2>Recall by typology, generation over generation</h2>"
        f'<div class="card">{svg}</div>'
        f'<p class="note">{html.escape(note)}</p>',
        heading="LaunderLab — red team decay benchmark (Phase 8)"), encoding="utf-8")
    return path


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    from launderlab.db.ledger import connect_configured

    out = Path(argv[0]) if argv and not argv[0].startswith("-") else DEFAULT_OUT
    conn = connect_configured()
    try:
        path = render(conn, out)
    finally:
        conn.close()
    print(f"Charts written to {path}")
    if "--no-open" not in argv:
        webbrowser.open(path.resolve().as_uri())
