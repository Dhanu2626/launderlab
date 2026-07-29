import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import mule_network, structuring
from launderlab.workbench import cases, risk
from launderlab.world.generate import load

fastapi_testclient = pytest.importorskip(
    "fastapi.testclient", reason="FastAPI not installed (pip install -e .[api])")
api = pytest.importorskip("launderlab.workbench.api")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Point the API at a throwaway world with real cases already open."""
    path = tmp_path_factory.mktemp("api") / "w.duckdb"
    conn = connect(path)
    load(conn, n=400, days=30, seed=81)

    biz = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id").fetchall()]
    sal = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id").fetchall()]
    rng = random.Random(3)
    for i in range(3):
        structuring.inject(conn, f"S{i}", rng.choice(biz), date(2026, 7, 3), rng,
                            target_total=2_500_000)
        mule_network.inject(conn, f"M{i}", rng.sample(sal, 4), date(2026, 7, 3), rng)

    cases.open_from_queue(conn, risk.score_accounts(conn), actor="system", min_score=20.0)
    conn.close()

    import os
    os.environ["LAUNDERLAB_DB"] = str(path)
    api.reset_connection()
    with fastapi_testclient.TestClient(api.app) as c:
        yield c
    api.reset_connection()
    os.environ.pop("LAUNDERLAB_DB", None)


def test_health_reports_a_populated_world(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["transactions"] > 0
    assert body["cases"] > 0, "fixture should have opened real cases"


def test_api_never_exposes_ground_truth():
    """Same boundary as every detection layer — a leaking API would silently
    invalidate every precision and recall number the project has produced."""
    import inspect
    import re

    source = inspect.getsource(api)
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert not re.search(rf"\b(FROM|JOIN)\s+{table}\b", source, re.IGNORECASE)


def test_queue_is_ranked_by_risk_and_carries_evidence(client):
    body = client.get("/queue").json()
    assert body, "queue is empty"
    scores = [c["risk_score"] for c in body]
    assert scores == sorted(scores, reverse=True)
    for case in body:
        assert case["signals"], f"case {case['case_id']} has no evidence attached"
        assert case["status"] in ("open", "in_review")


def test_queue_respects_limit_and_status_filter(client):
    assert len(client.get("/queue", params={"limit": 2}).json()) <= 2
    for case in client.get("/queue", params={"status": "closed"}).json():
        assert case["status"] == "closed"


def test_case_detail_and_timeline(client):
    case_id = client.get("/queue").json()[0]["case_id"]
    detail = client.get(f"/cases/{case_id}").json()
    assert detail["case_id"] == case_id
    assert detail["customer_name"], "UI needs a human name, not just an account id"

    timeline = client.get(f"/cases/{case_id}/timeline").json()
    assert timeline[0]["event_type"] == "opened"
    assert all(e["actor"] for e in timeline), "every event must name its actor"


def test_unknown_case_is_404(client):
    assert client.get("/cases/999999").status_code == 404
    assert client.get("/cases/999999/timeline").status_code == 404


def test_full_case_lifecycle_through_the_api(client):
    case_id = client.get("/queue").json()[0]["case_id"]

    assigned = client.post(f"/cases/{case_id}/assign",
                            json={"actor": "supervisor", "analyst": "dhanush"}).json()
    assert assigned["assigned_to"] == "dhanush"
    assert assigned["status"] == "in_review"

    noted = client.post(f"/cases/{case_id}/notes",
                         json={"actor": "dhanush", "note": "Called the RM."}).json()
    assert any(e["event_type"] == "note" for e in noted)

    closed = client.post(f"/cases/{case_id}/close", json={
        "actor": "dhanush", "disposition": "true_positive_sar",
        "rationale": "Cash pattern inconsistent with declared business."}).json()
    assert closed["status"] == "closed"
    assert closed["disposition"] == "true_positive_sar"

    reopened = client.post(f"/cases/{case_id}/reopen", json={
        "actor": "mlro", "reason": "New adverse media."}).json()
    assert reopened["status"] == "in_review"
    assert reopened["disposition"] is None
    # the earlier decision must still be visible
    kinds = [e["event_type"] for e in client.get(f"/cases/{case_id}/timeline").json()]
    assert kinds == ["opened", "assigned", "note", "disposition", "reopened"]


def test_lifecycle_violations_are_409_not_500(client):
    """Closing a closed case is a conflict with the record's state, not a crash."""
    case_id = client.get("/queue").json()[-1]["case_id"]
    client.post(f"/cases/{case_id}/close", json={
        "actor": "d", "disposition": "false_positive", "rationale": "explained"})
    again = client.post(f"/cases/{case_id}/close", json={
        "actor": "d", "disposition": "escalated", "rationale": "changed my mind"})
    assert again.status_code == 409
    assert "already closed" in again.json()["detail"]


