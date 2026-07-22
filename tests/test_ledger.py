from datetime import datetime

import duckdb
import pytest

from launderlab.db.ledger import connect, table_counts


@pytest.fixture()
def conn(tmp_path):
    return connect(tmp_path / "test.duckdb")


def _seed_account(conn):
    conn.execute(
        "INSERT INTO customers VALUES ('C001','Asha Rao','1994-03-12','salaried',"
        "'Hyderabad','full','low',?)",
        [datetime(2026, 1, 1)],
    )
    conn.execute(
        "INSERT INTO accounts VALUES ('A001','C001','savings','LLAB0000001','active',?)",
        [datetime(2026, 1, 2)],
    )


def test_schema_creates_core_tables(conn):
    counts = table_counts(conn)
    assert set(counts) == {"customers", "accounts", "transactions", "scheme_labels"}
    assert all(n == 0 for n in counts.values())


def test_transaction_insert_and_readback(conn):
    _seed_account(conn)
    conn.execute(
        """INSERT INTO transactions (ts, account_id, direction, channel, amount,
               counterparty_name, counterparty_ref, narration, balance_after)
           VALUES (?, 'A001', 'CR', 'UPI', 49500.00, 'Ravi K', 'ravi.k@okaxis',
                   'UPI/CR/519204/ravi.k@okaxis', 51210.00)""",
        [datetime(2026, 7, 3, 14, 5)],
    )
    direction, channel, amount, balance = conn.execute(
        "SELECT direction, channel, amount, balance_after FROM transactions"
    ).fetchone()
    assert (direction, channel) == ("CR", "UPI")
    assert amount == 49500
    assert balance == 51210


def test_amount_must_be_positive(conn):
    _seed_account(conn)
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            """INSERT INTO transactions (ts, account_id, direction, channel, amount,
                   narration, balance_after)
               VALUES (?, 'A001', 'DR', 'UPI', -5, 'bad', 0)""",
            [datetime(2026, 7, 3)],
        )


def test_unknown_account_rejected(conn):
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            """INSERT INTO transactions (ts, account_id, direction, channel, amount,
                   narration, balance_after)
               VALUES (?, 'GHOST', 'DR', 'UPI', 10, 'x', 0)""",
            [datetime(2026, 7, 3)],
        )


def test_scheme_labels_link_to_transactions(conn):
    _seed_account(conn)
    conn.execute(
        """INSERT INTO transactions (ts, account_id, direction, channel, amount,
               narration, balance_after)
           VALUES (?, 'A001', 'CR', 'CASH', 9500, 'CASH DEP/BR-HYD-01', 9500)""",
        [datetime(2026, 7, 4)],
    )
    txn_id = conn.execute("SELECT txn_id FROM transactions").fetchone()[0]
    conn.execute(
        "INSERT INTO scheme_labels VALUES (?, 'SCH-0001', 'structuring', 'placement')",
        [txn_id],
    )
    amount, typology = conn.execute(
        "SELECT t.amount, l.typology FROM transactions t JOIN scheme_labels l USING (txn_id)"
    ).fetchone()
    assert typology == "structuring"
    assert amount == 9500
