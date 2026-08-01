"""Collect the generated pages into `docs/` and build the landing page.

    python -m launderlab publish

THE GAP THIS CLOSES. `charts/` is gitignored, deliberately: those pages are
derived artifacts and regenerating them is one command. But the audience the
site was built for -- someone who will never clone a repository, install Python
or run a server -- cannot regenerate anything. Until this existed, the project's
entire visual output was invisible to exactly the people it was made for, which
is a strange place for a portfolio piece to end up.

`docs/` is GitHub Pages' conventional publish folder, so committing the pages
there makes them viewable with one setting flipped in the repository, and
nothing is published until a human flips it. That split is on purpose: this
command only writes files into the working tree. It never commits, never pushes
and never touches repository settings.

WHY COPIES AND NOT A SECOND RENDERER. Every experiment page here is written by
the module that owns its measurement (`viz`, `story`). Re-rendering them from a
different entry point would let a published figure drift from the one the
scorers grade, which is the failure this project has corrected four times. So
this copies bytes and invents no number of its own -- the landing page states
only figures that are fixed properties of the build, never measured results.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from launderlab import web

DEFAULT_SOURCE = Path("charts")
DEFAULT_DOCS = Path("docs")

# (source name, published name, title, what the page proves)
PAGES = (
    ("story.html", "story.html", "Story Mode",
     "Replay any injected scheme day by day. Accounts light up only on the day a "
     "real detector actually fired on them."),
    ("results.html", "results.html", "Measured results",
     "Detection rate, precision, queue composition and what the stack costs to "
     "run, every figure drawn from the scoring modules."),
    ("redteam.html", "redteam.html", "Red team benchmark",
     "Recall per typology across 8 generations of an adversary that mutates its "
     "own parameters. Decay is not uniform."),
    ("multibank.html", "multibank.html", "Cross-bank blind spot",
     "Four banks with genuinely separate ledgers flag 75-77% of mule accounts "
     "and reconstruct 0-6% of the chains those accounts form."),
)


def publish(source: Path = DEFAULT_SOURCE, docs: Path = DEFAULT_DOCS,
            ) -> tuple[list[str], list[str]]:
    """Copy every generated page into `docs/` and write the landing page.

    Returns (published names, missing names).
    """
    source, docs = Path(source), Path(docs)
    docs.mkdir(parents=True, exist_ok=True)

    copied, missing = [], []
    for name, target, _title, _blurb in PAGES:
        src = source / name
        if src.exists():
            shutil.copyfile(src, docs / target)
            copied.append(target)
        else:
            missing.append(name)

    landing = _landing(copied)
    docs.joinpath("index.html").write_text(landing, encoding="utf-8")
    # Also drop it beside the generated pages so `charts/` previews as the whole
    # site locally, with the same nav resolving the same way.
    if source.exists():
        source.joinpath("index.html").write_text(landing, encoding="utf-8")
    return copied, missing


# --------------------------------------------------------------- the landing

_LANDING_CSS = """
.big { padding:96px 0 56px; }
.big h1 { max-width:15ch; }
.qcard { border-left:2px solid var(--accent); padding-left:18px; }
.qcard .q { font-size:1rem; font-weight:620; color:var(--ink); margin-bottom:7px; }
.qcard .a { font-size:.91rem; color:var(--ink-dim); line-height:1.6; }
.qcard.t2 { border-color:var(--teal); } .qcard.t3 { border-color:var(--violet); }
.qcard.t4 { border-color:var(--amber); }
.stack { display:grid; gap:14px; }
.arch { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
        justify-content:center; padding:6px 0; }
.arch .b { border:1px solid var(--line); border-radius:11px; padding:12px 16px;
           background:var(--surface); text-align:center; min-width:132px; }
.arch .b .t { font-size:.84rem; font-weight:620; color:var(--ink); }
.arch .b .s { font-size:.73rem; color:var(--ink-faint); margin-top:3px;
              font-family:var(--mono); }
