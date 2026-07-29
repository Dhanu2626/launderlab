import json

import pytest

from launderlab.db.ledger import connect
from launderlab.world.generate import load

mcp_server = pytest.importorskip("launderlab.mcp_server",
                                  reason="MCP SDK not installed (pip install -e .[mcp])")


@pytest.fixture(scope="module", autouse=True)
def server_world(tmp_path_factory, monkeypatch_module):
    """Point the server at a throwaway world, so tests never touch data/launderlab.duckdb."""
    path = tmp_path_factory.mktemp("mcp") / "w.duckdb"
    conn = connect(path)
    load(conn, n=40, days=20, seed=7)
    conn.close()

    monkeypatch_module.setenv("LAUNDERLAB_DB", str(path))
    mcp_server._conn = None
    yield
    mcp_server._conn = None


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


def test_screen_name_catches_transliteration_variant():
    # 'Farhan Ali' vs watchlist 'Farhaan Ali' — the whole reason screening is fuzzy.
    # An exact-match screen would clear this and miss the sanctioned party.
    result = mcp_server.screen_name(name="Farhan Ali")
    assert result["decision"] == "REVIEW"
    assert any("Farhaan" in m["name"] for m in result["matches"])


def test_screen_name_ignores_unrelated_name():
    result = mcp_server.screen_name(name="Rohit Sharma")
    assert result["decision"] == "NO_HIT"
    assert result["matches"] == []


def test_screen_name_catches_phonetic_spelling_variant():
    # Sheikh/Shaikh are metaphone-identical (XKH) — the phonetic leg the ponytail
    # comment asked for, on top of the edit-distance leg
    result = mcp_server.screen_name(name="Imran Sheikh")
    assert result["decision"] == "REVIEW"
    assert any(m["name"] == "Imraan Shaikh" for m in result["matches"])


def test_screen_name_rejects_a_different_first_name():
    # two of three tokens match the listed 'Hassan Abdullah Al-Amri', but a
    # different given name means a different person
    assert mcp_server.screen_name(name="Muhammed Abdullah Al-Amri")["decision"] == "NO_HIT"


def test_screen_name_does_not_flag_a_shared_surname():
    # 'Suresh Gupta' is a listed PEP; a different Gupta must not inherit that hit
    assert mcp_server.screen_name(name="Rahul Gupta")["decision"] == "NO_HIT"


def test_screen_name_delegates_to_the_shared_matcher():
    # the server must not carry its own second copy of the matching logic, or the
    # offline precision/recall numbers would describe different code than this tool
    import inspect

    source = inspect.getsource(mcp_server)
    assert "SequenceMatcher" not in source
    assert "matcher.screen(" in source


def test_adverse_media_check_returns_expected_shape():
    result = mcp_server.adverse_media_check(name="Farhaan Ali")
    assert set(result) == {"query", "threshold", "articles_searched", "matches",
                           "decision", "note"}
    assert result["decision"] in {"REVIEW", "NO_HIT"}
    for match in result["matches"]:
        assert match["category"] != "none"
        assert match["score"] >= result["threshold"]


def test_screen_name_is_word_order_insensitive():
    assert mcp_server.screen_name(name="Ali Farhaan")["decision"] == "REVIEW"


def test_screen_name_flags_high_risk_jurisdiction():
    result = mcp_server.screen_name(name="ACME TRADING IRAN LLC")
    assert "IRAN" in result["high_risk_jurisdiction"]
    assert result["decision"] == "REVIEW"


def test_notice_row_never_matches():
    # the watchlist's provenance banner is data, not a person — it must not screen
    assert all(m["type"] != "notice" for m in mcp_server.screen_name(name="SYNTHETIC")["matches"])


def test_every_call_is_audited():
    before = len(mcp_server.audit_trail(limit=500)["entries"])
    mcp_server.screen_name(name="Zhang Wei Ming")
    after = mcp_server.audit_trail(limit=500)["entries"]
    assert len(after) > before
    latest = next(e for e in after if e["tool"] == "screen_name")
    assert json.loads(latest["params"])["name"] == "Zhang Wei Ming"
    assert latest["outcome"] == "ok"


def test_tools_accept_positional_arguments_and_still_audit_them_by_name():
    """Every other test in this file calls with keywords, which is why nobody
    noticed the audit decorator only accepted them: `screen_name("Asha Rao")`
    raised "takes 0 positional arguments" for a call matching the signature
    `@wraps` advertises. MCP itself passes a JSON object, so it worked over the
    wire and broke only for Python callers.

    The audit row must not change shape either — a `params` column that means
    something different depending on how the caller passed arguments is one a
    reviewer has to interpret rather than read."""
    positional = mcp_server.screen_name("Zhang Wei Ming")
    keyword = mcp_server.screen_name(name="Zhang Wei Ming")
    assert positional == keyword

    entry = next(e for e in mcp_server.audit_trail(limit=50)["entries"]
                 if e["tool"] == "screen_name")
    params = json.loads(entry["params"])
    assert params["name"] == "Zhang Wei Ming", "positional arg was not logged by name"
    # defaults are recorded too, so the row shows what actually ran
    assert "threshold" in params


def test_failed_calls_are_audited_too():
    # a lookup that errors is exactly the call a reviewer most wants to see
    with pytest.raises(ValueError):
        mcp_server.customer_profile(customer_id="NOPE")
    latest = next(e for e in mcp_server.audit_trail(limit=50)["entries"]
                  if e["tool"] == "customer_profile")
    assert latest["outcome"].startswith("error: ValueError")


def test_transaction_history_caps_limit():
    assert mcp_server.transaction_history(account_id="A001", limit=99999)["returned"] <= 500


def test_run_detection_returns_alert_shape():
    result = mcp_server.run_detection()
    assert set(result) == {"alert_count", "accounts_flagged", "alerts"}
    for alert in result["alerts"]:
        assert {"account_id", "rule", "reason", "ts", "amount"} == set(alert)


def test_server_never_reads_scheme_labels():
    # same quality-bar boundary as the rules engine: this server is blue-team
    # tooling, so ground truth stays invisible to it. Checks real SQL references,
    # not the string in the module's own docstrings explaining the rule.
    import inspect
    import re

    source = inspect.getsource(mcp_server)
    assert not re.search(r"\b(FROM|JOIN)\s+scheme_labels\b", source, re.IGNORECASE)


def test_server_exposes_no_generic_sql_tool():
    # a raw-SQL tool would route straight around every boundary above
    names = {fn.__name__ for fn in [mcp_server.screen_name, mcp_server.customer_profile,
                                     mcp_server.transaction_history, mcp_server.run_detection,
                                     mcp_server.audit_trail]}
    assert not {"query", "sql", "execute", "raw_query"} & names
