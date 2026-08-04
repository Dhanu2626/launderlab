"""Contrast and theming guarantees for the published design system.

The rule this file exists to enforce: **switching theme must never cost
readability.** That is easy to say and easy to break — the workbench already
shipped a version where three tier colours were carried unchanged from the light
palette into the dark one and measured 2.8–3.6:1 against the dark background,
well under the 4.5:1 that small text needs, and nobody had looked.

So nobody looks here either. Every ratio is recomputed from the actual CSS on
every run, in both themes, using the WCAG 2.1 formula.
"""

import re

import pytest

web = pytest.importorskip("launderlab.web")

# WCAG 2.1 thresholds. 4.5 is normal text; 3.0 is large text and non-text UI
# (borders, chart fills) — a chart bar is a graphical object, not a paragraph.
AA_TEXT = 4.5
AA_UI = 3.0


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


@pytest.fixture(scope="module")
def themes():
    """The two palettes, parsed from the CSS the pages actually ship."""
    both = {"dark": _tokens(web._DARK), "light": _tokens(web._LIGHT)}
    for name, tok in both.items():
        assert tok, f"{name} palette parsed empty — the token format changed"
    return both


def test_contrast_holds_in_both_themes(themes):
    """The requirement, stated as a measurement.

    Every foreground token is checked against every surface it can legitimately
    sit on. `--ink-faint` is included at full text strength deliberately: it is
    used for KPI detail lines, axis labels and table headers, all of which are
    small text, so the 3.0 large-text allowance does not apply to it. It failed
    this check at 3.88:1 before the light theme existed, and was corrected.
    """
    surfaces = ("bg", "bg-soft", "surface", "surface-2", "surface-3")
    text_tokens = ("ink", "ink-dim", "ink-faint", "accent", "teal", "violet",
                   "amber", "rose", "green", "tier1", "tier2", "tier3", "tier4")

    failures = []
    for theme, tok in themes.items():
        for fg in text_tokens:
            for surface in surfaces:
                if fg not in tok or surface not in tok:
                    continue
                ratio = contrast(tok[fg], tok[surface])
                if ratio < AA_TEXT:
                    failures.append(
                        f"{theme}: --{fg} on --{surface} is {ratio:.2f}:1 "
                        f"(needs {AA_TEXT})")
    assert not failures, "contrast below WCAG AA:\n  " + "\n  ".join(failures)


def test_chart_series_stay_distinguishable_from_the_page(themes):
    """Chart fills are graphical objects, so 3.0 is the bar — but a series that
    vanishes into the background is useless whatever the standard says."""
    failures = []
    for theme, tok in themes.items():
        for series in ("c1", "c2", "c3", "c4", "c5"):
            ratio = contrast(tok[series], tok["bg"])
            if ratio < AA_UI:
                failures.append(f"{theme}: --{series} is {ratio:.2f}:1 on --bg")
    assert not failures, "chart colours too faint:\n  " + "\n  ".join(failures)


def test_text_on_the_accent_colour_is_readable_in_both_themes(themes):
    """Buttons and the skip link put text ON the accent, not next to it.

    Near-black reads on the bright dark-theme blue and fails on the darker
    light-theme blue, which is exactly why `--on-accent` exists rather than a
    hardcoded colour.
    """
    for theme, tok in themes.items():
        ratio = contrast(tok["on-accent"], tok["accent"])
        assert ratio >= AA_TEXT, (
            f"{theme}: --on-accent on --accent is {ratio:.2f}:1")


def test_neither_theme_is_the_other_one_inverted(themes):
    """A carried-over palette is the specific bug this file exists to prevent.

    If the two themes shared a foreground value, one of them was not measured
    against its own background — which is how the workbench shipped three
    unreadable tier colours.
    """
    shared = {k for k in ("ink", "ink-dim", "ink-faint", "accent", "tier1",
                          "tier2", "tier3", "tier4")
              if themes["dark"].get(k) == themes["light"].get(k)}
    assert not shared, f"identical in both themes, so one was never measured: {shared}"


def test_the_tier_ramp_is_warm_and_ordered(themes):
    """Rust → orange → ochre → sand, strongest evidence tier first.

    Checked as hue, not as a literal list of values, so the ramp can be retuned
    without this test becoming a copy of the palette it is supposed to guard.
    """
    for theme, tok in themes.items():
        for tier in ("tier1", "tier2", "tier3", "tier4"):
            h = tok[tier].lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            assert r > b and g > b, (
                f"{theme}: --{tier} {tok[tier]} is not a warm colour "
                "(red and green must both exceed blue)")


def test_every_page_carries_a_working_theme_toggle():
    """It has to be reachable, labelled, and applied before first paint —
    a toggle that flashes the wrong theme on every load is worse than none."""
    page = web.shell(title="t", description="d", active="index.html", body="<p>x</p>")

    assert 'id="themebtn"' in page and "<button" in page
    assert 'aria-label="Switch colour theme"' in page, "the icon needs a name"
    # applied in <head>, before the body renders, so there is no flash
    head = page.split("</head>")[0]
    assert "ll-theme" in head and "data-theme" in head
    assert "localStorage" in page, "the choice must survive a page change"


def test_a_reader_who_never_clicks_still_gets_their_os_preference():
    """The head script deliberately does NOT set an attribute when no choice is
    stored, leaving the media query to decide. That is what makes the site
    respect a light-preferring reader even with JavaScript unavailable."""
    css = web.css()
    assert "@media (prefers-color-scheme: light)" in css
    assert ':root:not([data-theme="dark"])' in css

    # and an explicit choice must still win: it is written later in the sheet,
    # where equal specificity is resolved by source order
    assert css.index(':root:not([data-theme="dark"])') < css.index(':root[data-theme="dark"]')


def test_the_toggle_icon_follows_the_same_cascade_as_the_colours():
    """Found by clicking the real button, not by a test.

    The icon shows the theme you would switch TO. Keyed only off
    `[data-theme="light"]`, it was wrong in exactly one state — a reader whose
    OS asks for light and who has never clicked saw a light page with a
    "switch to light" sun on it, because no attribute is set when following the
    OS. It needs the same four-way cascade the tokens have.
    """
    css = web.css()
    for state in (':root:not([data-theme="dark"]) .themebtn .moon',
                  ':root[data-theme="light"] .themebtn .moon',
                  ':root[data-theme="dark"] .themebtn .sun'):
        assert state in css, f"missing icon rule for: {state}"
    # The OS-following rule must sit inside a light media query, or it would
    # flip the icon for dark readers too. There is more than one such block
    # (tokens and nav), so check every segment rather than assuming the first.
    segments = css.split("@media (prefers-color-scheme: light)")[1:]
    assert any(':root:not([data-theme="dark"]) .themebtn .moon' in seg
               for seg in segments), (
        "the OS-default icon rule is outside any light media query")


def test_no_page_hardcodes_a_colour_that_should_switch(themes):
    """A literal hex in a component rule is a value that cannot follow the
    theme. The nav background, the page wash and the button foreground were all
    hardcoded for dark, and all three broke the moment light existed."""
    components = "".join((web.BASE_CSS, web.NAV_CSS, web.LAYOUT_CSS,
                          web.COMPONENT_CSS, web.CHART_CSS))
    leaked = re.findall(r"#[0-9a-fA-F]{6}", components)
    assert not leaked, (
        f"component CSS must use tokens, not literals: {sorted(set(leaked))}")
