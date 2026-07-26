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


def table_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Row counts for each core table — the heartbeat of the bank."""
    tables = ["customers", "accounts", "transactions", "scheme_labels"]
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
