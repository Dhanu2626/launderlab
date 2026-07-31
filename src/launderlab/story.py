"""Story Mode — watch a scheme run, and watch the detection stack close in on it.

Everything before this phase reports detection as a *number*: 86.1% recall, 65.3%
precision, 15/15 chains. Those are the right numbers and they are honestly
measured, but a number is the end of an argument, not the start of one. Someone
who has never opened a ledger cannot read "86.1% recall" and see a crime being
committed. This module is the part of the project that shows them.

    python -m launderlab story          # writes charts/story.html

WHAT IT MEASURES, AND IT IS NEW. Every detection figure this project has produced
so far was computed against the *finished* world -- all 39 days of it, scored
once at the end. That silently assumes the bank is allowed to wait until the
crime is over before deciding it happened. Real monitoring runs nightly against
the ledger *so far*, so the question an FCC team actually asks is not "was it
caught" but "how long did it run first". Nothing here had ever answered that.

So this module replays each day: it points the UNMODIFIED detectors at a view of
the ledger truncated to that day and records the first day each one fires. The
gap between the scheme's first transaction and that day is **detection latency**,
in days, per scheme. Two properties make the number trustworthy:

* the detectors are the real ones. `rules.run_all` and `motifs.find_chains` run
  exactly as they do everywhere else -- there is no second, day-aware copy of a
  rule's logic that could drift from the one being graded. The truncation is a
  DuckDB view named `transactions` shadowing the real table via `search_path`, so
  the SQL a rule already contains does the filtering for free.
* it can under-report but never over-report. A rule that never fires reports no
  latency at all rather than a flattering one.

WHY RULES AND GRAPH ONLY, stated rather than glossed. Screening asks an identity
question -- a customer is on a watchlist on day 0 and on day 39, so "when did it
fire" has no meaning for it. The ML layer emits a ranking, not an event, and
re-fitting an unsupervised model 39 times would measure the model's day-to-day
instability rather than the scheme's visibility. Phase 8 drew the same boundary
for the same reason.

BOUNDARY. This module reads `scheme_labels`, and that is its job: it exists to
show ground truth next to what detection actually said. It sits on the scoring
side of the project's boundary rule, alongside `*/scoring.py`, `evaluate.py` and
`viz.py`. The load-bearing invariant is the *other* direction, and it has its own
test: **the caught side must come from the detectors, never from the labels.**
Colouring an account "detected" because it appears in `scheme_labels` would
render a beautiful animation of a detection that never happened -- which is
exactly the class of flattering artefact §7 of HANDOFF.md is a list of.
"""

from __future__ import annotations

import html
import json
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import duckdb

from launderlab.detect import rules
from launderlab.graph import build as graph_build
from launderlab.graph import motifs
from launderlab.viz import DEFAULT_OUT, bar_chart, page

# The schema whose `transactions` view shadows the real table while replaying.
_REPLAY_SCHEMA = "replay"

# `find_chains` is not a rule and has no rule name, but it is the only detector
# that can assert a *path*, so the story needs to name it distinctly.
GRAPH_DETECTOR = "pass_through_chain"


@dataclass(frozen=True)
class Detection:
    """One detector firing on one account, and the first day it could have."""
    layer: str          # "rules" or "graph"
    detector: str       # the rule's function name, or GRAPH_DETECTOR
    account_id: str
    day: date
    detail: str


