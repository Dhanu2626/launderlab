"""Collect the generated pages into `docs/` so a reader can actually see them.

    python -m launderlab publish

THE GAP THIS CLOSES. `charts/` is gitignored, deliberately: those pages are
derived artifacts and regenerating them is one command. But the audience Story
Mode was built for -- someone who will never clone a repository, install Python
or run a server -- cannot regenerate anything. Until now the project's entire
visual output was invisible to exactly the people it was made for, which is a
strange place for a portfolio piece to end up.

`docs/` is GitHub Pages' conventional publish folder, so committing the pages
there makes them viewable with one setting flipped in the repository, and
nothing is published until a human flips it. That split is on purpose: this
command only writes files into the working tree. It never commits, never pushes
and never touches repository settings.

WHY COPIES AND NOT A SECOND RENDERER. Every page here is written by the module
that owns its measurement (`viz`, `story`). Re-rendering them from a different
entry point would let a published figure drift from the one the scorers grade,
which is the failure this project has corrected four separate times. So this
copies bytes and refuses to invent any.
"""

from __future__ import annotations

import html
import shutil
from datetime import date
from pathlib import Path

DEFAULT_SOURCE = Path("charts")
DEFAULT_DOCS = Path("docs")

# (source name, published name, title, what the page proves)
#
# `charts/index.html` is republished as `charts.html`: `docs/index.html` is the
# landing page every visitor arrives on, and letting both claim that name would
# have one silently overwrite the other.
PAGES = (
    ("story.html", "story.html", "Story Mode",
     "Replay any injected scheme day by day. Accounts light up only on the day a "
     "real detector actually fired on them."),
    ("index.html", "charts.html", "Measured results + operating metrics",
     "Detection rate, precision, queue composition and what the stack costs to "
     "run, all drawn from the scoring modules."),
    ("redteam.html", "redteam.html", "Red team decay benchmark",
     "Recall per typology across 8 generations of an adversary that mutates its "
     "own parameters. Decay is not uniform."),
    ("multibank.html", "multibank.html", "The cross-bank blind spot",
     "Four banks with genuinely separate ledgers. They flag 75-77% of mule "
     "accounts and reconstruct 0-6% of the chains those accounts form."),
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

    docs.joinpath("index.html").write_text(_landing(copied), encoding="utf-8")
    return copied, missing


def _landing(available: list[str]) -> str:
    """The docs/ landing page. Links only to pages that were actually copied.

    A dead link on the one page a recruiter opens is worse than a missing entry,
    and a page that lists what it does not have is at least honest about it.
    """
    from launderlab.viz import page

    cards = []
    for _name, target, title, blurb in PAGES:
        if target in available:
            cards.append(
                f'<a class="card link" href="{target}"><b>{html.escape(title)}</b>'
                f'<span>{html.escape(blurb)}</span></a>')
        else:
            cards.append(
                f'<div class="card link off"><b>{html.escape(title)}</b>'
                f'<span>{html.escape(blurb)}</span>'
                f'<em>not generated yet</em></div>')

    body = (
        '<p class="sub">An open adversarial simulation range for anti-money-laundering '
        "detection: a synthetic bank, an injector that hides real laundering typologies "
        "inside it, a four-layer detection stack, an investigator workbench, a red team "
        "that adapts, and a multi-bank experiment. Because the injector records ground "
        "truth, every detector is scored on real precision and recall.</p>"
        f'<div class="grid">{"".join(cards)}</div>'
        '<p class="note">These pages are generated from a real run and copied here by '
        "<code>python -m launderlab publish</code>. Every figure on them comes from the "
        "project's scoring modules, so a published number cannot drift from the measured "
        f"one. Last published {date.today().isoformat()}.</p>")
    return page("LaunderLab", "", body, extra_css=_LANDING_CSS,
                heading="LaunderLab")


_LANDING_CSS = """
.grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
        margin-top:18px; }
.link { display:block; text-decoration:none; color:inherit; }
.link b { display:block; font-size:15px; margin-bottom:4px; }
.link span { display:block; font-size:12.5px; color:var(--muted); }
.link em { display:block; font-size:12px; color:var(--warn); margin-top:6px; font-style:normal; }
a.link:hover { border-color:var(--bar); }
.link.off { opacity:0.6; }
"""


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