def test_closing_rejects_an_unknown_disposition(client):
    case_id = client.get("/queue").json()[0]["case_id"]
    response = client.post(f"/cases/{case_id}/close", json={
        "actor": "d", "disposition": "probably_fine", "rationale": "seems ok"})
    assert response.status_code == 409
    assert "unknown disposition" in response.json()["detail"]


def test_actions_require_an_actor(client):
    """The case store refuses anonymous changes, so the API must too."""
    case_id = client.get("/queue").json()[0]["case_id"]
    assert client.post(f"/cases/{case_id}/notes", json={"note": "no actor"}).status_code == 422
    assert client.post(f"/cases/{case_id}/notes",
                        json={"actor": "", "note": "blank actor"}).status_code == 422


def test_dispositions_endpoint_matches_the_case_store(client):
    assert client.get("/dispositions").json() == cases.DISPOSITIONS


def test_narrative_endpoint_serves_plain_text_a_human_can_paste(client):
    """Slice 7.8. A narrative is pasted into a filing system or an email;
    JSON-escaping a document an analyst has to read is friction for nothing."""
    case_id = client.get("/queue").json()[0]["case_id"]
    response = client.get(f"/cases/{case_id}/narrative")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert "SUSPICIOUS ACTIVITY REPORT - NARRATIVE DRAFT" in text
    assert "REASON FOR SUSPICION" in text and "DISPOSITION" in text
    # it must describe the case the API serves, not a generic form
    detail = client.get(f"/cases/{case_id}").json()
    assert detail["account_id"] in text
    for signal in detail["signals"]:
        assert signal["detail"] in text


def test_narrative_for_an_unknown_case_is_404(client):
    assert client.get("/cases/999999/narrative").status_code == 404


def test_entity_360_returns_profile_transactions_and_chains(client):
    account_id = client.get("/queue").json()[0]["account_id"]
    body = client.get(f"/accounts/{account_id}").json()

    assert body["account_id"] == account_id
    assert body["full_name"] and body["segment"]
    assert body["transactions"], "an entity view with no transactions is useless"
    # newest first, so an analyst sees recent behaviour immediately
    stamps = [t["ts"] for t in body["transactions"]]
    assert stamps == sorted(stamps, reverse=True)
    for chain in body["chains"]:
        assert account_id in chain["accounts"]


def test_entity_360_summary_covers_the_whole_history_not_the_window(client):
    """The totals must not describe only the transactions that were returned.

    An entity screen showing "total credits" computed from the latest 100 rows
    would under-report every busy account, and would do it silently — the exact
    failure mode slice 7.4 found in the risk score. So the summary is computed in
    SQL over the full account and this test proves the window cannot fake it.
    """
    account_id = client.get("/queue").json()[0]["account_id"]

    windowed = client.get(f"/accounts/{account_id}", params={"transaction_limit": 5}).json()
    summary = windowed["summary"]
    assert len(windowed["transactions"]) == 5
    assert summary["transaction_count"] > 5, "need an account with more history than the window"

    full = client.get(f"/accounts/{account_id}", params={"transaction_limit": 500}).json()
    assert len(full["transactions"]) == summary["transaction_count"] <= 500
    assert summary["total_credit"] == pytest.approx(
        sum(t["amount"] for t in full["transactions"] if t["direction"] == "CR"))
    assert summary["total_debit"] == pytest.approx(
        sum(t["amount"] for t in full["transactions"] if t["direction"] == "DR"))
    assert summary["first_activity"] <= summary["last_activity"]
    # identical totals from both windows — the summary ignores the limit entirely
    assert full["summary"] == summary


def test_chains_carry_the_rows_and_the_humans_behind_them(client):
    """Slice 7.6. A chain drawn as four account ids is a picture of nothing an
    investigator can act on: they need the names, and they need to get from the
    chain back to the statement lines it was reconstructed from."""
    body = next(b for b in (client.get(f"/accounts/{c['account_id']}").json()
                            for c in client.get("/queue").json()) if b["chains"])
    chain = body["chains"][0]

    assert len(chain["names"]) == len(chain["accounts"])
    assert any(chain["names"]), "no customer name resolved for any hop"
    assert len(chain["hop_txns"]) == chain["hops"] == len(chain["amounts"])

    # every cited row must be a real transaction on the account the hop claims
    for i, (dr, cr) in enumerate(chain["hop_txns"]):
        for txn_id, account_id, direction in ((dr, chain["accounts"][i], "DR"),
                                              (cr, chain["accounts"][i + 1], "CR")):
            leg = next(t for t in client.get(
                f"/accounts/{account_id}", params={"transaction_limit": 500}
            ).json()["transactions"] if t["txn_id"] == txn_id)
            assert leg["direction"] == direction
            assert leg["amount"] == chain["amounts"][i]