@dataclass(frozen=True)
class SchemeStory:
    """One injected scheme, its own transactions, and what detection made of it."""
    scheme_id: str
    typology: str
    accounts: tuple[str, ...]
    names: dict[str, str]
    txns: tuple[dict, ...]
    started: date
    ended: date
    detections: tuple[Detection, ...] = ()
    # Detectors already firing on a scheme account BEFORE the scheme's first
    # transaction. Counting these as a catch would credit the scheme's detection
    # to an alert that predates it -- see `_split_prior`.
    prior: tuple[Detection, ...] = ()
    case_ids: tuple[int, ...] = ()
    bands: tuple[str, ...] = ()

    @property
    def caught_on(self) -> date | None:
        """First day any detector fired *because of* this scheme."""
        return min((d.day for d in self.detections), default=None)

    @property
    def latency_days(self) -> int | None:
        """Days the scheme ran before the stack could see it. None = never seen."""
        caught = self.caught_on
        return None if caught is None else (caught - self.started).days

    @property
    def ran_days(self) -> int:
        return (self.ended - self.started).days + 1

    @property
    def moved_before_alert(self) -> float | None:
        """Share of the scheme's labelled transaction value already posted when
        the first alert fired. None if it was never caught.

        THE NUMBER THAT CHANGES THE CONCLUSION, and latency alone hides it. A
        scheme can be caught quickly and still be caught far too late: `round_trip`
        needs the *return* leg before it can fire and `dormancy_burst` needs the
        cash-out, so both rules are structurally incapable of alerting while any
        of the money is still stoppable. Reporting "caught in 4 days" without this
        would be the flattering half of the truth.

        It is transaction value, not laundered value -- a round trip's departure
        and return are both labelled, so the same money is counted twice. The
        fraction is a fair progress measure through the scheme; the rupee total
        underneath it is not a loss figure and is never presented as one.
        """
        caught = self.caught_on
        if caught is None:
            return None
        total = sum(t["amount"] for t in self.txns)
        if not total:
            return None
        cutoff = caught.isoformat()
        return sum(t["amount"] for t in self.txns if t["day"] <= cutoff) / total

    @property
    def reached_analyst(self) -> bool:
        return bool(self.case_ids)


# --------------------------------------------------------------- the replay

@contextmanager
def replay(conn: duckdb.DuckDBPyConnection):
    """Yield `set_day(day)`, which points bare `transactions` at rows up to `day`.

    The real table is never touched. A view of the same name in an earlier
    `search_path` entry shadows it, so every existing detector -- whose SQL says
    `FROM transactions` and knows nothing about replaying -- filters itself.

    Restoring `search_path` in a `finally` is not defensive tidiness: leaving it
    pointed at the replay schema would silently give every later query in the
    process a truncated world, and a query that reads less than it should is the
    quietest possible kind of wrong.
    """
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_REPLAY_SCHEMA}")

    def set_day(day: date) -> None:
        # `day` is a date derived from the ledger's own timestamps and is
        # formatted to digits and dashes here, so it cannot carry SQL.
        cutoff = (day + timedelta(days=1)).strftime("%Y-%m-%d")
        conn.execute(
            f"CREATE OR REPLACE VIEW {_REPLAY_SCHEMA}.transactions AS"
            f" SELECT * FROM main.transactions WHERE ts < DATE '{cutoff}'")
        conn.execute(f"SET search_path='{_REPLAY_SCHEMA},main'")

    try:
        yield set_day
    finally:
        conn.execute("SET search_path='main'")


def first_fired(conn: duckdb.DuckDBPyConnection, days: list[date],
                ) -> dict[tuple[str, str], Detection]:
    """(account, detector) -> the first day that detector fired on that account.

    One pass over the calendar, not one pass per scheme: the detectors run
    bank-wide anyway, so every scheme's answer falls out of the same sweep.
    """
    seen: dict[tuple[str, str], Detection] = {}

    with replay(conn) as set_day:
        for day in days:
            set_day(day)

            for alert in rules.run_all(conn):
                seen.setdefault(
                    (alert.account_id, alert.rule),
                    Detection("rules", alert.rule, alert.account_id, day, alert.reason))

            for chain in motifs.find_chains(graph_build.build_graph(conn)):
                detail = (f"{chain.hops}-hop pass-through chain, "
                          f"{chain.retained:.0%} of the entry amount retained")
                for account_id in chain.accounts:
                    seen.setdefault(
                        (account_id, GRAPH_DETECTOR),
                        Detection("graph", GRAPH_DETECTOR, account_id, day, detail))

    return seen


def _split_prior(hits: list[Detection], started: date,
                 ) -> tuple[tuple[Detection, ...], tuple[Detection, ...]]:
    """Separate detections the scheme caused from ones that predate it.

    A scheme is injected into an account that already has a life. A business
    running `counterparty_concentration` before a shell scheme lands on it was
    already alerting, and crediting that alert to the scheme would report a
    negative latency dressed up as instant detection.
    """
    caused = tuple(sorted((d for d in hits if d.day >= started),
                          key=lambda d: (d.day, d.detector, d.account_id)))
    prior = tuple(sorted((d for d in hits if d.day < started),
                         key=lambda d: (d.day, d.detector, d.account_id)))
    return caused, prior


