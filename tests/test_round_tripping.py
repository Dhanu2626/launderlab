import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import round_tripping
from launderlab.world.generate import load


@pytest.fixture()
def world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=200, days=30, seed=7)
    return conn


def _business_accounts(conn, limit=10) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id LIMIT ?", [limit]
    ).fetchall()]


def test_injects_departure_and_return_with_inflation(world):
    acct = _business_accounts(world, 1)[0]
    n = round_tripping.inject(world, "SCH-R1", acct, date(2026, 7, 3), random.Random(1))
    assert n == 2

    rows = world.execute(
        "SELECT t.direction, t.amount::DOUBLE, t.counterparty_name, l.role"
        " FROM transactions t JOIN scheme_labels l USING (txn_id)"
        " WHERE l.scheme_id = 'SCH-R1' ORDER BY t.ts"
    ).fetchall()
    assert len(rows) == 2
    (dr_dir, dr_amt, dr_name, dr_role), (cr_dir, cr_amt, cr_name, cr_role) = rows
    assert (dr_dir, dr_role) == ("DR", "departure")
    assert (cr_dir, cr_role) == ("CR", "return")
    assert cr_amt > dr_amt  # inflated on return
    assert dr_name != cr_name  # different shell name each leg

    typologies = {t for (t,) in world.execute(
        "SELECT typology FROM scheme_labels WHERE scheme_id = 'SCH-R1'"
    ).fetchall()}
    assert typologies == {"round_tripping"}


def test_never_overdraws_across_many_accounts_and_seeds(world):
    # stress test: the safety cap is derived from each account's own historical
    # minimum, so it must hold no matter which account or random draw we throw at it
    accounts = _business_accounts(world, 10)
    for i, acct in enumerate(accounts):
        for seed in range(5):
            round_tripping.inject(world, f"SCH-STRESS-{i}-{seed}", acct,
                                   date(2026, 7, 1), random.Random(seed))
    min_bal = world.execute("SELECT min(balance_after) FROM transactions").fetchone()[0]
    assert float(min_bal) >= 0


def test_balances_still_reconcile_globally(world):
    acct = _business_accounts(world, 1)[0]
    round_tripping.inject(world, "SCH-R2", acct, date(2026, 7, 5), random.Random(3))

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


def test_deterministic(world):
    acct = _business_accounts(world, 1)[0]
    n1 = round_tripping.inject(world, "SCH-A", acct, date(2026, 7, 1), random.Random(9))

    conn2 = connect(":memory:")
    load(conn2, n=200, days=30, seed=7)
    n2 = round_tripping.inject(conn2, "SCH-A", acct, date(2026, 7, 1), random.Random(9))
    assert n1 == n2


def test_unknown_account_raises(world):
    with pytest.raises(ValueError):
        round_tripping.inject(world, "SCH-X", "GHOST", date(2026, 7, 1), random.Random(1))
