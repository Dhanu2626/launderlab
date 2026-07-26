"""The core banking ledger — a DuckDB database holding the synthetic bank."""

from __future__ import annotations

import csv
import tempfile
from importlib import resources
from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path("data") / "launderlab.duckdb"


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the ledger database (creating it if needed) and ensure the schema exists."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if db_path == ":memory:":
        conn = duckdb.connect()
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(path))
    conn.execute(_schema_sql())
    return conn


def _schema_sql() -> str:
    return resources.files("launderlab.db").joinpath("schema.sql").read_text(encoding="utf-8")


def bulk_insert(conn: duckdb.DuckDBPyConnection, table: str, columns: list[str],
                 rows: list[tuple]) -> None:
    """Load many rows fast via a temp CSV + DuckDB's native COPY.

    ~40k rows/sec measured, vs. executemany which doesn't finish 200k rows in 2 minutes —
    row-by-row inserts pay per-statement overhead that COPY skips entirely. Needed once the
    world scales past a few hundred customers; not worth it below that (see seed.py).
    """
    if not rows:
        return
    with tempfile.NamedTemporaryFile(mode="w", newline="", suffix=".csv", delete=False,
                                      encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
        path = f.name
    try:
        col_list = ", ".join(columns)
        conn.execute(
            f"COPY {table} ({col_list}) FROM '{path}' (HEADER, FORMAT CSV, NULLSTR '')"
        )
    finally:
        Path(path).unlink(missing_ok=True)


def reverse_opening(direction: str, amount, balance_after):
    """Derive the balance *before* one transaction from its direction/amount/balance_after —
    the same trick a statement's "Opening balance" row uses (see FIELD-NOTES Day 3)."""
    return balance_after - amount if direction == "CR" else balance_after + amount


def account_opening_balance(conn: duckdb.DuckDBPyConnection, account_id: str):
    """The balance an account started with, derived from its earliest transaction.
    Returns None if the account has no transactions."""
    row = conn.execute(
        "SELECT direction, amount, balance_after FROM transactions"
        " WHERE account_id = ? ORDER BY ts, txn_id LIMIT 1",
        [account_id],
    ).fetchone()
    return reverse_opening(*row) if row else None


def bulk_update(conn: duckdb.DuckDBPyConnection, table: str, key_col: str, set_col: str,
                 updates: list[tuple]) -> None:
    """Apply many (new_value, key) updates in one set-based statement instead of one
    UPDATE per row — the UPDATE equivalent of bulk_insert's COPY trick. Row-by-row
    UPDATE inherits the same executemany overhead measured for INSERT on Day 6
    (~24 rows/sec); this stays fast because DuckDB does the join, not Python.

    Scoped to BIGINT keys + numeric values — every current use case (rewriting
    balance_after by txn_id) — not a fully general multi-type helper.
    """
    if not updates:
        return
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _bulk_update_src (bkey BIGINT, bval DOUBLE)")
    conn.execute("DELETE FROM _bulk_update_src")
    bulk_insert(conn, "_bulk_update_src", ["bkey", "bval"], [(k, v) for v, k in updates])
    conn.execute(
        f"UPDATE {table} SET {set_col} = src.bval FROM _bulk_update_src src"
        f" WHERE {table}.{key_col} = src.bkey"
    )


def recompute_account_balances(conn: duckdb.DuckDBPyConnection, account_id: str, opening) -> None:
    """Replay an account's full transaction history (old + any newly injected rows) in
    time order and rewrite every balance_after from `opening` forward. Call this after
    inserting a transaction into the middle of an already-generated history — every row
    after the insertion point needs its running balance recalculated."""
    rows = conn.execute(
        "SELECT txn_id, direction, amount FROM transactions"
        " WHERE account_id = ? ORDER BY ts, txn_id",
        [account_id],
    ).fetchall()
    balance = opening
    updates = []
    for txn_id, direction, amount in rows:
        balance += amount if direction == "CR" else -amount
        updates.append((float(balance), txn_id))
    bulk_update(conn, "transactions", "txn_id", "balance_after", updates)


def table_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Row counts for each core table — the heartbeat of the bank."""
    tables = ["customers", "accounts", "transactions", "scheme_labels"]
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