# ------------------------------------------------------------ assembling it

def _scheme_rows(conn: duckdb.DuckDBPyConnection) -> dict[str, list[dict]]:
    """Every labelled transaction, by scheme. The answer key, read once."""
    rows = conn.execute(
        "SELECT l.scheme_id, l.typology, l.role, t.txn_id, t.account_id, t.ts,"
        " t.direction, t.channel, t.amount::DOUBLE, t.counterparty_name, t.narration"
        " FROM scheme_labels l JOIN transactions t USING (txn_id)"
        " ORDER BY l.scheme_id, t.ts, t.txn_id").fetchall()

    by_scheme: dict[str, list[dict]] = {}
    for (scheme_id, typology, role, txn_id, account_id, ts, direction,
         channel, amount, counterparty, narration) in rows:
        by_scheme.setdefault(scheme_id, []).append({
            "typology": typology, "role": role, "txn_id": txn_id,
            "account_id": account_id, "ts": ts, "day": ts.date().isoformat(),
            "direction": direction, "channel": channel, "amount": amount,
            "counterparty": counterparty, "narration": narration,
        })
    return by_scheme


def _names_and_cases(conn: duckdb.DuckDBPyConnection, accounts: set[str],
                     ) -> tuple[dict[str, str], dict[str, list[tuple[int, str]]]]:
    if not accounts:
        return {}, {}
    ids = sorted(accounts)
    marks = ",".join("?" * len(ids))
    names = dict(conn.execute(
        "SELECT a.account_id, c.full_name FROM accounts a JOIN customers c"
        f" USING (customer_id) WHERE a.account_id IN ({marks})", ids).fetchall())

    cases: dict[str, list[tuple[int, str]]] = {}
    for account_id, case_id, band in conn.execute(
            "SELECT account_id, case_id, risk_band FROM cases"
            f" WHERE account_id IN ({marks}) ORDER BY case_id", ids).fetchall():
        cases.setdefault(account_id, []).append((case_id, band))
    return names, cases


def build_stories(conn: duckdb.DuckDBPyConnection,
                  limit_per_typology: int | None = None) -> list[SchemeStory]:
    """Assemble every injected scheme with what the real detectors made of it."""
    by_scheme = _scheme_rows(conn)
    if not by_scheme:
        return []

    span = conn.execute("SELECT min(ts)::DATE, max(ts)::DATE FROM transactions").fetchone()
    days = []
    day, last = span[0], span[1]
    while day <= last:
        days.append(day)
        day += timedelta(days=1)

    fired = first_fired(conn, days)
    all_accounts = {row["account_id"] for rows in by_scheme.values() for row in rows}
    names, cases = _names_and_cases(conn, all_accounts)

    stories: list[SchemeStory] = []
    for scheme_id, rows in by_scheme.items():
        accounts = tuple(dict.fromkeys(row["account_id"] for row in rows))
        started = date.fromisoformat(rows[0]["day"])
        ended = date.fromisoformat(rows[-1]["day"])
        hits = [d for (account_id, _det), d in fired.items() if account_id in accounts]
        caused, prior = _split_prior(hits, started)
        case_rows = [pair for a in accounts for pair in cases.get(a, [])]

        stories.append(SchemeStory(
            scheme_id=scheme_id, typology=rows[0]["typology"], accounts=accounts,
            names={a: names.get(a, a) for a in accounts},
            txns=tuple(rows), started=started, ended=ended,
            detections=caused, prior=prior,
            case_ids=tuple(c for c, _ in case_rows),
            bands=tuple(b for _, b in case_rows),
        ))

    stories.sort(key=lambda s: (s.typology, s.scheme_id))
    if limit_per_typology is not None:
        kept: dict[str, int] = {}
        stories = [s for s in stories
                   if kept.setdefault(s.typology, 0) < limit_per_typology
                   and not kept.update({s.typology: kept[s.typology] + 1})]
    return stories


# --------------------------------------------------------------- the numbers

def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return (float(ordered[mid]) if len(ordered) % 2
            else (ordered[mid - 1] + ordered[mid]) / 2)


