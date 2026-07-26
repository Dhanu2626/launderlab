import pytest

from launderlab.db.ledger import connect
from launderlab.world.generate import load
from launderlab.world.seed import account_id


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    # 300 customers, full 30-day window: small enough to run fast, large enough to
    # exercise every segment's monthly-cadence events (salary, rent, EMI, remittance).
    c = connect(tmp_path_factory.mktemp("gen") / "g.duckdb")
    load(c, n=300, days=30, seed=5)
    return c


def test_population_and_transactions_loaded(conn):
    assert conn.execute("SELECT count(*) FROM customers").fetchone()[0] == 300
    assert conn.execute("SELECT count(*) FROM accounts").fetchone()[0] == 300
    n = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
    assert n > 1000  # 300 customers over 30 days should generate thousands of rows


def test_balances_reconcile(conn):
    # derive each account's opening balance by reversing its first transaction,
    # then replay every row in order and confirm the running total matches
    rows = conn.execute(
        "SELECT account_id, direction, amount, balance_after FROM transactions"
        " ORDER BY ts, txn_id"
    ).fetchall()
    running = {}
    for acct, direction, amount, balance_after in rows:
        if acct not in running:
            running[acct] = balance_after - amount if direction == "CR" else balance_after + amount
        running[acct] += amount if direction == "CR" else -amount
        assert running[acct] == balance_after


def test_no_negative_balances(conn):
    assert conn.execute("SELECT min(balance_after) FROM transactions").fetchone()[0] >= 0


def test_every_segment_present_and_active(conn):
    segments = {r[0] for r in conn.execute("SELECT DISTINCT segment FROM customers").fetchall()}
    assert segments == {"salaried", "student", "merchant", "business", "nri"}
    active = conn.execute("SELECT count(DISTINCT account_id) FROM transactions").fetchone()[0]
    # nri accounts only get a remittance + occasional shopping; with 300 people some
    # segments are tiny (nri ~5%), so allow a handful of quiet accounts rather than 100%
    assert active >= 280


def test_deterministic():
    a = connect(":memory:")
    b = connect(":memory:")
    na = load(a, n=200, days=14, seed=11)
    nb = load(b, n=200, days=14, seed=11)
    assert na == nb
    assert (conn_sum(a) == conn_sum(b))


def conn_sum(conn):
    return conn.execute("SELECT sum(amount) FROM transactions").fetchone()[0]


def test_account_id_prefix_matches_customer_id(conn):
    row = conn.execute("SELECT customer_id, account_id FROM accounts LIMIT 1").fetchone()
    customer_id, acct = row
    assert acct == account_id(customer_id)
