from datetime import datetime

import pytest

from launderlab.db.ledger import connect
from launderlab.workbench import cases, narrative
from launderlab.workbench.cases import CaseError
from launderlab.workbench.risk import RiskScore, RiskSignal


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "narrative.duckdb")
    c.execute("INSERT INTO customers VALUES ('C1','Asha Rao','1994-03-12','business',"
              "'Hyderabad','full','medium',?)", [datetime(2024, 1, 1)])
    c.execute("INSERT INTO accounts VALUES ('A1','C1','current','LLAB0000001','active',?)",
              [datetime(2024, 1, 1)])
    rows = [
        (datetime(2026, 7, 2, 10, 0), "CR", "CASH", 95_000, "-", "CASH-DEP/CR/BR-01", 95_000),
        (datetime(2026, 7, 3, 11, 0), "CR", "CASH", 98_000, "-", "CASH-DEP/CR/BR-01", 193_000),
        (datetime(2026, 7, 4, 12, 0), "CR", "CASH", 91_000, "-", "CASH-DEP/CR/BR-02", 284_000),
        (datetime(2026, 7, 5, 13, 0), "DR", "RTGS", 250_000, "ORBIT EXPORTS",
         "RTGS/DR/774321/INV-9910", 34_000),
    ]
    for ts, direction, channel, amount, party, narration, balance in rows:
        c.execute("INSERT INTO transactions (ts, account_id, direction, channel, amount,"
                  " counterparty_name, narration, balance_after) VALUES (?,'A1',?,?,?,?,?,?)",
                  [ts, direction, channel, amount, party, narration, balance])
    return c


def _risk() -> RiskScore:
    return RiskScore(account_id="A1", score=61.4, band="high", signals=[
        RiskSignal("rules", "structuring_burst: 3 cash deposits under Rs 100,000 "
                            "totaling Rs 284,000", 0.60),
        RiskSignal("graph", "in a 3-hop pass-through chain (Rs 284,000 entering, "
                            "88% retained)", 0.75),
    ])


@pytest.fixture()
def case_id(conn):
    return cases.open_case(conn, _risk(), actor="system")


def test_narrative_answers_who_what_when_and_why(conn, case_id):
    text = narrative.draft(conn, case_id)
    # who
    assert "Asha Rao" in text and "C1" in text
    assert "business" in text and "Hyderabad" in text
    # what account
    assert "A1" in text and "current" in text and "LLAB0000001" in text
    # what activity, with figures taken from the ledger rather than invented
    assert "Rs 284,000.00" in text          # total credits
    assert "Rs 250,000.00" in text          # total debits
    assert "CASH" in text and "RTGS" in text
    # why
    assert "structuring_burst" in text and "pass-through chain" in text
    assert "61.4" in text and "high" in text


def test_reason_for_suspicion_is_the_snapshot_verbatim(conn, case_id):
    """The narrative must describe the suspicion the analyst acted on, not a
    re-run of today's detectors. Same rule as the case store: detectors get
    retuned, and a filing that silently acquires reasoning nobody saw is worse
    than no filing."""
    text = narrative.draft(conn, case_id)
    for signal in cases.get(conn, case_id).signals:
        assert signal.detail in text


def test_narrative_reports_suspicion_and_never_asserts_guilt(conn, case_id):
    """A SAR reports suspicion; the bank is not the finder of fact. Language that
    concludes an offence occurred is a real compliance problem, not a style one."""
    text = narrative.draft(conn, case_id).lower()
    assert "consistent with" in text
    assert "no conclusion is drawn" in text
    for forbidden in ("laundered", "is guilty", "committed money laundering",
                      "the customer is a criminal", "proves"):
        assert forbidden not in text


def test_every_draft_is_stamped_as_a_draft(conn, case_id):
    text = narrative.draft(conn, case_id)
    assert "DRAFT" in text
    assert "not a filing" in text
    assert "verified" in text and "before submission" in text


def test_an_open_case_is_marked_provisional_and_a_closed_one_carries_its_disposition(
        conn, case_id):
    assert "must not be filed as it stands" in narrative.draft(conn, case_id)

    cases.assign(conn, case_id, "dhanush", actor="supervisor")
    cases.close(conn, case_id, "true_positive_sar", actor="dhanush",
                rationale="Cash pattern inconsistent with declared business.")
    closed = narrative.draft(conn, case_id)
    assert "true_positive_sar" in closed
    assert "must not be filed as it stands" not in closed
    assert "dhanush" in closed


def test_the_investigation_record_reproduces_the_audit_trail(conn, case_id):
    cases.add_note(conn, case_id, "Called the relationship manager.", actor="dhanush")
    text = narrative.draft(conn, case_id)
    for event in cases.timeline(conn, case_id):
        assert event.detail in text
        assert event.actor in text


def test_the_annex_does_not_claim_to_rank_by_suspicion(conn, case_id):
    """Only the graph layer can name the rows behind its own alert. Ranking the
    annex by value and calling it evidence would be inventing a link the
    detectors never produced."""
    text = narrative.draft(conn, case_id)
    assert "by amount" in text
    assert "not" in text and "assertion that these particular entries" in text


def test_the_same_case_always_drafts_the_same_narrative(conn, case_id):
    """Determinism is the argument for a template over a language model: a filing
    that changes wording between reads cannot be reviewed or diffed."""
    assert narrative.draft(conn, case_id) == narrative.draft(conn, case_id)


def test_unknown_case_raises_rather_than_drafting_an_empty_report(conn):
    with pytest.raises(CaseError, match="no such case"):
        narrative.draft(conn, 4242)


def test_narrative_never_reads_ground_truth():
    """Same boundary as every other layer. A narrative built from the answer key
    would be a filing the bank could not have produced from its own data."""
    import inspect
    import re

    source = inspect.getsource(narrative)
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert not re.search(rf"\b(FROM|JOIN)\s+{table}\b", source, re.IGNORECASE)
