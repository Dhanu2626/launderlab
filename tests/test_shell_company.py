import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import shell_company
from launderlab.typology.shell_company import _split_uneven
from launderlab.world.generate import load


@pytest.fixture()
def world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=200, days=30, seed=6)
    return conn


def _a_business_account(conn) -> str:
    return conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' LIMIT 1"
    ).fetchone()[0]


def test_split_uneven_always_positive_and_exact():
    for seed in range(200):
        rng = random.Random(seed)
        for n in range(2, 9):
            total = rng.randrange(100000, 5000000)
            pieces = _split_uneven(rng, total, n)
            assert len(pieces) == n
            assert all(p > 0 for p in pieces), (seed, n, total, pieces)
            assert sum(pieces) == total


def test_injects_few_large_concentrated_payments(world):
    acct = _a_business_account(world)
    n = shell_company.inject(world, "SCH-S1", acct, date(2026, 7, 3), random.Random(1),
                              target_total=2000000, n_invoices=5)
    assert n == 5

    rows = world.execute(
        "SELECT direction, channel, amount::DOUBLE, counterparty_name FROM transactions t"
        " JOIN scheme_labels l USING (txn_id) WHERE l.scheme_id = 'SCH-S1'"
    ).fetchall()
    assert len(rows) == 5
    assert all(direction == "CR" and channel in ("NEFT", "IMPS") for direction, channel, _, _
               in rows)
    shells = {name for *_, name in rows}
    assert len(shells) == 1  # every invoice from the SAME shell counterparty
    assert round(sum(amt for _, _, amt, _ in rows)) == 2000000


def test_labels_role_and_typology(world):
    acct = _a_business_account(world)
    shell_company.inject(world, "SCH-S2", acct, date(2026, 7, 3), random.Random(2),
                          target_total=1800000)
    typologies, roles = zip(*world.execute(
        "SELECT typology, role FROM scheme_labels WHERE scheme_id = 'SCH-S2'"
    ).fetchall())
    assert set(typologies) == {"shell_company"}
    assert set(roles) == {"integration"}


def test_balances_still_reconcile_globally(world):
    acct = _a_business_account(world)
    shell_company.inject(world, "SCH-S3", acct, date(2026, 7, 5), random.Random(3))

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


def test_deterministic(world):
    acct = _a_business_account(world)
    n1 = shell_company.inject(world, "SCH-A", acct, date(2026, 7, 1), random.Random(9),
                               target_total=2500000)

    conn2 = connect(":memory:")
    load(conn2, n=200, days=30, seed=6)
    n2 = shell_company.inject(conn2, "SCH-A", acct, date(2026, 7, 1), random.Random(9),
                               target_total=2500000)
    assert n1 == n2


def test_unknown_account_raises(world):
    with pytest.raises(ValueError):
        shell_company.inject(world, "SCH-X", "GHOST", date(2026, 7, 1), random.Random(1))
