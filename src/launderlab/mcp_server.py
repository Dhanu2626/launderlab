"""AML MCP server — exposes the ledger and detection stack to an AI agent.

Every tool here is read-only against the bank and lands a row in an append-only
audit trail. That is the whole point: an agent that can screen names and pull
transaction history is a compliance tool only if a reviewer can reconstruct,
afterwards, exactly what it looked at and what came back. Untraceable automation
is precisely what the FCA and FinCEN keep fining people for.

BOUNDARY: this is blue-team tooling, so no tool may read `scheme_labels`
(PROJECT.md's quality bar). There is deliberately no generic SQL tool — one would
hand any agent a route straight to the answer key and make every score
meaningless. Tools are parameterised and narrow for that reason, not for taste.

Run:  python -m launderlab.mcp_server
"""

from __future__ import annotations

import inspect
import json
import os
import threading
from datetime import datetime
from functools import wraps

from mcp.server.fastmcp import FastMCP

from launderlab.db.ledger import DEFAULT_DB_PATH, connect
from launderlab.detect import rules
from launderlab.screening import engine as screening_engine
from launderlab.screening import matcher

mcp = FastMCP("launderlab-aml")

# ponytail: one connection + one lock. DuckDB is fine with this at a single
# analyst's query rate; if this ever serves concurrent reviewers, give each
# request its own conn.cursor() instead.
_lock = threading.Lock()
_conn = None


def _db():
    global _conn
    if _conn is None:
        _conn = connect(os.environ.get("LAUNDERLAB_DB") or DEFAULT_DB_PATH.resolve())
        _conn.execute("CREATE SEQUENCE IF NOT EXISTS audit_seq")
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS audit_log ("
            " audit_id BIGINT PRIMARY KEY DEFAULT nextval('audit_seq'),"
            " ts TIMESTAMP NOT NULL, tool VARCHAR NOT NULL,"
            " params VARCHAR NOT NULL, outcome VARCHAR NOT NULL, hits INTEGER)"
        )
    return _conn


def audited(fn):
    """Log every call to the audit trail, including the ones that raise.

    A decorator rather than a log line inside each tool: the guarantee we want is
    "no tool can run unlogged", and that only holds if it is impossible to forget.
    """
    signature = inspect.signature(fn)

    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Positional args are BOUND TO THEIR NAMES before logging, not appended as
        # an anonymous list. Two reasons. `@wraps` advertises the wrapped
        # function's real signature, so `screen_name("Asha Rao")` looks legal --
        # it used to raise "takes 0 positional arguments", which is a baffling
        # error for a call that matches the documented signature. And an audit
        # trail whose `params` column means something different depending on how
        # the caller happened to pass arguments is one a reviewer has to
        # interpret; every row now records the same shape.
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        params = dict(bound.arguments)

        conn = _db()
        try:
            result = fn(*args, **kwargs)
            outcome, hits = "ok", _count(result)
        except Exception as exc:
            outcome, hits = f"error: {type(exc).__name__}: {exc}", None
            raise
        finally:
            with _lock:
                conn.execute(
                    "INSERT INTO audit_log (ts, tool, params, outcome, hits) VALUES (?,?,?,?,?)",
                    [datetime.now(), fn.__name__, json.dumps(params, default=str),
                     outcome, hits],
                )
        return result
    return wrapper


def _count(result) -> int | None:
    """How many records a tool returned — the number a reviewer actually cares about."""
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        for key in ("matches", "alerts", "transactions", "entries"):
            if isinstance(result.get(key), list):
                return len(result[key])
    return None


# ---------------------------------------------------------------- name screening
# Thin front end over launderlab.screening — the matching logic lives there, is
# scored against ground truth, and is shared with the batch engine, so what this
# tool returns is exactly what the offline precision/recall numbers describe.


@mcp.tool()
@audited
def screen_name(name: str, threshold: float = matcher.DEFAULT_THRESHOLD) -> dict:
    """Screen a name against the sanctions/PEP watchlist and high-risk jurisdictions.

    Matching is Jaro-Winkler with Metaphone corroboration over aligned name tokens,
    so transliterations ('Farhan'/'Farhaan'), phonetic variants ('Mohammed'/
    'Muhammad'), initials ('S K Gupta') and reordered names all still hit. Returns
    every candidate at or above `threshold` with its score, so a human decides —
    the tool never auto-clears anyone.
    """
    matches = matcher.screen(name, screening_engine.load_watchlist(), threshold)

    upper = name.upper()
    geo = [c for c in rules.HIGH_RISK_WATCHLIST if c in upper]

    return {
        "query": name,
        "threshold": threshold,
        "matches": [
            {"name": m.name, "score": m.score, "type": m.list_type,
             "program": m.program, "country": m.country}
            for m in matches
        ],
        "high_risk_jurisdiction": geo,
        "decision": "REVIEW" if matches or geo else "NO_HIT",
        "note": "Fuzzy match — a hit is a lead for human review, not a confirmed identity. "
                "Name alone cannot separate two people who share a name; confirm with "
                "date of birth or nationality before acting.",
    }