@dataclass(frozen=True)
class LatencyReport:
    """Detection latency across every scheme, by typology."""
    by_typology: dict[str, list[int]] = field(default_factory=dict)
    never_caught: dict[str, int] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    moved: dict[str, list[float]] = field(default_factory=dict)

    @property
    def median_days(self) -> dict[str, float]:
        return {t: _median(v) for t, v in self.by_typology.items() if v}

    @property
    def median_moved(self) -> dict[str, float]:
        """Median share of a scheme already posted when its first alert fired."""
        return {t: _median(v) for t, v in self.moved.items() if v}


def latency_report(stories: list[SchemeStory]) -> LatencyReport:
    by_typology: dict[str, list[int]] = {}
    never: dict[str, int] = {}
    totals: dict[str, int] = {}
    moved: dict[str, list[float]] = {}
    for story in stories:
        totals[story.typology] = totals.get(story.typology, 0) + 1
        by_typology.setdefault(story.typology, [])
        never.setdefault(story.typology, 0)
        moved.setdefault(story.typology, [])
        if story.latency_days is None:
            never[story.typology] += 1
        else:
            by_typology[story.typology].append(story.latency_days)
            share = story.moved_before_alert
            if share is not None:
                moved[story.typology].append(share)
    return LatencyReport(by_typology=by_typology, never_caught=never,
                         totals=totals, moved=moved)


def exposure_chart(report: LatencyReport) -> tuple[str, str]:
    """How much of a scheme had already moved by the time anything fired.

    Deliberately its own chart rather than a second series on the latency one:
    they are different units (days against a share) and, more importantly, they
    disagree — the typology caught fastest in days is among the worst here, and
    a viewer has to be able to see that rather than have it averaged away.
    """
    medians = report.median_moved
    rows = sorted(((f"{t}  n={len(report.moved[t])}", v) for t, v in medians.items()),
                  key=lambda r: r[1], reverse=True)
    svg = bar_chart(rows, maximum=1.0)
    note = ("Median share of a scheme's labelled transaction value that had already "
            "posted on the day its first alert fired. A short bar is a scheme "
            "caught with money still stoppable; a full bar is an alert that could "
            "only ever arrive after the fact. Three rules are structurally "
            "incapable of firing earlier — round_trip needs the return leg and "
            "dormancy_burst needs the cash-out, so the evidence they require does "
            "not exist until the scheme has completed. That is a property of the "
            "detection design, not a tuning mistake, and no threshold fixes it. "
            "This counts transaction value, so a round trip's departure and return "
            "are both included; it measures progress through a scheme, not loss.")
    return svg, note


def latency_chart(report: LatencyReport) -> tuple[str, str]:
    """Median days from a scheme's first transaction to its first alert."""
    medians = report.median_days
    rows = []
    for typology in sorted(report.totals):
        caught = len(report.by_typology.get(typology, []))
        total = report.totals[typology]
        if typology in medians:
            rows.append((f"{typology}  {caught}/{total} caught", medians[typology]))
        else:
            rows.append((f"{typology}  0/{total} caught", 0.0))
    rows.sort(key=lambda r: r[1], reverse=True)

    svg = bar_chart(rows, fmt="{:.1f}d")
    never_total = sum(report.never_caught.values())
    note = ("Median days from a scheme's first transaction to the first day any "
            "detector could have fired on it, measured by re-running the real "
            "rules engine and graph detector against the ledger truncated to each "
            "day. A zero-length bar means no scheme of that typology was ever "
            f"caught, not that it was caught instantly — {never_total} of "
            f"{sum(report.totals.values())} schemes were never seen at all. "
            "Screening and ML are excluded: one answers an identity question that "
            "has no firing day, the other emits a ranking rather than an event.")
    return svg, note


# --------------------------------------------------------------- the page

