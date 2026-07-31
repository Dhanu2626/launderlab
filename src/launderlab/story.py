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
from launderlab import web
from launderlab.viz import DEFAULT_OUT, bar_chart

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
.stage { display:grid; gap:16px; grid-template-columns:1fr 340px; align-items:start; }
@media (max-width:960px){ .stage { grid-template-columns:1fr; } }
.picker { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:20px; }
.picker button {
  font:inherit; font-size:.8rem; padding:6px 12px; cursor:pointer; color:var(--ink-dim);
  background:var(--surface); border:1px solid var(--line); border-radius:99px;
  transition:background .16s, color .16s, border-color .16s;
}
.picker button:hover { color:var(--ink); border-color:var(--line-strong); }
.picker button.on { background:var(--accent); border-color:var(--accent); color:#04070d;
                    font-weight:600; }
.picker .ty { opacity:.7; }
.scrub { display:flex; align-items:center; gap:16px; margin:2px 0 18px; flex-wrap:wrap; }
.scrub input[type=range] {
  flex:1; min-width:200px; -webkit-appearance:none; appearance:none; height:5px;
  border-radius:99px; background:var(--surface-3); outline:none; cursor:pointer;
}
.scrub input[type=range]::-webkit-slider-thumb {
  -webkit-appearance:none; width:17px; height:17px; border-radius:99px;
  background:var(--accent); border:3px solid var(--bg); cursor:grab;
  box-shadow:0 0 0 1px var(--accent);
}
.scrub input[type=range]::-moz-range-thumb {
  width:14px; height:14px; border-radius:99px; background:var(--accent);
  border:3px solid var(--bg); cursor:grab;
}
.daylab { font-family:var(--mono); font-size:.9rem; color:var(--ink); min-width:210px; }
.daylab .d2 { color:var(--ink-faint); font-size:.76rem; display:block; margin-top:2px;
              font-family:var(--sans); }
.playbtn {
  font:inherit; font-size:.8rem; padding:7px 15px; border-radius:8px; cursor:pointer;
  background:var(--surface-2); color:var(--ink); border:1px solid var(--line-strong);
  transition:background .16s;
}
.playbtn:hover { background:var(--surface-3); }
.flow { display:flex; align-items:stretch; gap:6px; overflow-x:auto; padding:8px 2px 12px; }
.node {
  flex:0 0 auto; min-width:156px; border:1px solid var(--line); border-radius:11px;
  padding:11px 13px; background:var(--surface); position:relative;
  transition:border-color .35s var(--ease), box-shadow .35s var(--ease),
             background .35s var(--ease);
}
.node.lit {
  border-color:var(--rose); background:rgba(248,113,113,.07);
  box-shadow:0 0 0 1px rgba(248,113,113,.28), 0 0 26px -6px rgba(248,113,113,.4);
}
.node .who { font-size:.83rem; font-weight:620; color:var(--ink); line-height:1.35; }
.node .id { font-family:var(--mono); font-size:.7rem; color:var(--ink-faint); margin-top:2px; }
.node .amt { font-family:var(--mono); font-size:.75rem; margin-top:7px; color:var(--ink-dim); }
.node .amt b { color:var(--ink); font-weight:600; }
.node .flag {
  position:absolute; top:-8px; right:9px; font-size:.62rem; font-family:var(--mono);
  background:var(--rose); color:#1a0505; padding:2px 7px; border-radius:99px;
  font-weight:700; opacity:0; transform:translateY(-3px); transition:all .3s var(--ease);
}
.node.lit .flag { opacity:1; transform:none; }
.arrow { flex:0 0 auto; align-self:center; color:var(--ink-faint); font-size:15px; }
.det { display:flex; gap:11px; align-items:flex-start; padding:11px 0;
       border-bottom:1px solid var(--line); }
.det:last-child { border-bottom:0; }
.det .when {
  flex:0 0 auto; font-family:var(--mono); font-size:.67rem; padding:3px 8px;
  border-radius:99px; border:1px solid var(--line); color:var(--ink-faint);
  background:var(--surface-2); white-space:nowrap; transition:all .3s var(--ease);
}
.det.fired .when { background:var(--rose); border-color:var(--rose); color:#1a0505;
                   font-weight:700; }
