import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import mule_network
from launderlab.world.generate import load


@pytest.fixture()
def world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=200, days=30, seed=4)
    return conn


def _a_chain(conn, n=4) -> list[str]:
    rows = conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried', 'student') ORDER BY account_id LIMIT ?", [n]
    ).fetchall()
    return [r[0] for r in rows]


def test_injects_correct_leg_count_and_roles(world):
    chain = _a_chain(world, 4)
    n = mule_network.inject(world, "SCH-M1", chain, date(2026, 7, 3), random.Random(1),
                             total=1000000)
    assert n == 2 * len(chain) - 1  # entry leg + 2 legs per hop

    roles = world.execute(
        "SELECT t.account_id, l.role FROM transactions t"
        " JOIN scheme_labels l USING (txn_id) WHERE l.scheme_id = 'SCH-M1'"
        " ORDER BY t.account_id"
    ).fetchall()
    by_account = {}
    for acct, role in roles:
        by_account.setdefault(acct, set()).add(role)
    assert by_account[chain[0]] == {"source"}
    assert by_account[chain[-1]] == {"sink"}
    for mule in chain[1:-1]:
        assert by_account[mule] == {"mule"}

    typologies = {t for (t,) in world.execute(
        "SELECT typology FROM scheme_labels WHERE scheme_id = 'SCH-M1'"
    ).fetchall()}
    assert typologies == {"layering"}


def test_amount_decays_hop_over_hop(world):
    chain = _a_chain(world, 4)
    mule_network.inject(world, "SCH-M2", chain, date(2026, 7, 3), random.Random(2),
                         total=1000000)
    hop_amounts = [row[0] for row in world.execute(
        "SELECT t.amount::DOUBLE FROM transactions t JOIN scheme_labels l USING (txn_id)"
        " WHERE l.scheme_id = 'SCH-M2' AND t.direction = 'DR' ORDER BY t.ts"
    ).fetchall()]
    assert len(hop_amounts) == len(chain) - 1
    assert hop_amounts[0] < 1000000  # entry amount minus first cut
    for earlier, later in zip(hop_amounts, hop_amounts[1:]):
        assert later < earlier  # each further hop skims more off a shrinking pile


def test_timestamps_strictly_increase_along_chain(world):
    chain = _a_chain(world, 5)
    mule_network.inject(world, "SCH-M3", chain, date(2026, 7, 3), random.Random(3))
    ts_list = [row[0] for row in world.execute(
        "SELECT t.ts FROM transactions t JOIN scheme_labels l USING (txn_id)"
        " WHERE l.scheme_id = 'SCH-M3' AND t.direction = 'CR' ORDER BY t.ts"
    ).fetchall()]
    assert ts_list == sorted(ts_list)
    assert len(set(ts_list)) == len(ts_list)


def test_balances_reconcile_globally_after_injection(world):
    chain = _a_chain(world, 4)
    mule_network.inject(world, "SCH-M4", chain, date(2026, 7, 5), random.Random(4))

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
    chain = _a_chain(world, 4)
    other = world.execute(
        "SELECT account_id FROM accounts WHERE account_id NOT IN"
        " (" + ", ".join("?" * len(chain)) + ") LIMIT 1", chain,
    ).fetchone()[0]
    before = world.execute(
        "SELECT txn_id, balance_after FROM transactions WHERE account_id = ? ORDER BY txn_id",
        [other],
    ).fetchall()

    mule_network.inject(world, "SCH-M5", chain, date(2026, 7, 3), random.Random(5))

    after = world.execute(
        "SELECT txn_id, balance_after FROM transactions WHERE account_id = ? ORDER BY txn_id",
        [other],
    ).fetchall()
    assert before == after


def test_deterministic(world):
    chain = _a_chain(world, 4)
    n1 = mule_network.inject(world, "SCH-A", chain, date(2026, 7, 1), random.Random(9),
                              total=900000)

    conn2 = connect(":memory:")
    load(conn2, n=200, days=30, seed=4)
    n2 = mule_network.inject(conn2, "SCH-A", chain, date(2026, 7, 1), random.Random(9),
                              total=900000)
    assert n1 == n2


def test_chain_too_short_raises(world):
    chain = _a_chain(world, 1)
    with pytest.raises(ValueError):
        mule_network.inject(world, "SCH-X", chain, date(2026, 7, 1), random.Random(1))


def test_unknown_account_raises(world):
    chain = _a_chain(world, 2) + ["GHOST"]
    with pytest.raises(ValueError):
        mule_network.inject(world, "SCH-Y", chain, date(2026, 7, 1), random.Random(1))
