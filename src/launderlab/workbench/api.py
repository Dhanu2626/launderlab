"""FastAPI backend for the investigator workbench.

Serves three things the UI needs: the case queue, one entity's full picture, and
the actions that move a case through its lifecycle. Everything it exposes already
exists in `workbench.cases`, `workbench.risk` and the detection layers — this is
a transport, not a second implementation, so what an analyst sees in the browser
is exactly what the offline scorers grade.

TWO BOUNDARIES, both inherited and both load-bearing:

* **No endpoint exposes `scheme_labels`, `entity_labels` or `media_labels`.** The
  same rule the rules engine, screening engine, graph layer and MCP server all
  follow. An API that leaked ground truth would invalidate every precision and
  recall number the project has produced, and it would do so silently.
* **Every case mutation names its actor.** The case store refuses to change
  anything without one, so the API requires it too rather than inventing a
  default — "the system did it" is not an audit trail.

Run:  python -m launderlab.workbench.api      (or uvicorn on the app object)
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from importlib import resources
from typing import Annotated

import duckdb
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from launderlab.db.ledger import DEFAULT_DB_PATH, connect
from launderlab.graph import build as graph_build
from launderlab.graph import motifs
from launderlab.workbench import cases, narrative
from launderlab.workbench.cases import CaseError

app = FastAPI(title="LaunderLab investigator workbench",
              summary="Alert queue, entity 360 and case lifecycle over the synthetic bank.")

# ponytail: one connection behind a lock, same as mcp_server. DuckDB copes fine at
# a single analyst's query rate; give each request its own cursor if this ever
# serves a real team.
_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None


def db() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = connect(os.environ.get("LAUNDERLAB_DB") or DEFAULT_DB_PATH.resolve())
    return _conn


def reset_connection() -> None:
    """Drop the cached handle — used by tests pointing at a throwaway world."""
    global _conn
    _conn = None


# --------------------------------------------------------------------- schemas

class SignalOut(BaseModel):
    source: str
    detail: str
    contribution: float


class CaseOut(BaseModel):
    case_id: int
    account_id: str
    customer_name: str | None = None
    opened_at: datetime
    risk_score: float
    risk_band: str
    status: str
    disposition: str | None
    assigned_to: str | None
    closed_at: datetime | None
    signals: list[SignalOut] = Field(default_factory=list)


class EventOut(BaseModel):
    event_id: int
    ts: datetime
    actor: str
    event_type: str
    detail: str


class TransactionOut(BaseModel):
    txn_id: int
    ts: datetime
    direction: str
    channel: str
    amount: float
    counterparty_name: str | None
    narration: str
    balance_after: float


class ChainOut(BaseModel):
    accounts: list[str]
    names: list[str | None]      # the humans behind the account ids
    amounts: list[float]
    hop_txns: list[list[int]]    # (DR row, CR row) per hop, in order
    hops: int
    retained: float
    started: datetime
    ended: datetime


class AccountSummary(BaseModel):
    """Totals over the account's WHOLE history, not the window returned below.

    Deriving these in the browser from `transactions` would understate every one
    of them the moment an account has more rows than `transaction_limit` — and it
    would do so silently, which is exactly the class of quietly-wrong number this
    project keeps finding. So they are computed in SQL over the full history.
    """
    transaction_count: int
    total_credit: float
    total_debit: float
    first_activity: datetime | None
    last_activity: datetime | None


class Entity360(BaseModel):
    account_id: str
    customer_id: str
    full_name: str
    segment: str
    city: str | None
    kyc_level: str
    risk_rating: str
    account_type: str
    status: str
    opened_at: datetime
    summary: AccountSummary
    transactions: list[TransactionOut]
    chains: list[ChainOut]
    open_cases: list[int]


class ActorAction(BaseModel):
    actor: str = Field(min_length=1, description="Who is performing this action")


class AssignIn(ActorAction):
    analyst: str = Field(min_length=1)


class NoteIn(ActorAction):
    note: str = Field(min_length=1)


class CloseIn(ActorAction):
    disposition: str
    rationale: str = Field(min_length=1)


class ReopenIn(ActorAction):
    reason: str = Field(min_length=1)


# --------------------------------------------------------------------- helpers

def _customer_name(conn: duckdb.DuckDBPyConnection, account_id: str) -> str | None:
    row = conn.execute(
        "SELECT c.full_name FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE a.account_id = ?", [account_id]).fetchone()
    return row[0] if row else None


def _names_for(conn: duckdb.DuckDBPyConnection, account_ids: list[str]) -> dict[str, str]:
    """Account id -> customer name, in one query rather than one per hop."""
    if not account_ids:
        return {}
    placeholders = ",".join("?" * len(account_ids))
    return dict(conn.execute(
        "SELECT a.account_id, c.full_name FROM accounts a JOIN customers c USING (customer_id)"
        f" WHERE a.account_id IN ({placeholders})", account_ids).fetchall())


def _to_case_out(conn: duckdb.DuckDBPyConnection, case: cases.Case) -> CaseOut:
    return CaseOut(
        case_id=case.case_id, account_id=case.account_id,
        customer_name=_customer_name(conn, case.account_id),
        opened_at=case.opened_at, risk_score=case.risk_score, risk_band=case.risk_band,
        status=case.status, disposition=case.disposition, assigned_to=case.assigned_to,
        closed_at=case.closed_at,
        signals=[SignalOut(source=s.source, detail=s.detail, contribution=s.contribution)
                 for s in case.signals],
    )


def _guard(fn):
    """Turn a lifecycle violation into a 409, not a 500.

    Closing an already-closed case is a *conflict* with the record's state, not a
    server fault, and the UI needs to tell the analyst which one it was.
    """
    try:
        return fn()
    except CaseError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if "no such case" in message else 409,
                            detail=message) from exc


# ---------------------------------------------------------------------- routes

@app.get("/", response_class=HTMLResponse)
def workbench_ui() -> str:
    """The investigator queue itself.

    Served as one self-contained page rather than a built frontend: no bundler,
    no node_modules, no extra CI stage, and it works the moment the API is up.
    The API is the contract, so a React build can replace this later without a
    single endpoint changing.
    """
    return resources.files("launderlab.workbench.static").joinpath(
        "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    with _lock:
        counts = {
            table: db().execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("customers", "accounts", "transactions", "cases")
        }
    return {"status": "ok", **counts}


@app.get("/queue", response_model=list[CaseOut])
def queue(status: Annotated[str | None, Query()] = "open",
          assigned_to: Annotated[str | None, Query()] = None,
          limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[CaseOut]:
    """The work list, highest risk first — analyst hours are the scarce resource."""
    with _lock:
        conn = db()
        return [_to_case_out(conn, c)
                for c in cases.queue(conn, status=status, assigned_to=assigned_to, limit=limit)]


@app.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: int) -> CaseOut:
    with _lock:
        conn = db()
        return _to_case_out(conn, _guard(lambda: cases.get(conn, case_id)))


@app.get("/cases/{case_id}/timeline", response_model=list[EventOut])
def get_timeline(case_id: int) -> list[EventOut]:
    """The audit trail — the part an examiner actually reads."""
    with _lock:
        conn = db()
        events = _guard(lambda: cases.timeline(conn, case_id))
    return [EventOut(event_id=e.event_id, ts=e.ts, actor=e.actor,
                     event_type=e.event_type, detail=e.detail) for e in events]


@app.post("/cases/{case_id}/assign", response_model=CaseOut)
def assign_case(case_id: int, payload: Annotated[AssignIn, Body()]) -> CaseOut:
    with _lock:
        conn = db()
        _guard(lambda: cases.assign(conn, case_id, payload.analyst, actor=payload.actor))
        return _to_case_out(conn, cases.get(conn, case_id))


@app.post("/cases/{case_id}/notes", response_model=list[EventOut])
def add_note(case_id: int, payload: Annotated[NoteIn, Body()]) -> list[EventOut]:
    with _lock:
        conn = db()
        _guard(lambda: cases.add_note(conn, case_id, payload.note, actor=payload.actor))
        events = cases.timeline(conn, case_id)
    return [EventOut(event_id=e.event_id, ts=e.ts, actor=e.actor,
                     event_type=e.event_type, detail=e.detail) for e in events]


@app.post("/cases/{case_id}/close", response_model=CaseOut)
def close_case(case_id: int, payload: Annotated[CloseIn, Body()]) -> CaseOut:
    with _lock:
        conn = db()
        _guard(lambda: cases.close(conn, case_id, payload.disposition,
                                    actor=payload.actor, rationale=payload.rationale))
        return _to_case_out(conn, cases.get(conn, case_id))


@app.post("/cases/{case_id}/reopen", response_model=CaseOut)
def reopen_case(case_id: int, payload: Annotated[ReopenIn, Body()]) -> CaseOut:
    with _lock:
        conn = db()
        _guard(lambda: cases.reopen(conn, case_id, actor=payload.actor, reason=payload.reason))
        return _to_case_out(conn, cases.get(conn, case_id))


@app.get("/cases/{case_id}/narrative", response_class=PlainTextResponse)
def case_narrative(case_id: int) -> str:
    """The SAR narrative draft — the only artefact anyone outside the bank reads.

    Plain text on purpose: a narrative is pasted into a filing system or an
    email, and JSON-escaping a document an analyst has to read is friction for
    nothing. It is a *draft* and says so in its own footer.
    """
    with _lock:
        conn = db()
        return _guard(lambda: narrative.draft(conn, case_id))


@app.get("/dispositions")
def dispositions() -> dict:
    """The closing options and what each one means, so the UI never invents its own."""
    return cases.DISPOSITIONS


@app.get("/accounts/{account_id}", response_model=Entity360)
def entity_360(account_id: str,
               transaction_limit: Annotated[int, Query(ge=1, le=500)] = 100) -> Entity360:
    """Everything about one account: who they are, what they did, who they moved money with."""
    with _lock:
        conn = db()
        row = conn.execute(
            "SELECT a.account_id, c.customer_id, c.full_name, c.segment, c.city,"
            " c.kyc_level, c.risk_rating, a.account_type, a.status, a.opened_at"
            " FROM accounts a JOIN customers c USING (customer_id) WHERE a.account_id = ?",
            [account_id]).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no such account: {account_id}")

        totals = conn.execute(
            "SELECT count(*),"
            " coalesce(sum(CASE WHEN direction = 'CR' THEN amount END), 0)::DOUBLE,"
            " coalesce(sum(CASE WHEN direction = 'DR' THEN amount END), 0)::DOUBLE,"
            " min(ts), max(ts) FROM transactions WHERE account_id = ?", [account_id]).fetchone()

        txns = conn.execute(
            "SELECT txn_id, ts, direction, channel, amount::DOUBLE, counterparty_name,"
            " narration, balance_after::DOUBLE FROM transactions WHERE account_id = ?"
            " ORDER BY ts DESC, txn_id DESC LIMIT ?", [account_id, transaction_limit]
        ).fetchall()

        chains = [c for c in motifs.find_chains(graph_build.build_graph(conn))
                  if account_id in c.accounts]
        chain_names = _names_for(conn, sorted({a for c in chains for a in c.accounts}))
        open_case_ids = [r[0] for r in conn.execute(
            "SELECT case_id FROM cases WHERE account_id = ? AND status IN ('open','in_review')"
            " ORDER BY case_id", [account_id]).fetchall()]

    return Entity360(
        account_id=row[0], customer_id=row[1], full_name=row[2], segment=row[3],
        city=row[4], kyc_level=row[5], risk_rating=row[6], account_type=row[7],
        status=row[8], opened_at=row[9],
        summary=AccountSummary(transaction_count=totals[0], total_credit=totals[1],
                               total_debit=totals[2], first_activity=totals[3],
                               last_activity=totals[4]),
        transactions=[TransactionOut(
            txn_id=t[0], ts=t[1], direction=t[2], channel=t[3], amount=t[4],
            counterparty_name=t[5], narration=t[6], balance_after=t[7]) for t in txns],
        chains=[ChainOut(accounts=list(c.accounts),
                         names=[chain_names.get(a) for a in c.accounts],
                         amounts=list(c.amounts),
                         hop_txns=[list(pair) for pair in c.hop_txns],
                         hops=c.hops, retained=c.retained,
                         started=c.started, ended=c.ended)
                for c in chains],
        open_cases=open_case_ids,
    )


def main() -> None:  # pragma: no cover - entry point
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)


if __name__ == "__main__":  # pragma: no cover
    main()
