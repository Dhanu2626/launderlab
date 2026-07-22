"""One-command demo: initialise the ledger and show the bank's heartbeat."""

from launderlab.db.ledger import DEFAULT_DB_PATH, connect, table_counts


def main() -> None:
    conn = connect()
    print(f"LaunderLab ledger ready at {DEFAULT_DB_PATH}")
    for table, n in table_counts(conn).items():
        print(f"  {table:<14} {n:>8} rows")
    print("Phase 0: the vault exists. Phase 1 fills it with a living bank.")


if __name__ == "__main__":
    main()
