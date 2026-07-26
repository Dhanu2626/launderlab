from datetime import datetime

from launderlab.db.ledger import bulk_insert, bulk_update, connect


def test_bulk_insert_round_trips_values(tmp_path):
    conn = connect(tmp_path / "b.duckdb")
    conn.execute(
        "INSERT INTO customers VALUES ('C1','x','2000-01-01','salaried','Hyderabad',"
        "'full','low',?)", [datetime(2020, 1, 1)],
    )
    conn.execute(
        "INSERT INTO accounts VALUES ('A1','C1','savings','X','active',?)",
        [datetime(2020, 1, 1)],
    )
    rows = [
        (datetime(2026, 7, 1, 6, 15), "A1", "CR", "UPI", 85000.0, None, None,
         "ATM-CASH/DR/HYD-27", 12345.5),
        (datetime(2026, 7, 2, 9, 0), "A1", "DR", "NEFT", 1234.75, "Some Payee", "ref@bank",
         "has, a comma", 9999.99),
    ]
    bulk_insert(conn, "transactions",
                ["ts", "account_id", "direction", "channel", "amount", "counterparty_name",
                 "counterparty_ref", "narration", "balance_after"], rows)

    got = conn.execute(
        "SELECT ts, amount::DOUBLE, counterparty_name, narration, balance_after::DOUBLE"
        " FROM transactions ORDER BY ts"
    ).fetchall()
    assert got[0] == (datetime(2026, 7, 1, 6, 15), 85000.0, None, "ATM-CASH/DR/HYD-27", 12345.5)
    assert got[1] == (datetime(2026, 7, 2, 9, 0), 1234.75, "Some Payee", "has, a comma", 9999.99)


def test_bulk_insert_empty_rows_is_noop(tmp_path):
    conn = connect(tmp_path / "b2.duckdb")
    bulk_insert(conn, "transactions", ["ts"], [])
    assert conn.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0


def test_bulk_update_rewrites_only_targeted_rows(tmp_path):
    conn = connect(tmp_path / "b3.duckdb")
    conn.execute(
        "INSERT INTO customers VALUES ('C1','x','2000-01-01','salaried','Hyderabad',"
        "'full','low',?)", [datetime(2020, 1, 1)],
    )
    conn.execute(
        "INSERT INTO accounts VALUES ('A1','C1','savings','X','active',?)",
        [datetime(2020, 1, 1)],
    )
    bulk_insert(conn, "transactions",
                ["ts", "account_id", "direction", "channel", "amount", "narration",
                 "balance_after"],
                [(datetime(2026, 1, 1), "A1", "CR", "UPI", 100.0, "a", 100.0),
                 (datetime(2026, 1, 2), "A1", "CR", "UPI", 50.0, "b", 150.0),
                 (datetime(2026, 1, 3), "A1", "CR", "UPI", 25.0, "c", 175.0)])
    ids = [r[0] for r in conn.execute("SELECT txn_id FROM transactions ORDER BY ts").fetchall()]

    bulk_update(conn, "transactions", "txn_id", "balance_after",
                [(9999.0, ids[0]), (8888.0, ids[2])])

    got = dict(conn.execute("SELECT txn_id, balance_after::DOUBLE FROM transactions").fetchall())
    assert got[ids[0]] == 9999.0
    assert got[ids[1]] == 150.0
    assert got[ids[2]] == 8888.0


def test_bulk_update_empty_is_noop(tmp_path):
    conn = connect(tmp_path / "b4.duckdb")
    bulk_update(conn, "transactions", "txn_id", "balance_after", [])
    assert conn.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