@mcp.tool()
@audited
def adverse_media_check(name: str, threshold: float = matcher.DEFAULT_THRESHOLD) -> dict:
    """Search adverse media for a name, using the same fuzzy matching as screening.

    Benign business coverage is excluded — an article has to actually allege
    something before it counts as adverse. Precision here is genuinely low by
    nature (same name, different human is common), so every hit is a lead.
    """
    # Shared with the entity-360 endpoint rather than matched again here: two
    # copies of a screening rule drift, and then what a user is shown stops being
    # what the scorer grades. Same reason `screen_name` was rewired in Phase 4.
    with _lock:
        conn = _db()
        found = screening_engine.media_for_name(conn, name, threshold=threshold)
        searched = len(screening_engine._adverse_articles(conn))

    hits = [{"article_id": hit.article_id, "headline": hit.headline,
             "category": hit.category, "score": hit.score} for hit in found]

    return {
        "query": name,
        "threshold": threshold,
        "articles_searched": searched,
        "matches": hits,
        "decision": "REVIEW" if hits else "NO_HIT",
        "note": "Name-matched against news text — a hit is a lead, not a confirmed "
                "identification of your customer.",
    }


# ------------------------------------------------------------------ customer view

@mcp.tool()
@audited
def customer_profile(customer_id: str) -> dict:
    """KYC profile for one customer: identity, segment, risk rating, KYC level, accounts."""
    with _lock:
        row = _db().execute(
            "SELECT customer_id, full_name, dob, segment, city, kyc_level, risk_rating,"
            " created_at FROM customers WHERE customer_id = ?", [customer_id]
        ).fetchone()
        if row is None:
            raise ValueError(f"No such customer: {customer_id}")
        accounts = _db().execute(
            "SELECT account_id, account_type, ifsc, status, opened_at FROM accounts"
            " WHERE customer_id = ?", [customer_id]
        ).fetchall()

    keys = ["customer_id", "full_name", "dob", "segment", "city", "kyc_level",
            "risk_rating", "created_at"]
    profile = {k: str(v) if v is not None else None for k, v in zip(keys, row)}
    profile["accounts"] = [
        dict(zip(["account_id", "account_type", "ifsc", "status", "opened_at"],
                 [str(v) for v in acct]))
        for acct in accounts
    ]
    return profile


@mcp.tool()
@audited
def transaction_history(account_id: str, limit: int = 50) -> dict:
    """Recent transactions for an account, newest first. `limit` is capped at 500."""
    limit = max(1, min(int(limit), 500))
    with _lock:
        rows = _db().execute(
            "SELECT txn_id, ts, direction, channel, amount::DOUBLE, counterparty_name,"
            " narration, balance_after::DOUBLE FROM transactions WHERE account_id = ?"
            " ORDER BY ts DESC, txn_id DESC LIMIT ?", [account_id, limit]
        ).fetchall()

    keys = ["txn_id", "ts", "direction", "channel", "amount", "counterparty_name",
            "narration", "balance_after"]
    return {
        "account_id": account_id,
        "returned": len(rows),
        "transactions": [
            {k: (str(v) if k == "ts" else v) for k, v in zip(keys, r)} for r in rows
        ],
    }


# --------------------------------------------------------------------- detection

@mcp.tool()
@audited
def run_detection() -> dict:
    """Run all six detection rules over the ledger and return the alerts they raise.

    Reuses the same rules engine the project scores offline, so an alert seen here is
    the alert the scorer grades — the agent gets no privileged view.
    """
    with _lock:
        alerts = rules.run_all(_db())
    return {
        "alert_count": len(alerts),
        "accounts_flagged": len({a.account_id for a in alerts}),
        "alerts": [
            {"account_id": a.account_id, "rule": a.rule, "reason": a.reason,
             "ts": str(a.ts), "amount": a.amount}
            for a in sorted(alerts, key=lambda a: a.amount, reverse=True)
        ],
    }


@mcp.tool()
@audited
def audit_trail(limit: int = 50) -> dict:
    """Read back the audit trail — every tool call made against this server."""
    limit = max(1, min(int(limit), 500))
    with _lock:
        rows = _db().execute(
            "SELECT audit_id, ts, tool, params, outcome, hits FROM audit_log"
            " ORDER BY audit_id DESC LIMIT ?", [limit]
        ).fetchall()
    keys = ["audit_id", "ts", "tool", "params", "outcome", "hits"]
    return {"entries": [{k: (str(v) if k == "ts" else v) for k, v in zip(keys, r)}
                        for r in rows]}


if __name__ == "__main__":
    mcp.run()
