"""Phase 2 capstone: all six typologies injected together onto overlapping
accounts, proving the injection engine composes correctly — not just that each
typology works alone. This is the test three real bugs this batch (Days 9, 10,
12) would have been caught by immediately if it had existed from the start;
it exists now as a permanent regression guard against that whole class of bug.
"""

import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
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
def world(tmp_path_factory):
    conn = connect(tmp_path_factory.mktemp("cap") / "w.duckdb")
    load(conn, n=1000, days=30, seed=42)

    rng = random.Random(100)
    business = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id LIMIT 5"
    ).fetchall()]
    nri_or_business = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('business', 'nri') ORDER BY account_id LIMIT 5"
    ).fetchall()]
    sal_students = [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried', 'student') ORDER BY account_id LIMIT 20"
    ).fetchall()]
    low_activity = [r[0] for r in conn.execute(
        "SELECT account_id FROM transactions GROUP BY account_id"
        " ORDER BY count(*) ASC LIMIT 5"
    ).fetchall()]

    # Deliberately overlapping: the SAME business accounts get four different
    # typologies each, since that's the harder, more realistic composability proof.
    for i, acct in enumerate(business):
        structuring.inject(conn, f"CAP-STRUCT-{i}", acct, date(2026, 7, 2), rng)
        shell_company.inject(conn, f"CAP-SHELL-{i}", acct, date(2026, 7, 3), rng)
        round_tripping.inject(conn, f"CAP-RT-{i}", acct, date(2026, 7, 4), rng)
    for i, acct in enumerate(nri_or_business):
        high_risk_geography.inject(conn, f"CAP-GEO-{i}", acct, date(2026, 7, 5), rng)
    for i in range(5):
        chain = sal_students[i * 4:(i + 1) * 4]
        mule_network.inject(conn, f"CAP-MULE-{i}", chain, date(2026, 7, 6), rng)
    for i, acct in enumerate(low_activity):
        dormant_reactivation.inject(conn, f"CAP-DORM-{i}", acct, rng)

    return conn


def test_all_six_typologies_present(world):
    typologies = {t for (t,) in world.execute(
        "SELECT DISTINCT typology FROM scheme_labels"
    ).fetchall()}
    assert typologies == {
        "structuring", "layering", "shell_company", "round_tripping",
        "dormant_reactivation", "high_risk_geography",
    }


def test_some_accounts_run_multiple_typologies(world):
    overlap = world.execute("""
        SELECT account_id, count(DISTINCT typology) AS n_types
        FROM transactions t JOIN scheme_labels l USING (txn_id)
        GROUP BY account_id HAVING n_types > 1
    """).fetchall()
    assert len(overlap) >= 5  # the 5 business accounts each got 3 typologies


def test_global_reconciliation_across_entire_ledger(world):
    running = {}
    rows = world.execute(
        "SELECT account_id, direction, amount, balance_after FROM transactions"
        " ORDER BY account_id, ts, txn_id"
    ).fetchall()
    for account_id, direction, amount, balance_after in rows:
        if account_id not in running:
            running[account_id] = balance_after - amount if direction == "CR" \
                else balance_after + amount
        running[account_id] += amount if direction == "CR" else -amount
        assert running[account_id] == balance_after


def test_no_negative_balances_anywhere(world):
    min_bal = world.execute("SELECT min(balance_after) FROM transactions").fetchone()[0]
    assert float(min_bal) >= 0


def test_ground_truth_never_double_labels_same_scheme_and_txn(world):
    # PRIMARY KEY (txn_id, scheme_id) on scheme_labels enforces this at the DB
    # level already; this test documents and re-confirms the invariant explicitly
    dupes = world.execute("""
        SELECT txn_id, scheme_id, count(*) FROM scheme_labels
        GROUP BY txn_id, scheme_id HAVING count(*) > 1
    """).fetchall()
    assert dupes == []