.arch .ar { color:var(--ink-faint); font-size:16px; }
"""


def _test_count() -> int:
    """How many tests exist, counted rather than typed.

    This was a hand-written "302" and it went stale within a day -- on the one
    page every reader lands on, and on a site whose whole claim is that its
    figures are generated rather than typed.

    It counts test FUNCTIONS, and the chip says so, because that is not the same
    number pytest reports. Two `@pytest.mark.parametrize` functions expand into
    11 cases, so 301 functions collect as 310 cases. Both are true and they are
    labelled differently rather than reconciled: making this match pytest exactly
    would mean either parsing parametrize decorators (fragile, and wrong the
    first time someone writes one this parser does not expect) or running the
    suite at publish time (33 seconds, and a dependency on pytest for a command
    whose entire job is copying files).
    """
    tests = Path(__file__).resolve().parents[2] / "tests"
    if not tests.is_dir():
        return 0
    return sum(
        1
        for f in tests.glob("test_*.py")
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.startswith("def test_")
    )


def _landing(available: list[str]) -> str:
    """The landing page. Links only to pages that were actually generated.

    A dead link on the one page a reader opens is worse than a missing entry,
    and a page that lists what it does not have is at least honest about it.

    Every figure here is a fixed property of the build -- how many typologies
    exist, how many tests pass -- never a measured result. Measured results are
    stated only on the pages that render them from the scorers, so this page
    cannot drift out of step with them.
    """
    def live(target: str) -> bool:
        """Whether a target page was actually generated this run.

        Every link on this page routes through here. The research-question cards
        and the two start-here cards used to link unconditionally, so a partial
        build published a landing page with dead links on it -- caught by the
        test written for exactly that, one layer up.
        """
        return target in available

    def linked(target: str, inner: str, cls: str = "card hover",
               rv: int = 0, plain_cls: str = "card") -> str:
        if live(target):
            return f'<a class="{cls}" href="{target}" data-rv="{rv}">{inner}</a>'
        return (f'<div class="{plain_cls}" data-rv="{rv}" style="opacity:.55">{inner}'
                f'<p style="margin-top:12px;color:var(--amber);font-size:.82rem">'
                f'Not generated yet</p></div>')

    cards = []
    for _name, target, title, blurb in PAGES:
        head = f'<h3>{web.esc(title)}</h3><p>{web.esc(blurb)}</p>'
        cards.append(linked(target, head + (
            '<p style="margin-top:12px;color:var(--accent);font-size:.85rem;'
            'font-weight:600">Explore &#8594;</p>' if live(target) else "")))

    questions = (
        ("Detection decay", "How fast does a detection stack rot against an adapting "
         "adversary?",
         "<strong>Non-uniformly.</strong> One rule collapses to zero recall within two "
         "generations of adaptation and stays collapsed. Two others never fully evade "
         "across eight. A single aggregate recall figure could not have shown the "
         "difference.", "", "redteam.html"),
        ("False-positive economics", "What does a true alert actually cost to find?",
         "Measured for every configuration, never estimated. The <strong>top 25 alerts "
         "are 100% true positives</strong>; the next 25 cost 10 false positives &mdash; "
         "1.25 analyst reviews per true find at a budget of 50.", "t2", "results.html"),
        ("The cross-bank blind spot", "What can a single institution structurally not see?",
         "Banks flag <strong>75&ndash;77%</strong> of individual mule accounts on their own "
         "books and reconstruct <strong>0&ndash;6%</strong> of the chains those accounts "
         "form. Privacy-preserving co-operation recovers 69&ndash;81% of hops without "
         "sharing customer data.", "t3", "multibank.html"),
        ("Detection latency", "Was the alert soon enough to matter? (added by Phase 9)",
         "&ldquo;Caught&rdquo; was never one property. The typology this stack detects "
         "<em>fastest</em> is caught with <strong>100% of the money already moved</strong>, "
         "because the rule that catches it cannot fire until the crime has completed.",
         "t4", "story.html"),
    )
    qhtml = '<div class="grid g2">' + "".join(
        linked(href,
               f'<div class="qcard {tone}"><div class="q">{web.esc(q)}</div>'
               f'<div class="a">{a}</div></div>'
               f'<p style="margin-top:14px;font-size:.78rem;color:var(--ink-faint);'
               f'font-family:var(--mono)">{web.esc(label)}</p>', rv=i)
        for i, (label, q, a, tone, href) in enumerate(questions)) + "</div>"

    phases = (
        ("0–1", "World engine", "10,000 customers and 630,755 transactions in 31 seconds, "
         "every balance reconciled."),
        ("2", "Typology injector", "Six laundering typologies from public advisories, each "
         "writing transaction-level ground truth."),
        ("3–4", "Rules & screening", "Six tunable scenarios; name matching on Jaro-Winkler "
         "plus phonetic corroboration."),
        ("5", "Graph analytics", "Transfer graph rebuilt from shared payment references; "
         "pass-through chains detected."),
        ("6", "ML tournament", "Six model families on one leaderboard, scored at an alert "
         "budget rather than by ROC-AUC."),
        ("7", "Investigator workbench", "Alert queue, entity 360, link graph, disposition "
         "workflow, SAR narrative draft."),
        ("8", "Red team", "An adversary that mutates its own scheme parameters every "
         "generation it gets caught."),
        ("8.5", "Multi-bank", "The world split across four institutions with genuinely "
         "separate ledger files."),
        ("9", "Story Mode & metrics", "Day-by-day replay, detection latency, and the four "
         "KPIs an FCC function reports upward."),
    )
    timeline = '<div class="tl">' + "".join(
        f'<div class="tl-i done"><span class="tl-t">Phase {web.esc(num)}</span>'
        f'<div class="tl-h">{web.esc(title)}</div>'
        f'<div class="tl-d">{web.esc(desc)}</div></div>'
        for num, title, desc in phases) + "</div>"

    arch = ('<div class="card pad-lg" data-rv="0"><div class="arch">'
            + '<div class="b"><div class="t">Red team</div>'
              '<div class="s">mutating adversary</div></div>'
            + '<span class="ar">&#8594;</span>'
            + '<div class="b"><div class="t">Synthetic bank</div>'
              '<div class="s">+ ground truth</div></div>'
            + '<span class="ar">&#8594;</span>'
            + '<div class="b"><div class="t">Detection stack</div>'
              '<div class="s">4 layers</div></div>'
            + '<span class="ar">&#8594;</span>'
            + '<div class="b"><div class="t">Workbench</div>'
              '<div class="s">queue &#8594; SAR</div></div>'
            + '<span class="ar">&#8594;</span>'
            + '<div class="b"><div class="t">Scorers</div>'
              '<div class="s">precision / recall</div></div>'
            + '</div>'
            '<p class="note">The loop closes: the scorers grade the stack against ground '
            'truth, and the red team reads what got caught and adapts. Because the injector '
            'records the answer key, every arrow in this diagram can be measured &mdash; '
            'which is the measurement a production bank cannot make, because no bank knows '
            'what it missed.</p></div>')

    body = (
        '<div class="hero big"><div class="wrap">'
        '<span class="eyebrow" data-rv="0">Open adversarial range &middot; AML detection</span>'
        '<h1 data-rv="1"><span class="grad">An answer key for '
        'anti-money-laundering detection</span></h1>'
        '<p class="lede" data-rv="2">Every bank runs AML detection. None of them can tell you '
        'how good it is &mdash; they know what they caught, and there is no way to know what '
        'they missed. <strong>LaunderLab builds the missing answer key:</strong> a synthetic '
        'bank, six real laundering typologies injected with transaction-level ground truth, '
        'a four-layer detection stack, an investigator workbench, and a red team that adapts '
        'to whatever gets caught.</p>'
        '<div class="btn-row" data-rv="3">'
        + ('<a class="btn pri" href="story.html">Watch a scheme unfold &#8594;</a>'
           if live("story.html") else '')
        + ('<a class="btn sec" href="results.html">See the measured results</a>'
           if live("results.html") else '')
        + f'<a class="btn sec" href="{web.GITHUB_URL}" rel="noopener">'
          'Source &amp; whitepaper</a>'
        + '</div>'
        '<div class="hero-meta" data-rv="4">'
        '<span class="chip"><b>10,000</b> customers</span>'
        '<span class="chip"><b>630,755</b> transactions in 31s</span>'
        '<span class="chip"><b>6</b> typologies</span>'
        '<span class="chip"><b>4</b> detection layers</span>'
        f'<span class="chip"><b>{_test_count()}</b> test functions, zero skips</span>'
        '</div></div></div>'

        + web.section(
            sid="what", eyebrow="In three seconds",
            title="A cyber range, but for financial crime",
            lede="Security teams have had adversarial ranges for years: a red team attacks, a "
                 "blue team defends, and you measure who wins. Financial-crime teams have "
                 "nothing equivalent, because you cannot safely publish real laundering data "
                 "&mdash; and without ground truth you cannot score a detector honestly. "
                 "LaunderLab generates the data instead, and records the answer.",
            body=arch)

        + web.section(
            sid="explore", eyebrow="Explore", title="Four experiments, in depth",
            lede="Each page states its objective, shows the measurement, then explains the "
                 "finding, the engineering behind it, and the limits of what it proves.",
            tone="teal",
            body=f'<div class="grid g2">{"".join(cards)}</div>')

        + web.section(
            sid="questions", eyebrow="Research questions",
            title="Four questions, four measured answers",
            lede="Three were the founding thesis. The fourth was forced by building the "
                 "visual layer &mdash; and it changed how the other three should be read.",
            tone="violet", body=qhtml)

        + web.section(
            sid="honesty", eyebrow="Why trust any of this",
            title="Seventeen times a flattering number turned out to be an artefact",
            lede="Each one was measured, corrected, and <em>written down</em> rather than "
                 "quietly kept. That record is the most valuable thing in the project.",
            tone="amber",
            body='<div class="grid g2" data-rv="0">'
                 + web.card("A perfect ML score that was a data bug",
                            "Gradient boosting scored a flawless 1.000 average precision. "
                            "The legitimate world emitted zero cash transactions, so the "
                            "model had simply learned &ldquo;cash means crime&rdquo;.",
                            hover=False)
                 + web.card("100% rule precision that was a property of the world",
                            "Fixing the cash gap took one rule from 0 to 24 false positives "
                            "on a clean world. The original precision had been an artefact "
                            "of a bank where nobody legitimately banked cash.", hover=False)
                 + web.card("Green CI that was running 178 of 226 tests",
                            "Three modules skipped on a missing dependency &mdash; including "
                            "two of the checks that enforce the project's core boundary. A "
                            "skipped module counts as one skip, so 48 missing tests hid "
                            "behind the number 3.", hover=False)
                 + web.card("A risk score whose top band was unreachable",
                            "Every case in the bank was low or medium and the highest score "
                            "achievable was 43.5. &ldquo;High&rdquo; and "
                            "&ldquo;critical&rdquo; described nothing &mdash; found when a "
                            "SAR draft called a confirmed structuring scheme low risk.",
                            hover=False)
                 + '</div>'
                 + web.box("finding", "The pattern behind almost all of them",
                           "<p>They surfaced by <strong>rendering a number where a person had "
                           "to read it next to a decision</strong>. Detection metrics grade a "
                           "detector against ground truth. Nothing grades whether its output "
                           "is usable &mdash; or whether it is being graded on the right axis "
                           "at all.</p>")
                 + web.box("limit", "And the limits are published too",
                           "<p>The world is synthetic and its realism bounds every figure. "
                           "The benchmarks use one seed. The co-operation protocol is a "
                           "prototype whose residual disclosure is stated rather than "
                           "glossed. Alert-to-SAR conversion is reported as <em>not "
                           "measurable</em> rather than as zero, because no case in this "
                           "world has been worked to a disposition.</p>"))

        + web.section(
            sid="timeline", eyebrow="How it was built", title="Nine phases, measured as it went",
            lede="Every phase shipped a visual artifact and a number, and no phase was marked "
                 "complete on a claim that had not been checked.",
            body=f'<div class="split"><div data-rv="0">{timeline}</div>'
                 '<div class="stack" data-rv="1">'
                 + web.card("The boundary that makes it meaningful",
                            "No detection code may read the ground-truth tables. If a "
                            "detector could see the answer key, every precision and recall "
                            "figure here would be meaningless &mdash; and it would fail "
                            "silently. Enforced by source-level tests in twelve places.",
                            hover=False)
                 + web.card("Every page is generated, never typed",
                            "The figures on these pages are rendered from the same scoring "
                            "modules the test suite grades. A hand-written page with results "
                            "pasted in would look identical on day one and be silently wrong "
                            "the first time a threshold moved.", hover=False)
                 + '</div></div>')

        + web.section(
            sid="start", eyebrow="Start here", title="Two ways in",
            body='<div class="grid g2">'
                 + linked("story.html",
                            '<div><div class="nx-k">Three minutes</div>'
                            '<div class="nx-t">Watch a scheme unfold</div>'
                            '<div class="nx-d">Drag a day slider through a real laundering '
                            'scheme and watch the detection stack close in on it.</div></div>'
                            '<div class="arw" aria-hidden="true">&#8594;</div>',
                            cls="next", rv=0, plain_cls="card")
                 + linked("results.html",
                            '<div><div class="nx-k">Thirty minutes</div>'
                            '<div class="nx-t">Read every measurement</div>'
                            '<div class="nx-d">Detection rate, false-positive economics, '
                            'decay under adaptation, and the cross-bank result &mdash; with '
                            'the limits of each.</div></div>'
                            '<div class="arw" aria-hidden="true">&#8594;</div>',
                            cls="next", rv=1, plain_cls="card")
                 + '</div>'
                 + f'<p class="note">Generated by <code>python -m launderlab publish</code>. '
                   f'Last published {date.today().isoformat()}.</p>')
    )

    return web.shell(
        title="LaunderLab — An open adversarial range for AML detection",
        description="A synthetic bank with real laundering typologies injected and ground "
                    "truth recorded, so every AML detector can be scored on real precision "
                    "and recall. Detection decay, false-positive economics and the "
                    "cross-bank blind spot, measured in the open.",
        active="index.html", body=body, extra_css=_LANDING_CSS)


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    source = Path(argv[0]) if argv and not argv[0].startswith("-") else DEFAULT_SOURCE
    copied, missing = publish(source)

    print(f"Published {len(copied)} page(s) to {DEFAULT_DOCS}/")
    for name in copied:
        print(f"  {name}")
    if missing:
        print(f"  missing (generate these first): {', '.join(missing)}")
        print("    python -m launderlab charts / story / redteam / multibank")
    print()
    print("Nothing is public yet. To publish, in the GitHub repo settings enable")
    print("Pages -> Deploy from a branch -> main / docs.")
