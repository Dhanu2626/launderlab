import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology.structuring import inject
from launderlab.world.generate import load


@pytest.fixture()
def world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=150, days=30, seed=3)
    return conn


def _a_business_account(conn) -> str:
    return conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' LIMIT 1"
    ).fetchone()[0]


def test_injects_labeled_cash_deposits_under_ceiling(world):
    acct = _a_business_account(world)
    n = inject(world, "SCH-TEST-1", acct, date(2026, 7, 1),
               random.Random(1), target_total=1000000, deposit_ceiling=90000)

    rows = world.execute(
        "SELECT direction, channel, amount::DOUBLE FROM transactions t"
        " JOIN scheme_labels l USING (txn_id) WHERE l.scheme_id = 'SCH-TEST-1'"
    ).fetchall()
    assert len(rows) == n
    assert all(direction == "CR" and channel == "CASH" for direction, channel, _ in rows)
    assert all(amount <= 90000 for *_ , amount in rows)
    assert round(sum(amount for *_, amount in rows)) == 1000000


def test_labels_role_and_typology(world):
    acct = _a_business_account(world)
    inject(world, "SCH-TEST-2", acct, date(2026, 7, 1),
           random.Random(2), target_total=850000)
    typologies, roles = zip(*world.execute(
        "SELECT typology, role FROM scheme_labels WHERE scheme_id = 'SCH-TEST-2'"
    ).fetchall())
    assert set(typologies) == {"structuring"}
    assert set(roles) == {"placement"}


def test_balances_still_reconcile_globally(world):
    acct = _a_business_account(world)
    inject(world, "SCH-TEST-3", acct, date(2026, 7, 5),
           random.Random(3), target_total=1200000)

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
    assert world.execute("SELECT min(balance_after) FROM transactions").fetchone()[0] >= 0


def test_other_accounts_untouched(world):
    other = world.execute(
        "SELECT account_id FROM accounts WHERE account_id != ?",
        [_a_business_account(world)],
    ).fetchone()[0]
    before = world.execute(
        "SELECT txn_id, balance_after FROM transactions WHERE account_id = ? ORDER BY txn_id",
        [other],
    ).fetchall()

    acct = _a_business_account(world)
    inject(world, "SCH-TEST-4", acct, date(2026, 7, 1), random.Random(4))

    after = world.execute(
        "SELECT txn_id, balance_after FROM transactions WHERE account_id = ? ORDER BY txn_id",
        [other],
    ).fetchall()
    assert before == after


def test_deterministic(world):
    acct = _a_business_account(world)
    n1 = inject(world, "SCH-A", acct, date(2026, 7, 1),
                random.Random(9), target_total=900000)

    conn2 = connect(":memory:")
    load(conn2, n=150, days=30, seed=3)
    n2 = inject(conn2, "SCH-A", acct, date(2026, 7, 1),
                random.Random(9), target_total=900000)
    assert n1 == n2


def test_unknown_account_raises(world):
    with pytest.raises(ValueError):
        inject(world, "SCH-X", "GHOST", date(2026, 7, 1), random.Random(1))