def _story_json(story: SchemeStory) -> dict:
    """The shape the page's JavaScript reads. Dates as ISO strings throughout."""
    return {
        "scheme_id": story.scheme_id,
        "typology": story.typology,
        "accounts": list(story.accounts),
        "names": story.names,
        "started": story.started.isoformat(),
        "ended": story.ended.isoformat(),
        "ran_days": story.ran_days,
        # Built here rather than by Date arithmetic in the browser: `setDate`
        # steps in LOCAL time while `toISOString` reads back UTC, so across a
        # DST boundary a 23-hour step lands on the same UTC date twice and the
        # scrubber silently repeats a day. Python has the real dates already.
        "calendar": [(story.started + timedelta(days=i)).isoformat()
                     for i in range(story.ran_days)],
        "latency": story.latency_days,
        "moved_before_alert": story.moved_before_alert,
        "caught_on": story.caught_on.isoformat() if story.caught_on else None,
        "cases": [{"case_id": c, "band": b}
                  for c, b in zip(story.case_ids, story.bands)],
        "txns": [{"day": t["day"], "account_id": t["account_id"],
                  "direction": t["direction"], "channel": t["channel"],
                  "amount": t["amount"], "role": t["role"],
                  "counterparty": t["counterparty"] or "", "narration": t["narration"]}
                 for t in story.txns],
        "detections": [{"layer": d.layer, "detector": d.detector,
                        "account_id": d.account_id, "day": d.day.isoformat(),
                        "detail": d.detail} for d in story.detections],
        "prior": [{"layer": d.layer, "detector": d.detector,
                   "account_id": d.account_id, "day": d.day.isoformat(),
                   "detail": d.detail} for d in story.prior],
    }


def most_illustrative(stories: list[SchemeStory]) -> int:
    """Index of the scheme the page should open on.

    Found by looking at the rendered page rather than by a failing test, which
    is how 7.4, 7.5 and 7.8b were all found too. Sorted by typology, the first
    scheme is a `dormant_reactivation` that runs for ONE day — so the page
    loaded with a slider that had a single position and nothing to scrub, and
    the one feature the page exists for appeared broken on arrival.

    So prefer a scheme that runs long enough to scrub AND is caught partway
    through, because that is the only case where dragging the slider shows the
    transition from undetected to detected actually happening.
    """
    def rank(story: SchemeStory) -> tuple[bool, int]:
        mid_scheme = (story.latency_days is not None
                      and 0 < story.latency_days < story.ran_days)
        return (mid_scheme, story.ran_days)

    return max(range(len(stories)), key=lambda i: rank(stories[i]))


_STORY_CSS = """
.picker { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 18px; }
.picker button { font:inherit; font-size:12.5px; padding:5px 10px; cursor:pointer;
  background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:6px; }
.picker button.on { background:var(--bar); border-color:var(--bar); color:#fff; }
.scrub { display:flex; align-items:center; gap:12px; margin:4px 0 14px; }
.scrub input { flex:1; }
.day { font-variant-numeric:tabular-nums; font-weight:600; min-width:200px; }
.flow { display:flex; align-items:stretch; gap:8px; overflow-x:auto; padding:4px 0; }
.node { flex:0 0 auto; min-width:150px; border:1px solid var(--line); border-radius:8px;
  padding:8px 10px; background:var(--bg); }
.node.lit { border-color:var(--warn); box-shadow:0 0 0 2px color-mix(in srgb,var(--warn) 25%,transparent); }
.node .who { font-size:12.5px; font-weight:600; }
.node .id { font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
.node .amt { font-size:12px; margin-top:4px; font-variant-numeric:tabular-nums; }
.arrow { flex:0 0 auto; align-self:center; color:var(--muted); font-size:18px; }
.det { display:flex; gap:8px; align-items:baseline; padding:5px 0;
  border-bottom:1px solid var(--line); font-size:13px; }
.det:last-child { border-bottom:0; }
.det .pill { flex:0 0 auto; font-size:11px; padding:1px 7px; border-radius:99px;
  border:1px solid var(--line); color:var(--muted); }
.det.fired .pill { background:var(--warn); border-color:var(--warn); color:#fff; }
.det .what { font-weight:600; }
.det .why { color:var(--muted); }
table.txns { border-collapse:collapse; width:100%; font-size:12.5px;
  font-variant-numeric:tabular-nums; }
table.txns th { text-align:left; color:var(--muted); font-weight:500;
  border-bottom:1px solid var(--line); padding:4px 8px 4px 0; }
table.txns td { padding:3px 8px 3px 0; border-bottom:1px solid var(--line); }
table.txns td.dr { color:var(--warn); } table.txns td.cr { color:var(--bar2); }
.stat { display:flex; flex-wrap:wrap; gap:22px; margin:2px 0 14px; }
.stat div { font-size:12.5px; color:var(--muted); }
.stat b { display:block; font-size:17px; color:var(--ink); font-variant-numeric:tabular-nums; }
"""