def test_a_chain_hop_can_be_opened_as_its_own_entity(client):
    """The point of drawing the graph is following it. Every account in a chain
    has to resolve on its own, including the hops with no case of their own."""
    body = next(b for b in (client.get(f"/accounts/{c['account_id']}").json()
                            for c in client.get("/queue").json()) if b["chains"])
    for account_id in body["chains"][0]["accounts"]:
        hop = client.get(f"/accounts/{account_id}")
        assert hop.status_code == 200
        assert hop.json()["full_name"]


def test_unknown_account_is_404(client):
    assert client.get("/accounts/NOPE").status_code == 404


def test_workbench_ui_is_served_and_self_contained(client):
    """The queue page must load with no build step and no external fetches.

    A portfolio demo that needs a bundler running, or a CDN reachable, is a demo
    that fails in the room. Everything it needs ships in the wheel.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    html = response.text
    assert "investigator workbench" in html.lower()
    # no external origins - no CDN scripts, stylesheets or fonts
    assert "http://" not in html and "https://" not in html
    # it must actually call the API it is paired with
    for endpoint in ("/queue", "/health", "/cases/", "/accounts/"):
        assert endpoint in html


def test_ui_case_view_carries_the_whole_entity_360(client):
    """Slice 7.5: an alert names an account, but adjudicating one needs the
    customer behind it — KYC, what the account did in total, who they moved money
    with, and the statement. All four render from `/accounts/{id}`."""
    html = client.get("/").text
    assert "renderProfile" in html and "renderStatement" in html
    for heading in ("Customer", "Activity (whole history)", "Money chains", "Statement"):
        assert heading in html
    # totals come from the server's whole-history summary, never re-derived from
    # the truncated transaction list the page happens to hold
    assert "summary.total_credit" in html or "s.total_credit" in html


def test_ui_asks_for_the_full_statement_not_the_default_window(client):
    """Looking at the screen caught this: an account flagged for *89 cash
    deposits* rendered a statement starting a week after the account itself did,
    because the endpoint defaults to the latest 100 rows. The evidence screen was
    truncating the evidence. It must request the API's maximum window, and the
    two numbers must not drift apart."""
    account_id = client.get("/queue").json()[0]["account_id"]
    assert client.get(f"/accounts/{account_id}",
                      params={"transaction_limit": 500}).status_code == 200
    assert client.get(f"/accounts/{account_id}",
                      params={"transaction_limit": 501}).status_code == 422
    assert "transaction_limit=500" in client.get("/").text


def test_ui_can_work_a_case_end_to_end_not_just_read_one(client):
    """Slice 7.7: the four lifecycle endpoints existed since 7.3, but nothing in
    the browser could reach them — the workbench was read-only, which is not a
    workbench. Every action must also name its analyst, because the case store
    refuses anonymous changes and the API refuses to invent a default."""
    html = client.get("/").text
    for endpoint in ("/assign", "/notes", "/close", "/reopen", "/dispositions"):
        assert endpoint in html
    assert "requireAnalyst" in html and "actor: analyst()" in html
    # dispositions are fetched, never hardcoded — a UI vocabulary of its own
    # would quietly destroy the statistics a regulator samples
    for disposition in cases.DISPOSITIONS:
        assert f'"{disposition}"' not in html


def test_ui_draws_the_chain_and_offers_the_narrative(client):
    """7.6 and 7.8 in the page: the chain is drawn as the path the money took
    with clickable hops, and a case can be drafted into a SAR narrative."""
    html = client.get("/").text
    assert "chainSvg" in html and "<svg" in html.replace("`<svg", "<svg")
    assert "openAccount" in html and "focusHop" in html
    assert "/narrative" in html and "Draft SAR narrative" in html


def test_ui_tiers_match_the_measured_evidence_hierarchy(client):
    """Slice 7.1 measured graph > rules > ML by precision; the queue is ordered
    that way deliberately, so a regression in the UI's ordering is a real bug."""
    html = client.get("/").text
    positions = [html.index(f'key: "{source}"') for source in ("graph", "rules", "ml")]
    assert positions == sorted(positions), "tiers must stay in measured precision order"
