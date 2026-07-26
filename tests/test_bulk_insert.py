from datetime import datetime

from launderlab.db.ledger import bulk_insert, connect


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
