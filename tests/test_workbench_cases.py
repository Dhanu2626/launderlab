from datetime import datetime

import pytest

from launderlab.db.ledger import connect
from launderlab.workbench import cases
from launderlab.workbench.cases import CaseError
from launderlab.workbench.risk import RiskScore, RiskSignal


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "cases.duckdb")
    c.execute("INSERT INTO customers VALUES ('C1','Asha Rao','1994-03-12','salaried',"
              "'Hyderabad','full','low',?)", [datetime(2020, 1, 1)])
    c.execute("INSERT INTO accounts VALUES ('A1','C1','savings','LLAB0000001','active',?)",
              [datetime(2020, 1, 1)])
    c.execute("INSERT INTO customers VALUES ('C2','Vikram Iyer','1991-08-04','business',"
              "'Mumbai','full','medium',?)", [datetime(2020, 1, 1)])
    c.execute("INSERT INTO accounts VALUES ('A2','C2','current','LLAB0000001','active',?)",
              [datetime(2020, 1, 1)])
    return c


def _risk(account_id="A1", score=72.5, band="high") -> RiskScore:
    return RiskScore(account_id=account_id, score=score, band=band, signals=[
        RiskSignal("rules", "structuring_burst: 27 cash deposits", 1.0),
        RiskSignal("graph", "in a 3-hop pass-through chain", 0.75),
    ])


def test_opening_a_case_snapshots_its_evidence(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    case = cases.get(conn, case_id)
    assert case.account_id == "A1"
    assert case.status == "open"
    assert case.disposition is None
    assert {s.source for s in case.signals} == {"rules", "graph"}
    assert case.signals[0].contribution >= case.signals[-1].contribution


def test_a_case_cannot_be_opened_without_evidence(conn):
    bare = RiskScore(account_id="A1", score=10.0, band="low", signals=[])
    with pytest.raises(CaseError, match="no evidence"):
        cases.open_case(conn, bare, actor="system")


def test_every_mutation_leaves_an_event(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    cases.assign(conn, case_id, "dhanush", actor="supervisor")
    cases.add_note(conn, case_id, "Called the RM; customer claims scrap sales.", actor="dhanush")
    cases.close(conn, case_id, "true_positive_sar", actor="dhanush",
                rationale="Cash pattern inconsistent with declared business.")

    kinds = [e.event_type for e in cases.timeline(conn, case_id)]
    assert kinds == ["opened", "assigned", "note", "disposition"]


def test_timeline_is_ordered_and_attributed(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    cases.add_note(conn, case_id, "first", actor="dhanush")
    cases.add_note(conn, case_id, "second", actor="reviewer")
    events = cases.timeline(conn, case_id)
    assert [e.event_id for e in events] == sorted(e.event_id for e in events)
    assert events[-1].actor == "reviewer"
    assert events[-1].detail == "second"


def test_case_events_are_never_updated_or_deleted():
    """Append-only is the property the audit trail rests on, so assert it in source."""
    import inspect
    import re

    from launderlab.workbench import cases as module
    source = inspect.getsource(module)
    assert not re.search(r"UPDATE\s+case_events", source, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+case_events", source, re.IGNORECASE)


def test_closing_requires_a_known_disposition_and_a_rationale(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    with pytest.raises(CaseError, match="unknown disposition"):
        cases.close(conn, case_id, "probably_fine", actor="d", rationale="looks ok")
    with pytest.raises(CaseError, match="not defensible"):
        cases.close(conn, case_id, "false_positive", actor="d", rationale="   ")
    assert cases.get(conn, case_id).status == "open"


def test_a_closed_case_carries_its_disposition(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    cases.close(conn, case_id, "false_positive", actor="dhanush",
                rationale="Deposits match declared retail takings.")
    case = cases.get(conn, case_id)
    assert case.status == "closed"
    assert case.disposition == "false_positive"
    assert case.closed_at is not None
    assert not case.is_open


def test_a_case_cannot_be_closed_twice(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    cases.close(conn, case_id, "false_positive", actor="d", rationale="explained")
    with pytest.raises(CaseError, match="already closed"):
        cases.close(conn, case_id, "escalated", actor="d", rationale="changed my mind")


def test_reopening_clears_disposition_but_keeps_the_history(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    cases.close(conn, case_id, "false_positive", actor="d", rationale="explained")
    cases.reopen(conn, case_id, actor="mlro", reason="New adverse media surfaced.")

    case = cases.get(conn, case_id)
    assert case.status == "in_review"
    assert case.disposition is None
    # the earlier decision must still be readable -- changing your mind is a fact
    kinds = [e.event_type for e in cases.timeline(conn, case_id)]
    assert "disposition" in kinds and kinds[-1] == "reopened"
    assert any("false_positive" in e.detail for e in cases.timeline(conn, case_id))


def test_closed_cases_cannot_be_reassigned(conn):
    case_id = cases.open_case(conn, _risk(), actor="system")
    cases.close(conn, case_id, "escalated", actor="d", rationale="referred to MLRO")
    with pytest.raises(CaseError, match="closed"):
        cases.assign(conn, case_id, "someone", actor="supervisor")


def test_queue_is_ranked_by_risk_and_filters_by_status(conn):
    low = cases.open_case(conn, _risk("A1", 35.0, "medium"), actor="system")
    high = cases.open_case(conn, _risk("A2", 91.0, "critical"), actor="system")

    ranked = [c.case_id for c in cases.queue(conn)]
    assert ranked == [high, low]

    cases.close(conn, high, "false_positive", actor="d", rationale="explained")
    assert [c.case_id for c in cases.queue(conn, status="open")] == [low]
    assert [c.case_id for c in cases.queue(conn, status="closed")] == [high]


def test_queue_filters_by_assignee(conn):
    mine = cases.open_case(conn, _risk("A1"), actor="system")
    cases.open_case(conn, _risk("A2"), actor="system")
    cases.assign(conn, mine, "dhanush", actor="supervisor")
    assert [c.case_id for c in cases.queue(conn, assigned_to="dhanush")] == [mine]


def test_open_from_queue_skips_low_risk_and_never_duplicates(conn):
    scores = [_risk("A1", 80.0, "high"), _risk("A2", 12.0, "low")]
    first = cases.open_from_queue(conn, scores, actor="system", min_score=30.0)
    assert len(first) == 1, "only the account above the threshold should open"

    # re-running detection must not bury analysts in duplicates
    second = cases.open_from_queue(conn, scores, actor="system", min_score=30.0)
    assert second == []

    # but once the case is closed, a fresh signal may legitimately open a new one
    cases.close(conn, first[0], "false_positive", actor="d", rationale="explained")
    third = cases.open_from_queue(conn, scores, actor="system", min_score=30.0)
    assert len(third) == 1


def test_unknown_case_raises_everywhere(conn):
    for call in (lambda: cases.get(conn, 999),
                 lambda: cases.timeline(conn, 999),
                 lambda: cases.add_note(conn, 999, "x", actor="d"),
                 lambda: cases.assign(conn, 999, "d", actor="s")):
        with pytest.raises(CaseError, match="no such case"):
            call()