.det .dw { font-family:var(--mono); font-size:.82rem; font-weight:600; color:var(--ink-dim); }
.det.fired .dw { color:var(--rose); }
.det .dd { font-size:.79rem; color:var(--ink-faint); margin-top:3px; line-height:1.5; }
.narr {
  font-size:.92rem; color:var(--ink-dim); border-left:2px solid var(--accent);
  padding:4px 0 4px 15px; margin:0; line-height:1.62;
}
.narr b { color:var(--ink); }
.susp { display:flex; align-items:center; gap:11px; margin-top:15px; }
.susp .bars { display:flex; gap:4px; flex:1; }
.susp .bars i { height:6px; flex:1; border-radius:99px; background:var(--surface-3);
                transition:background .35s var(--ease); }
.susp .bars i.on { background:var(--amber); }
.susp .bars i.on.hot { background:var(--rose); }
.susp .lab { font-family:var(--mono); font-size:.71rem; color:var(--ink-faint);
             white-space:nowrap; }
/* Both axes explicitly: the cells are nowrap, and relying on the spec's
   "if one axis is not visible the other computes to auto" is a subtlety to
   depend on for whether a table can push the whole card wider than the page. */
.txr { max-height:330px; overflow:auto; }
.txr table { width:100%; border-collapse:collapse; }
.txr th { position:sticky; top:0; background:var(--surface); text-align:left;
          font-size:.66rem; letter-spacing:.07em; text-transform:uppercase;
          color:var(--ink-faint); font-weight:700; padding:7px 10px 7px 0;
          border-bottom:1px solid var(--line); }
.txr td { padding:6px 10px 6px 0; border-bottom:1px solid var(--line);
          color:var(--ink-dim); font-family:var(--mono); font-size:.745rem;
          white-space:nowrap; }
.txr td.dr { color:var(--rose); } .txr td.cr { color:var(--green); }
.txr td.na { font-family:var(--sans); color:var(--ink-dim); white-space:normal; }
.txr tr.new td { animation:rowIn .45s var(--ease) both; }
@keyframes rowIn { from { opacity:0; transform:translateX(-6px); } to { opacity:1; transform:none; } }
.side .card { margin-bottom:14px; }
.side .card:last-child { margin-bottom:0; }
.sh { font-size:.7rem; letter-spacing:.11em; text-transform:uppercase;
      color:var(--ink-faint); font-family:var(--mono); margin:0 0 11px; font-weight:700; }
.kv { display:flex; justify-content:space-between; gap:12px; padding:7px 0;
      border-bottom:1px solid var(--line); font-size:.82rem; }
.kv:last-child { border-bottom:0; }
.kv .k { color:var(--ink-faint); }
.kv .v { color:var(--ink); font-family:var(--mono); text-align:right;
         font-variant-numeric:tabular-nums; }