_STORY_JS = """
const fmt = n => 'Rs ' + Math.round(n).toLocaleString('en-IN');

let current = STORIES[0], calendar = [], at = 0;

function pick(i) {
  current = STORIES[i]; calendar = current.calendar; at = calendar.length - 1;
  document.querySelectorAll('.picker button').forEach((b,j) => b.classList.toggle('on', i===j));
  const slider = document.getElementById('scrub');
  slider.max = calendar.length - 1; slider.value = at;
  draw();
}

function draw() {
  const s = current, today = calendar[at];
  const upto = s.txns.filter(t => t.day <= today);
  document.getElementById('day').textContent =
    today + '  (day ' + (at+1) + ' of ' + calendar.length + ')';

  const moved = upto.reduce((a,t) => a + t.amount, 0);
  document.getElementById('stats').innerHTML =
    '<div><b>' + s.scheme_id + '</b>' + s.typology + '</div>' +
    '<div><b>' + upto.length + ' / ' + s.txns.length + '</b>labelled transactions</div>' +
    '<div><b>' + fmt(moved) + '</b>moved so far</div>' +
    '<div><b>' + (s.latency === null ? 'never' : s.latency + ' days')
      + '</b>ran before first alert</div>' +
    '<div><b>' + (s.moved_before_alert === null ? '—'
      : Math.round(s.moved_before_alert * 100) + '%')
      + '</b>had moved by then</div>';

  // Nodes light up only when a REAL detector has fired on them by `today`.
  const lit = new Set(s.detections.filter(d => d.day <= today).map(d => d.account_id));
  document.getElementById('flow').innerHTML = s.accounts.map((a, i) => {
    const mine = upto.filter(t => t.account_id === a);
    const cr = mine.filter(t => t.direction === 'CR').reduce((x,t) => x+t.amount, 0);
    const dr = mine.filter(t => t.direction === 'DR').reduce((x,t) => x+t.amount, 0);
    return (i ? '<div class="arrow">&#8594;</div>' : '') +
      '<div class="node' + (lit.has(a) ? ' lit' : '') + '">' +
      '<div class="who">' + (s.names[a] || a) + '</div>' +
      '<div class="id">' + a + '</div>' +
      '<div class="amt">in ' + fmt(cr) + '</div>' +
      '<div class="amt">out ' + fmt(dr) + '</div></div>';
  }).join('');

  const rows = s.detections.map(d => {
    const fired = d.day <= today;
    return '<div class="det' + (fired ? ' fired' : '') + '">' +
      '<span class="pill">' + (fired ? d.day : 'day ' + d.day) + '</span>' +
      '<span><span class="what">' + d.detector + '</span> on ' + d.account_id +
      '<br><span class="why">' + d.detail + '</span></span></div>';
  });
  document.getElementById('dets').innerHTML = rows.length ? rows.join('') :
    '<p class="note">No detector ever fired on this scheme. It ran to completion unseen.</p>';

  const seats = s.cases.length
    ? s.cases.map(c => 'case #' + c.case_id + ' (' + c.band + ' band)').join(', ')
    : 'never reached an analyst';
  document.getElementById('outcome').textContent = 'Outcome: ' + seats + '.';
  if (s.prior.length) {
    document.getElementById('prior').innerHTML = '<p class="note">' + s.prior.length +
      ' detector hit(s) on these accounts predate the scheme and are excluded from ' +
      'the latency above: ' + s.prior.map(d => d.detector + ' on ' + d.account_id +
      ' (' + d.day + ')').join(', ') + '.</p>';
  } else { document.getElementById('prior').innerHTML = ''; }

  document.getElementById('txns').innerHTML =
    '<tr><th>day</th><th>account</th><th>dir</th><th>channel</th>' +
    '<th>amount</th><th>role</th><th>narration</th></tr>' +
    upto.slice().reverse().map(t => '<tr><td>' + t.day + '</td><td>' + t.account_id +
      '</td><td class="' + t.direction.toLowerCase() + '">' + t.direction +
      '</td><td>' + t.channel + '</td><td>' + fmt(t.amount) + '</td><td>' +
      (t.role || '') + '</td><td>' + t.narration + '</td></tr>').join('');
}

document.getElementById('scrub').addEventListener('input', e => {
  at = +e.target.value; draw();
});
document.querySelectorAll('.picker button').forEach((b, i) =>
  b.addEventListener('click', () => pick(i)));
pick(OPEN_ON);
"""


