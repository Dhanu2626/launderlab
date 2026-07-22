"""One-command demo: initialise the ledger and show the bank's heartbeat.

Usage:
    python -m launderlab          show table counts
    python -m launderlab seed     seed the 25-customer cast + one week of life, then show counts
"""

import sys

from launderlab.db.ledger import DEFAULT_DB_PATH, connect, table_counts
from launderlab.world import seed


def main() -> None:
    conn = connect()
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        already = conn.execute("SELECT count(*) FROM customers").fetchone()[0]
        if already:
            print(f"Ledger already has {already} customers — not seeding twice.")
        else:
            n = seed.load(conn)
            print(f"Seeded one week of life: {n} transactions posted.")
    print(f"LaunderLab ledger ready at {DEFAULT_DB_PATH}")
    for table, n in table_counts(conn).items():
        print(f"  {table:<14} {n:>8} rows")


if __name__ == "__main__":
    main()
