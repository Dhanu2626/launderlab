import random

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import dormant_reactivation
from launderlab.world.generate import load


@pytest.fixture()
def world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=200, days=30, seed=8)
    return conn


def _low_activity_accounts(conn, limit=10) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM transactions GROUP BY account_id"
        " ORDER BY count(*) ASC LIMIT ?", [limit]
    ).fetchall()]


def test_reactivation_lands_after_last_existing_activity(world):
    acct = _low_activity_accounts(world, 1)[0]
    last_before = world.execute(
        "SELECT max(ts) FROM transactions WHERE account_id = ?", [acct]
    ).fetchone()[0]

    dormant_reactivation.inject(world, "SCH-D1", acct, random.Random(1))

    reactivation_ts = world.execute(
        "SELECT min(t.ts) FROM transactions t JOIN scheme_labels l USING (txn_id)"
        " WHERE l.scheme_id = 'SCH-D1' AND l.role = 'reactivation'"
    ).fetchone()[0]
    assert reactivation_ts > last_before


def test_credit_then_rapid_cashout(world):
    acct = _low_activity_accounts(world, 1)[0]
    n = dormant_reactivation.inject(world, "SCH-D2", acct, random.Random(2),
                                     burst_total=1000000, n_cashouts=3)
    assert n == 4  # 1 reactivation credit + 3 cashout debits

    rows = world.execute(
        "SELECT t.direction, t.amount::DOUBLE, l.role FROM transactions t"
        " JOIN scheme_labels l USING (txn_id) WHERE l.scheme_id = 'SCH-D2' ORDER BY t.ts"
    ).fetchall()
    assert rows[0][0] == "CR" and rows[0][2] == "reactivation"
    assert rows[0][1] == 1000000
    assert all(d == "DR" and role == "cashout" for d, _, role in rows[1:])
    cashed_out = sum(amt for _, amt, _ in rows[1:])
    assert 0.90 * 1000000 <= cashed_out <= 0.97 * 1000000

    typologies = {t for (t,) in world.execute(
        "SELECT typology FROM scheme_labels WHERE scheme_id = 'SCH-D2'"
    ).fetchall()}
    assert typologies == {"dormant_reactivation"}


def test_never_overdraws_across_many_accounts_and_seeds(world):
    accounts = _low_activity_accounts(world, 10)
    for i, acct in enumerate(accounts):
        for seed in range(5):
            dormant_reactivation.inject(world, f"SCH-STRESS-{i}-{seed}", acct,
                                         random.Random(seed))
    min_bal = world.execute("SELECT min(balance_after) FROM transactions").fetchone()[0]
    assert float(min_bal) >= 0


def test_balances_still_reconcile_globally(world):
    acct = _low_activity_accounts(world, 1)[0]
    dormant_reactivation.inject(world, "SCH-D3", acct, random.Random(3))

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
    acct = _low_activity_accounts(world, 1)[0]
    n1 = dormant_reactivation.inject(world, "SCH-A", acct, random.Random(9))

    conn2 = connect(":memory:")
    load(conn2, n=200, days=30, seed=8)
    n2 = dormant_reactivation.inject(conn2, "SCH-A", acct, random.Random(9))
    assert n1 == n2


def test_unknown_account_raises(world):
    with pytest.raises(ValueError):
        dormant_reactivation.inject(world, "SCH-X", "GHOST", random.Random(1))
