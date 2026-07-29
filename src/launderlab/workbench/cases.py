"""Case management — where a detection becomes a decision.

Everything before this module finds things. This is the only part of LaunderLab
that records a human having looked, and it is what an examiner would actually ask
to see.

THREE RULES ENFORCED HERE, all for the same reason — an investigation is only
worth as much as its auditability:

1. **Every mutation writes an event.** Assigning, noting, closing, reopening: all
   of it lands in `case_events`. There is no code path that changes a case without
   leaving a trace, because "who cleared this account, and when" is the first
   question anyone asks after something goes wrong.

2. **Events are append-only.** Nothing here updates or deletes them. A
   disposition that can be quietly rewritten is worthless as evidence, and a
   changed decision is itself a fact worth keeping.

3. **Evidence is snapshotted at open time.** Detectors get retuned — Phase 6
   re-tuned two rules and made a third produce known false positives — so
   re-deriving why a case was opened from today's code would rewrite history. The
   case records what the analyst was actually shown.

A closed case must carry a disposition, and a disposition only exists on a closed
case; `close()` is the single door between those states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import duckdb

from launderlab.workbench.risk import RiskScore, RiskSignal

DISPOSITIONS = {
    "false_positive": "Reviewed and cleared — activity explained.",
    "true_positive_sar": "Suspicious. SAR filed.",
    "true_positive_no_sar": "Suspicious but below the reporting threshold; documented.",
    "escalated": "Referred onward for senior review.",
}
OPEN_STATUSES = ("open", "in_review")


class CaseError(RuntimeError):
    """Raised when a transition would break the case lifecycle."""


@dataclass(frozen=True)
class CaseEvent:
    event_id: int
    ts: datetime
    actor: str
    event_type: str
    detail: str


@dataclass(frozen=True)
class Case:
    case_id: int
    account_id: str
    opened_at: datetime
    risk_score: float
    risk_band: str
    status: str
    disposition: str | None
    assigned_to: str | None
    closed_at: datetime | None
    signals: list[RiskSignal] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


def _record(conn: duckdb.DuckDBPyConnection, case_id: int, actor: str,
            event_type: str, detail: str, ts: datetime | None = None) -> None:
    conn.execute(
        "INSERT INTO case_events (case_id, ts, actor, event_type, detail) VALUES (?,?,?,?,?)",
        [case_id, ts or datetime.now(), actor, event_type, detail],
    )


def open_case(conn: duckdb.DuckDBPyConnection, risk: RiskScore, actor: str,
              opened_at: datetime | None = None) -> int:
    """Open a case from a risk score, snapshotting the evidence behind it."""
    if not risk.signals:
        raise CaseError(f"refusing to open a case for {risk.account_id} with no evidence")

    opened_at = opened_at or datetime.now()
    conn.execute(
        "INSERT INTO cases (account_id, opened_at, risk_score, risk_band, status)"
        " VALUES (?, ?, ?, ?, 'open')",
        [risk.account_id, opened_at, risk.score, risk.band],
    )
    case_id = conn.execute("SELECT max(case_id) FROM cases").fetchone()[0]

    conn.executemany(
        "INSERT INTO case_signals VALUES (?, ?, ?, ?)",
        [(case_id, s.source, s.detail, round(s.contribution, 3)) for s in risk.signals],
    )
    _record(conn, case_id, actor, "opened",
            f"opened on {risk.account_id} at risk {risk.score} ({risk.band}) "
            f"from {len(risk.signals)} signal(s)", opened_at)
    return case_id


def _require(conn: duckdb.DuckDBPyConnection, case_id: int) -> tuple[str, str | None]:
    row = conn.execute("SELECT status, disposition FROM cases WHERE case_id = ?",
                       [case_id]).fetchone()
    if row is None:
        raise CaseError(f"no such case: {case_id}")
    return row


def assign(conn: duckdb.DuckDBPyConnection, case_id: int, analyst: str, actor: str) -> None:
    status, _ = _require(conn, case_id)
    if status == "closed":
        raise CaseError(f"case {case_id} is closed; reopen it before reassigning")
    conn.execute("UPDATE cases SET assigned_to = ?, status = 'in_review' WHERE case_id = ?",
                 [analyst, case_id])
    _record(conn, case_id, actor, "assigned", f"assigned to {analyst}")


def add_note(conn: duckdb.DuckDBPyConnection, case_id: int, note: str, actor: str) -> None:
    """Notes are events, not a mutable field — an investigator's reasoning is the
    part a reviewer most needs, and it must not be editable after the fact."""
    _require(conn, case_id)
    if not note.strip():
        raise CaseError("refusing to record an empty note")
    _record(conn, case_id, actor, "note", note.strip())


def close(conn: duckdb.DuckDBPyConnection, case_id: int, disposition: str, actor: str,
          rationale: str, closed_at: datetime | None = None) -> None:
    """The only door from open to closed, and it demands a reason."""
    status, _ = _require(conn, case_id)
    if status == "closed":
        raise CaseError(f"case {case_id} is already closed")
    if disposition not in DISPOSITIONS:
        raise CaseError(f"unknown disposition {disposition!r}; "
                        f"expected one of {sorted(DISPOSITIONS)}")
    if not rationale.strip():
        raise CaseError("a disposition without a rationale is not defensible")

    closed_at = closed_at or datetime.now()
    conn.execute(
        "UPDATE cases SET status = 'closed', disposition = ?, closed_at = ? WHERE case_id = ?",
        [disposition, closed_at, case_id])
    _record(conn, case_id, actor, "disposition",
            f"{disposition}: {rationale.strip()}", closed_at)


def reopen(conn: duckdb.DuckDBPyConnection, case_id: int, actor: str, reason: str) -> None:
    """Reopening clears the disposition but never the history of having had one."""
    status, disposition = _require(conn, case_id)
    if status != "closed":
        raise CaseError(f"case {case_id} is not closed")
    conn.execute(
        "UPDATE cases SET status = 'in_review', disposition = NULL, closed_at = NULL"
        " WHERE case_id = ?", [case_id])
    _record(conn, case_id, actor, "reopened",
            f"reopened (was {disposition}): {reason.strip()}")


def get(conn: duckdb.DuckDBPyConnection, case_id: int) -> Case:
    row = conn.execute(
        "SELECT case_id, account_id, opened_at, risk_score::DOUBLE, risk_band, status,"
        " disposition, assigned_to, closed_at FROM cases WHERE case_id = ?", [case_id]
    ).fetchone()
    if row is None:
        raise CaseError(f"no such case: {case_id}")
    signals = [
        RiskSignal(source=source, detail=detail, contribution=float(contribution))
        for source, detail, contribution in conn.execute(
            "SELECT source, detail, contribution FROM case_signals WHERE case_id = ?"
            " ORDER BY contribution DESC", [case_id]).fetchall()
    ]
    return Case(*row, signals=signals)


def timeline(conn: duckdb.DuckDBPyConnection, case_id: int) -> list[CaseEvent]:
    """Full history, oldest first — the thing an examiner reads."""
    _require(conn, case_id)
    return [
        CaseEvent(*row) for row in conn.execute(
            "SELECT event_id, ts, actor, event_type, detail FROM case_events"
            " WHERE case_id = ? ORDER BY event_id", [case_id]).fetchall()
    ]


def queue(conn: duckdb.DuckDBPyConnection, status: str | None = "open",
          assigned_to: str | None = None, limit: int = 50) -> list[Case]:
    """The work list: highest risk first, because analyst hours are the scarce thing."""
    clauses, params = [], []
    if status == "open":
        clauses.append("status IN ('open','in_review')")
    elif status:
        clauses.append("status = ?")
        params.append(status)
    if assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    rows = conn.execute(
        "SELECT case_id FROM cases " + where + " ORDER BY risk_score DESC, case_id LIMIT ?",
        [*params, limit],
    ).fetchall()
    return [get(conn, case_id) for (case_id,) in rows]


def open_from_queue(conn: duckdb.DuckDBPyConnection, scores: list[RiskScore], actor: str,
                    min_score: float = 30.0, limit: int = 50) -> list[int]:
    """Open cases for the highest-risk accounts that do not already have one.

    Skipping accounts with a live case matters: re-running detection is routine,
    and a system that opens a duplicate case every run buries analysts in exactly
    the noise the alert budget is meant to control.
    """
    existing = {
        row[0] for row in conn.execute(
            "SELECT account_id FROM cases WHERE status IN ('open','in_review')").fetchall()
    }
    opened = []
    for risk in scores:
        if len(opened) >= limit:
            break
        if risk.score < min_score or risk.account_id in existing:
            continue
        opened.append(open_case(conn, risk, actor))
    return opened
