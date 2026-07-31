"""One-command demo: initialise the ledger and show the bank's heartbeat.

Usage:
    python -m launderlab                 show table counts
    python -m launderlab seed            seed the 25-customer cast + one week of life
    python -m launderlab statement A001  render account A001 as an HTML statement
    python -m launderlab demo-world      build a world with crime in it, ready for
                                         the workbench (see launderlab/demo.py)
    python -m launderlab charts          redraw the measured-results charts as SVG
    python -m launderlab media-experiment  measure whether adverse media earns a
                                         place in the risk score (workbench/media_experiment.py)
    python -m launderlab redteam           run the Phase 8 decay benchmark: an
                                         adversary that mutates its own typology
                                         parameters generation over generation
                                         (see redteam.py). ~8 min at defaults
    python -m launderlab multibank         run the Phase 8.5 cross-bank blind-spot
                                         experiment: split the world into 4 banks
                                         with separate ledgers, measure what each
                                         sees alone, then what privacy-preserving
                                         co-operation buys back (see multibank.py)
    python -m launderlab story             Phase 9 Story Mode: replay each injected
                                         scheme day by day and measure how long it
                                         ran before any detector could see it
                                         (see story.py). Reads LAUNDERLAB_DB
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

    if args and args[0] == "media-experiment":
        from launderlab.workbench.media_experiment import main as run_media_experiment
        run_media_experiment(args[1:])
        return

    if args and args[0] == "redteam":
        from launderlab.redteam import main as run_redteam
        run_redteam(args[1:])
        return

    if args and args[0] == "multibank":
        from launderlab.multibank import main as run_multibank
        run_multibank(args[1:])
        return

    # Before connect(), like demo-world: story opens the world named by
    # LAUNDERLAB_DB itself, and DuckDB locks per file.
    if args and args[0] == "story":
        from launderlab.story import main as run_story
        run_story(args[1:])
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
