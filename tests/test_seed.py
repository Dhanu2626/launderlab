import pytest

from launderlab.db.ledger import connect
from launderlab.world.seed import CAST, account_id, load


def _fresh(tmp_path, name="seed.duckdb"):
    conn = connect(tmp_path / name)
    load(conn)
    return conn


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    # module-scoped: these tests only read the seeded world, so one load suffices
    return _fresh(tmp_path_factory.mktemp("seed"))


def test_cast_loaded(conn):
    assert conn.execute("SELECT count(*) FROM customers").fetchone()[0] == 25
    assert conn.execute("SELECT count(*) FROM accounts").fetchone()[0] == 25
    n = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
    assert 400 <= n <= 1500


def test_balances_reconcile(conn):
    running = {account_id(p.customer_id): p.opening for p in CAST}
    rows = conn.execute(
        "SELECT account_id, direction, amount, balance_after FROM transactions"
        " ORDER BY ts, txn_id"
    ).fetchall()
    for acct, direction, amount, balance_after in rows:
        running[acct] += amount if direction == "CR" else -amount
        assert running[acct] == balance_after


def test_no_negative_balances(conn):
    assert conn.execute("SELECT min(balance_after) FROM transactions").fetchone()[0] >= 0


def test_every_account_has_activity(conn):
    active = conn.execute("SELECT count(DISTINCT account_id) FROM transactions").fetchone()[0]
    assert active == 25


def test_deterministic(tmp_path):
    a = _fresh(tmp_path, "a.duckdb")
    b = _fresh(tmp_path, "b.duckdb")
    qa = a.execute("SELECT count(*), sum(amount) FROM transactions").fetchone()
    qb = b.execute("SELECT count(*), sum(amount) FROM transactions").fetchone()
    assert qa == qb