@media (prefers-reduced-motion:reduce) { .txr tr.new td { animation:none; } }
"""

_STORY_JS = """
(function(){
  var RM = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var fmt = function(n){ return 'Rs ' + Math.round(n).toLocaleString('en-IN'); };
  var cur = STORIES[0], cal = [], at = 0, timer = null, prevRows = -1;
  var $ = function(id){ return document.getElementById(id); };

  function pick(i){
    stop();
    cur = STORIES[i]; cal = cur.calendar; at = cal.length - 1; prevRows = -1;
    document.querySelectorAll('.picker button').forEach(function(b,j){
      b.classList.toggle('on', i === j);
      b.setAttribute('aria-pressed', i === j ? 'true' : 'false');
    });
    var s = $('scrub'); s.max = cal.length - 1; s.value = at;
    $('profile').innerHTML = profile(cur);
    draw();
  }

  function profile(s){
    var rows = [
      ['Scheme', s.scheme_id],
      ['Typology', s.typology],
      ['Accounts', s.accounts.length],
      ['Ran for', s.ran_days + (s.ran_days === 1 ? ' day' : ' days')],
      ['First alert', s.latency === null ? 'never' : 'day ' + (s.latency + 1)],
      ['Reached an analyst', s.cases.length
        ? s.cases.map(function(c){ return '#' + c.case_id + ' (' + c.band + ')'; }).join(', ')
        : 'no']
    ];
    return rows.map(function(r){
      return '<div class="kv"><span class="k">' + r[0] + '</span>' +
             '<span class="v">' + r[1] + '</span></div>';
    }).join('');
  }

  /* The one honest rule of this screen: an account is only ever lit because a
     REAL detector fired on it by the day being viewed -- never because it
     appears in ground truth. It is in ground truth the entire time. */
  function draw(){
    var s = cur, today = cal[at];
    var upto = s.txns.filter(function(t){ return t.day <= today; });
    var fired = s.detections.filter(function(d){ return d.day <= today; });
    var lit = {}; fired.forEach(function(d){ lit[d.account_id] = 1; });

    $('daynum').textContent = today;
    $('dayoff').textContent = 'Day ' + (at + 1) + ' of ' + cal.length + ' \\u00b7 ' +
      upto.length + ' of ' + s.txns.length + ' labelled transactions posted';

    var moved = upto.reduce(function(a,t){ return a + t.amount; }, 0);
    var total = s.txns.reduce(function(a,t){ return a + t.amount; }, 0);
    $('kmoved').textContent = fmt(moved);
    $('kshare').textContent = total ? Math.round(moved / total * 100) + '%' : '0%';
    $('kfired').textContent = fired.length + ' of ' + s.detections.length;

    /* "Evidence" is what the STACK holds -- how many independent detectors have
       fired by today. It is not a new risk score and nothing here reads a label. */
    var n = fired.length, cap = Math.max(s.detections.length, 3), bars = '';
    for (var i = 0; i < cap; i++)
      bars += '<i class="' + (i < n ? 'on' + (n >= 2 ? ' hot' : '') : '') + '"></i>';
    $('suspbars').innerHTML = bars;
    $('susplab').textContent = n === 0 ? 'no signal'
      : (n === 1 ? '1 detector' : n + ' detectors \\u00b7 corroborated');

    $('flow').innerHTML = s.accounts.map(function(a,i){
      var mine = upto.filter(function(t){ return t.account_id === a; });
      var cr = mine.filter(function(t){ return t.direction === 'CR'; })
                   .reduce(function(x,t){ return x + t.amount; }, 0);
      var dr = mine.filter(function(t){ return t.direction === 'DR'; })
                   .reduce(function(x,t){ return x + t.amount; }, 0);
      return (i ? '<div class="arrow">&#8594;</div>' : '') +
        '<div class="node' + (lit[a] ? ' lit' : '') + '">' +
        '<span class="flag">ALERT</span>' +
        '<div class="who">' + (s.names[a] || a) + '</div>' +
        '<div class="id">' + a + '</div>' +
        '<div class="amt">in <b>' + fmt(cr) + '</b></div>' +
        '<div class="amt">out <b>' + fmt(dr) + '</b></div></div>';
    }).join('');

    $('dets').innerHTML = s.detections.length ? s.detections.map(function(d){
      var on = d.day <= today;
      return '<div class="det' + (on ? ' fired' : '') + '">' +
        '<span class="when">' + (on ? d.day : 'pending') + '</span>' +
        '<div><div class="dw">' + d.detector + '</div>' +
        '<div class="dd">' + (on ? d.detail : 'has not fired yet') +
        ' &middot; ' + d.account_id + '</div></div></div>';
    }).join('') : '<p class="dd">No detector ever fired on this scheme. It ran to ' +
      'completion unseen &mdash; and it is in the answer key the whole time.</p>';

    $('narr').innerHTML = narrate(s, today, upto, fired, moved, total);

    var rows = upto.slice().reverse();
    $('txns').innerHTML = '<tr><th>Day</th><th>Account</th><th>Dir</th><th>Channel</th>' +
      '<th>Amount</th><th>Role</th><th>Narration</th></tr>' +
      rows.map(function(t,i){
        var isNew = !RM && prevRows >= 0 && i < rows.length - prevRows;
        return '<tr' + (isNew ? ' class="new"' : '') + '><td>' + t.day + '</td>' +
          '<td>' + t.account_id + '</td>' +
          '<td class="' + t.direction.toLowerCase() + '">' + t.direction + '</td>' +
          '<td>' + t.channel + '</td><td>' + fmt(t.amount) + '</td>' +
          '<td class="na">' + (t.role || '') + '</td>' +
          '<td class="na">' + t.narration + '</td></tr>';
      }).join('');
    prevRows = rows.length;
  }

  /* Narration is assembled only from facts already on this page: the day, what
     has posted, what has fired. It asserts nothing the data does not show. */
  function narrate(s, today, upto, fired, moved, total){
    if (!upto.length)
      return '<b>Nothing has posted yet.</b> The scheme begins on ' + s.started + '.';
    var pct = total ? Math.round(moved / total * 100) : 0, out;
    if (!fired.length) {
      out = '<b>Still invisible.</b> ' + upto.length + ' of ' + s.txns.length +
        ' scheme transactions have posted and <b>' + pct + '%</b> of the value has ' +
        'moved, but no detector has fired. These accounts are in the answer key right ' +
        'now &mdash; the stack simply has no evidence yet.';
      if (s.latency === null)
        out += ' It never will: no detector fires on this scheme at any point.';
    } else if (fired.length === 1 && fired[0].day === today) {
      out = '<b>First alert.</b> <b>' + fired[0].detector + '</b> fires on ' +
        fired[0].account_id + ' today &mdash; day ' + (s.latency + 1) + ' of the scheme. ' +
        '<b>' + pct + '%</b> of the value had already moved by the time the evidence ' +
        'this rule needs came into existence.';
    } else if (fired.length === 1) {
      out = '<b>One detector is holding this case.</b> <b>' + fired[0].detector +
        '</b> fired on ' + fired[0].day + '. A single signal is the weakest kind of ' +
        'case &mdash; it names a scenario, but nothing corroborates it.';
    } else {
      out = '<b>Corroborated.</b> ' + fired.length + ' independent detectors have now ' +
        'fired. Two layers agreeing is what separates a case worth an analyst&rsquo;s ' +
        'day from a single-signal alert.';
    }
    if (pct >= 100 && fired.length)
      out += ' <b>All of the money had already moved</b> &mdash; whatever happens next, ' +
        'nothing here was stoppable.';
    return out;
  }

  function stop(){
    if (timer) { clearInterval(timer); timer = null; $('play').textContent = 'Replay'; }
  }
  function play(){
    if (timer) { stop(); return; }
    if (at >= cal.length - 1) { at = 0; $('scrub').value = 0; draw(); }
    $('play').textContent = 'Pause';
    timer = setInterval(function(){
      if (at >= cal.length - 1) { stop(); return; }
      at++; $('scrub').value = at; draw();
    }, RM ? 10 : 470);
  }

  $('scrub').addEventListener('input', function(e){ stop(); at = +e.target.value; draw(); });
  $('play').addEventListener('click', play);
  document.querySelectorAll('.picker button').forEach(function(b,i){
    b.addEventListener('click', function(){ pick(i); });
  });
  pick(OPEN_ON);
})();
"""


def _stage() -> str:
    """The replay itself: flow, scrubber, narrative, evidence, transactions."""
    return (
        '<div class="stage">'
        '<div>'
        '<div class="card pad-lg" data-rv="0">'
        '<div class="scrub">'
        '<span class="daylab"><span id="daynum">&mdash;</span>'
        '<span class="d2" id="dayoff"></span></span>'
        '<input type="range" id="scrub" min="0" value="0" step="1" '
        'aria-label="Replay day">'
        '<button class="playbtn" id="play" type="button">Replay</button>'
        '</div>'
        '<div class="flow" id="flow"></div>'
        '<div class="susp"><span class="lab">Evidence</span>'
        '<span class="bars" id="suspbars"></span>'
        '<span class="lab" id="susplab"></span></div>'
        '<p class="narr" id="narr" style="margin-top:16px" aria-live="polite"></p>'
        '</div>'
        '<div class="card pad-lg" style="margin-top:14px" data-rv="1">'
        '<p class="sh">Transaction explorer</p>'
        '<div class="txr"><table id="txns"></table></div>'
        '</div></div>'
        '<div class="side" data-rv="1">'
        '<div class="card"><p class="sh">Account profile</p><div id="profile"></div></div>'
        '<div class="card"><p class="sh">Investigation panel</p>'
        '<div class="kv"><span class="k">Value posted</span>'
        '<span class="v" id="kmoved">&mdash;</span></div>'
        '<div class="kv"><span class="k">Share of scheme</span>'
        '<span class="v" id="kshare">&mdash;</span></div>'
        '<div class="kv"><span class="k">Detectors fired</span>'
        '<span class="v" id="kfired">&mdash;</span></div>'
        '</div>'
        '<div class="card"><p class="sh">Detector reasoning</p><div id="dets"></div></div>'
        '</div></div>')


def render(conn: duckdb.DuckDBPyConnection, out_dir: Path = DEFAULT_OUT,
           limit_per_typology: int | None = 3) -> Path:
    """Write Story Mode as one self-contained investigation replay."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "story.html"
    stories = build_stories(conn, limit_per_typology=limit_per_typology)

    if not stories:
        path.write_text(web.shell(
            title="LaunderLab — Story Mode",
            description="Replay an injected money-laundering scheme day by day.",
            active="story.html",
            body=web.hero(
                eyebrow="Story Mode", title="No story to tell",
                lede="This ledger has <strong>no injected schemes</strong> in it, so there "
                     "is nothing to replay.")
            + web.section(
                sid="fix", eyebrow="Fix", title="Build a world with crime in it",
                body=web.box("warn", "Next step",
                             "<p>Run <code>python -m launderlab demo-world</code>, then "
                             "point <code>LAUNDERLAB_DB</code> at it and re-run "
                             "<code>python -m launderlab story</code>.</p>"))),
            encoding="utf-8")
        return path

    everything = build_stories(conn, limit_per_typology=None)
    report = latency_report(everything)
    svg, note = latency_chart(report)
    exposure_svg, exposure_note = exposure_chart(report)

    buttons = "".join(
        f'<button type="button" aria-pressed="false">{html.escape(s.scheme_id)}'
        f'<span class="ty"> · {html.escape(s.typology)}</span></button>' for s in stories)
    payload = json.dumps([_story_json(s) for s in stories], separators=(",", ":"))

    caught = sum(1 for s in everything if s.latency_days is not None)
    medians, moved = report.median_days, report.median_moved
    slowest = max(medians, key=medians.get) if medians else None
    worst = max(moved, key=moved.get) if moved else None

    body = (
        web.hero(
            eyebrow="Story Mode · Phase 9.1", tone="teal",
            title="Watch the detection stack close in",
            lede="Scrub a day at a time through a <strong>real injected scheme</strong>. An "
                 "account outlines in red only when a real detector has actually fired on "
                 "it by that day &mdash; never because it is in the answer key. It is in "
                 "the answer key the entire time; that is exactly the point.",
            meta=[(f"{len(everything)}", "schemes replayed"),
                  (f"{caught}/{len(everything)}", "ever caught"),
                  ("nightly", "re-detection cadence")])
        + web.section(
            sid="replay", eyebrow="Investigation replay",
            title="Pick a scheme. Drag the day. Watch what an analyst would have seen.",
            lede="Every frame re-runs the <em>unmodified</em> rules engine and graph "
                 "detector against a view of the ledger truncated to that day. There is no "
                 "second, day-aware copy of a rule that could disagree with the one being "
                 "graded.",
            tone="teal",
            body='<div class="picker" role="group" aria-label="Choose a scheme to replay">'
                 f'{buttons}</div>' + _stage())
        + web.section(
            sid="latency", eyebrow="The measurement",
            title="How long a scheme runs before anything fires",
            lede="Every detection figure this project had published was scored against the "
                 "<em>finished</em> world &mdash; which quietly assumes a bank may wait "
                 "until the crime is over before deciding it happened. Real monitoring runs "
                 "nightly against the ledger so far. Nothing here had ever answered how "
                 "long that takes.",
            body=web.kpis([
                (f"{medians.get(slowest, 0):.0f}d", "Slowest to detect",
                 f"<code>{web.esc(slowest or '—')}</code> needs the longest to accumulate "
                 "enough evidence to fire at all", "amber"),
                (f"{moved.get(worst, 0):.0%}", "Worst exposure at first alert",
                 f"<code>{web.esc(worst or '—')}</code> is caught with this share of its "
                 "value already moved", "rose"),
                (f"{caught}/{len(everything)}", "Schemes ever caught",
                 "The rest ran to completion with no detector firing at any point",
                 "violet"),
            ], "g3")
            + '<div style="height:18px"></div>'
            + web.chart_card(svg, caption=web.esc(note))
            + '<div style="height:16px"></div>'
            + web.chart_card(exposure_svg, caption=web.esc(exposure_note))
            + web.box("finding", "Latency and usefulness are nearly inverted",
                      "<p><code>round_tripping</code> is caught in a median of four days "
                      "&mdash; fast &mdash; with <strong>100% of the money already "
                      "moved</strong>, every time. That is not a tuning problem. The rule "
                      "fires on money leaving and coming back, so it needs the return leg "
                      "to exist before it has anything to see, and the return leg is the "
                      "last act of the scheme. It is structurally incapable of alerting "
                      "while a rupee is still stoppable. Meanwhile <code>structuring</code> "
                      "&mdash; the slowest, the worst bar on the latency chart &mdash; is "
                      "caught with roughly half the scheme still to come.</p>")
            + web.box("why", "Why this is a different axis, not a better number",
                      "<p>Detection rate asks <em>whether</em> a control fires. This asks "
                      "<em>when</em> &mdash; and then whether that was soon enough to "
                      "matter. A control can score perfectly on the first and be worthless "
                      "on the second, and no amount of threshold tuning moves it: the shape "
                      "of the evidence the rule requires is what decides it.</p>")
            + web.expandable(
                "Engineering note: how the day-by-day re-detection works",
                "<p>A DuckDB view named <code>transactions</code> shadows the real table "
                "through <code>search_path</code>, so the SQL every rule already contains "
                "does the filtering for free. The detectors are the real ones, called "
                "exactly as they are everywhere else. A test asserts the truncation really "
                "truncates by counting rows through the view &mdash; because if the "
                "shadowing ever silently stopped working, every scheme would report as "
                "detected on day one, which is a flattering number with nothing failing.</p>")
            + web.expandable(
                "Why screening and ML are excluded from this measurement",
                "<p>Screening asks an identity question: a customer is on a watchlist on "
                "day 0 and on day 39, so &ldquo;when did it fire&rdquo; has no meaning for "
                "it. The ML layer emits a ranking rather than an event, and re-fitting an "
                "unsupervised model once per day would measure the model&rsquo;s day-to-day "
                "instability rather than the scheme&rsquo;s visibility. The red team "
                "benchmark drew the same boundary for the same reason.</p>"))
        + web.section(
            sid="limits", eyebrow="Limitations", title="What this replay does not show",
            tone="amber",
            body='<div class="grid g2" data-rv="0">'
                 + web.card("Latency can under-report, never over-report",
                            "A rule that never fires reports no latency at all rather than "
                            "a flattering one. A detection dated before the scheme's own "
                            "first transaction would mean the replay leaked future rows, "
                            "and a test asserts it never does.", hover=False)
                 + web.card("Exposure counts transaction value, not loss",
                            "A round trip's departure and return are both labelled, so the "
                            "same money is counted twice. It is a fair progress measure "
                            "through a scheme; the rupee figure underneath it is not a loss "
                            "number and is never presented as one.", hover=False)
                 + web.card("Alerts predating a scheme are excluded",
                            "A scheme is injected into an account that already has a life. "
                            "Crediting a pre-existing alert to the scheme would report a "
                            "detection the scheme did not cause, and could even produce a "
                            "negative latency.", hover=False)
                 + web.card("Nightly is an assumption about cadence",
                            "This models a stack re-run once a day. A bank running intraday "
                            "monitoring would see shorter latencies; one running weekly "
                            "batches would see longer ones.", hover=False)
                 + "</div>")
        + web.section(
            sid="next", eyebrow="Next", title="Continue",
            body=web.next_link("results.html", "Measured results",
                               "Every detector, graded against the answer key",
                               "Detection rate, precision, queue composition, and what the "
                               "stack costs to run."))
    )

    path.write_text(web.shell(
        title="LaunderLab — Story Mode",
        description="Replay a real money-laundering scheme day by day and watch a "
                    "four-layer AML detection stack close in on it. Detection latency "
                    "measured by re-running the real detectors against day-truncated "
                    "views of the same ledger.",
        active="story.html", body=body, extra_css=_STORY_CSS,
        extra_js=f"const STORIES = {payload};"
                 f"const OPEN_ON = {most_illustrative(stories)};{_STORY_JS}"),
        encoding="utf-8")
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