def render(conn: duckdb.DuckDBPyConnection, out_dir: Path = DEFAULT_OUT,
           limit_per_typology: int | None = 3) -> Path:
    """Write Story Mode as one self-contained page. Returns its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stories = build_stories(conn, limit_per_typology=limit_per_typology)

    if not stories:
        body = ('<p class="note warn">No injected schemes in this ledger, so there is '
                "no story to tell. Build a world with crime in it first: "
                "<code>python -m launderlab demo-world</code>.</p>")
        path = out_dir / "story.html"
        path.write_text(page("LaunderLab — Story Mode", "", body), encoding="utf-8")
        return path

    report = latency_report(build_stories(conn, limit_per_typology=None))
    svg, note = latency_chart(report)
    exposure_svg, exposure_note = exposure_chart(report)

    buttons = "".join(
        f'<button type="button">{html.escape(s.scheme_id)} · '
        f'{html.escape(s.typology)}</button>' for s in stories)
    payload = json.dumps([_story_json(s) for s in stories])

    body = (
        f'<div class="picker">{buttons}</div>'
        '<div class="card">'
        '<div class="stat" id="stats"></div>'
        '<div class="scrub"><span class="day" id="day"></span>'
        '<input type="range" id="scrub" min="0" value="0" step="1"></div>'
        '<div class="flow" id="flow"></div>'
        '</div>'
        '<h2>What the detection stack saw</h2>'
        '<div class="card" id="dets"></div>'
        '<p class="note" id="outcome"></p><div id="prior"></div>'
        '<h2>The scheme\'s own transactions, up to the day above</h2>'
        '<div class="card"><table class="txns" id="txns"></table></div>'
        '<h2>Detection latency — how long a scheme runs before anything fires</h2>'
        f'<div class="card">{svg}</div>'
        f'<p class="note">{html.escape(note)}</p>'
        '<h2>How much had already moved when the alert fired</h2>'
        f'<div class="card">{exposure_svg}</div>'
        f'<p class="note">{html.escape(exposure_note)}</p>'
        f"<script>const STORIES = {payload};"
        f"const OPEN_ON = {most_illustrative(stories)};{_STORY_JS}</script>"
    )
    subtitle = ("Scrub the day slider to replay a real injected scheme. An account "
                "outlines in red only when a real detector has actually fired on it "
                "by that day — never because it is in the answer key. Regenerate with "
                "<code>python -m launderlab story</code>.")

    path = out_dir / "story.html"
    path.write_text(page("LaunderLab — Story Mode", subtitle, body,
                         extra_css=_STORY_CSS), encoding="utf-8")
    return path


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    from launderlab.db.ledger import connect_configured

    out = Path(argv[0]) if argv and not argv[0].startswith("-") else DEFAULT_OUT
    conn = connect_configured()
    try:
        stories = build_stories(conn, limit_per_typology=None)
        report = latency_report(stories)
        path = render(conn, out)
    finally:
        conn.close()

    print(f"Story Mode written to {path}")
    moved = report.median_moved
    for typology in sorted(report.totals):
        caught = len(report.by_typology.get(typology, []))
        total = report.totals[typology]
        median = report.median_days.get(typology)
        if median is None:
            print(f"  {typology:<22} 0/{total} caught, never detected")
            continue
        # Both numbers together or neither: "caught in 4 days" reads as a success
        # until you see that all of the money had already moved by then.
        print(f"  {typology:<22} {caught}/{total} caught, median {median:.1f}d to "
              f"first alert, {moved.get(typology, 0):.0%} of it already moved by then")
    if "--no-open" not in argv:
        webbrowser.open(path.resolve().as_uri())
