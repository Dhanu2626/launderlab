"""One-command demo: initialise the ledger and show the bank's heartbeat.

Usage:
    python -m launderlab                 show table counts
    python -m launderlab seed            seed the 25-customer cast + one week of life
    python -m launderlab statement A001  render account A001 as an HTML statement
    python -m launderlab demo-world      build a world with crime in it, ready for
                                         the workbench (see launderlab/demo.py)
    python -m launderlab charts          redraw the measured-results charts as SVG
"""

import sys
import webbrowser

from launderlab.db.ledger import DEFAULT_DB_PATH, connect, table_counts
from launderlab.demo import main as build_demo_world
from launderlab.statement import write
from launderlab.viz import main as draw_charts
from launderlab.world import seed


def main() -> None:
    args = sys.argv[1:]

    # Before connect(): the demo builder opens its OWN file, and DuckDB locks
    # per file — holding the default ledger open here would be for nothing.
    if args and args[0] == "demo-world":
        build_demo_world(args[1:])
        return

    if args and args[0] == "charts":
        draw_charts(args[1:])
        return

    conn = connect()

    if args and args[0] == "statement":
        if len(args) < 2:
            print("usage: python -m launderlab statement <account_id>")
            return
        path = write(conn, args[1])
        print(f"Statement written to {path}")
        webbrowser.open(path.resolve().as_uri())
        return

    if args and args[0] == "seed":
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
