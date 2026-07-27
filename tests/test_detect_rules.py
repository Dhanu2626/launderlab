import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.detect import rules
from launderlab.typology import (
    dormant_reactivation,
    high_risk_geography,
    mule_network,
    round_tripping,
    shell_company,
    structuring,
)
from launderlab.world.generate import load


@pytest.fixture(scope="module")
def clean_world(tmp_path_factory):
    # module-scoped: no rule ever writes to the ledger, so every test can share
    # one generated (uninjected) world safely
    conn = connect(tmp_path_factory.mktemp("clean") / "w.duckdb")
    load(conn, n=300, days=30, seed=99)
    return conn


def _accounts(conn, segment, limit):
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = ? ORDER BY account_id LIMIT ?", [segment, limit]
    ).fetchall()]


def test_rules_never_reference_scheme_labels():
    # the core quality-bar boundary: detection earns its alert from transaction
    # data alone. Checks actual SQL table references (FROM/JOIN scheme_labels),
    # not just the string "scheme_labels" anywhere - that would also flag this
    # module's own explanatory docstrings about the boundary it must respect.
    import inspect
    import re

    from launderlab.detect import rules as rules_module
    source = inspect.getsource(rules_module)
    assert not re.search(r"\b(FROM|JOIN)\s+scheme_labels\b", source, re.IGNORECASE)


def test_clean_world_has_almost_no_false_positives(clean_world):
    alerts = rules.run_all(clean_world)
    # 300 entirely legitimate customers; a well-tuned rules engine should stay quiet
    assert len(alerts) <= 2


@pytest.fixture()
def injected_world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=300, days=30, seed=42)
    return conn


def test_structuring_rule_catches_its_own_typology(injected_world):
    acct = _accounts(injected_world, "business", 1)[0]
    structuring.inject(injected_world, "T1", acct, date(2026, 7, 3), random.Random(1))
    caught = {a.account_id for a in rules.structuring_burst(injected_world)}
    assert acct in caught


def test_rapid_pass_through_catches_mule_hops(injected_world):
    chain = _accounts(injected_world, "salaried", 4)
    mule_network.inject(injected_world, "T2", chain, date(2026, 7, 3), random.Random(2))
    caught = {a.account_id for a in rules.rapid_pass_through(injected_world)}
    # source + intermediate mules all individually show the pattern; sink only
    # receives, so it's structurally invisible to a per-account pass-through rule
    assert chain[0] in caught
    assert chain[1] in caught


def test_counterparty_concentration_catches_shell_company(injected_world):
    acct = _accounts(injected_world, "business", 1)[0]
    shell_company.inject(injected_world, "T3", acct, date(2026, 7, 3), random.Random(3))
    caught = {a.account_id for a in rules.counterparty_concentration(injected_world)}
    assert acct in caught


def test_round_trip_catches_round_tripping_but_not_normal_ap_ar(injected_world):
    acct = _accounts(injected_world, "business", 3)[2]
    round_tripping.inject(injected_world, "T4", acct, date(2026, 7, 1), random.Random(4))
    caught = {a.account_id for a in rules.round_trip(injected_world)}
    assert acct in caught
    # the channel restriction to RTGS is what keeps ordinary NEFT/IMPS business
    # purchase-then-receipt cycles from tripping this rule - verify directly
    other_business = _accounts(injected_world, "business", 3)
    innocent = [a for a in other_business if a != acct]
    assert not (set(innocent) & caught)


def test_dormancy_burst_catches_reactivation_not_weekly_pocket_money(injected_world):
    student = _accounts(injected_world, "student", 1)[0]
    dormant_reactivation.inject(injected_world, "T5", student, random.Random(5))
    caught = {a.account_id for a in rules.dormancy_burst(injected_world)}
    assert student in caught
    # every OTHER student in this world lives on ordinary weekly pocket money,
    # which also "follows a gap" and is "big relative to their tiny average" -
    # the rule must not be fooled by that shape alone
    other_students = [a for a in _accounts(injected_world, "student", 20) if a != student]
    assert not (set(other_students) & caught)


def test_high_risk_geography_catches_flagged_countries(injected_world):
    acct = _accounts(injected_world, "business", 1)[0]
    high_risk_geography.inject(injected_world, "T6", acct, date(2026, 7, 3), random.Random(6),
                                n_transactions=1)
    caught = {a.account_id for a in rules.high_risk_geography(injected_world)}
    assert acct in caught


def test_run_all_combines_every_rule(injected_world):
    acct = _accounts(injected_world, "business", 1)[0]
    structuring.inject(injected_world, "T7", acct, date(2026, 7, 3), random.Random(7))
    alerts = rules.run_all(injected_world)
    assert any(a.account_id == acct and a.rule == "structuring_burst" for a in alerts)
