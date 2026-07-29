"""Build a world the workbench can actually be demonstrated on.

Everything in phases 3-7 is measured against a world that has both honest
traffic and injected crime in it, but until now that world only ever existed
inside a test fixture or a throwaway script. The consequences were real and
recurring: the workbench opened on an empty queue, and the MCP server's
`run_detection` tool returned nothing against the seeded 25-customer ledger and
demoed as a list of empty lists.

So this is the missing step between "the code works" and "here, look":

    python -m launderlab demo-world

generates a bank, injects all six typologies, runs the full detection stack and
opens the cases an analyst would find waiting. It writes to its own file and
refuses to overwrite one silently, because losing a world someone was mid-review
on would be its own small disaster.

BOUNDARY: this is a *builder*, not a detector. It uses the injectors (which
write ground truth by design) and the risk layer (which never reads it).
"""

from __future__ import annotations

import random
import time
from datetime import date
from pathlib import Path

from launderlab.db.ledger import connect
from launderlab.typology import (
    dormant_reactivation,
    high_risk_geography,
    mule_network,
    round_tripping,
    shell_company,
    structuring,
)
from launderlab.workbench import cases, risk
from launderlab.world.generate import load

DEFAULT_DEMO_PATH = Path("data/demo.duckdb")

# Deliberately not "one of everything": the mix decides what the queue looks
# like. Structuring and mule networks dominate because they are what Phases 3
# and 5 detect well, so the demo shows a queue with work in both tiers rather
# than one tier full and two empty.
SCHEME_MIX = {
    "structuring": 8,
    "mule_network": 8,
    "shell_company": 5,
    "round_tripping": 5,
    "dormant_reactivation": 5,
    "high_risk_geography": 5,
}


def build(path: Path = DEFAULT_DEMO_PATH, customers: int = 1200, days: int = 30,
          seed: int = 7, min_score: float = 20.0, overwrite: bool = False,
          mix: dict[str, int] | None = None) -> dict:
    """Generate, inject, detect and open cases. Returns a summary of what it made.

    `mix` overrides how many schemes of each typology to inject. It exists for
    the test suite: a structuring scheme costs ~4s to inject (30-50 rows, each
    followed by a balance recompute), so the demo's 36 schemes are a two-minute
    proposition and a test only needs to prove the pipeline composes.
    """
    mix = SCHEME_MIX if mix is None else mix
    unknown = set(mix) - set(SCHEME_MIX)
    if unknown:
        # a mistyped key would otherwise inject nothing and report success
        raise ValueError(f"unknown typology in mix: {sorted(unknown)}; "
                         f"expected some of {sorted(SCHEME_MIX)}")
    count = mix.get  # an explicit mix is complete: anything absent means none
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"{path} already exists. Pass overwrite=True (CLI: --overwrite) to replace it.")
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    conn = connect(path)
    load(conn, n=customers, days=days, seed=seed)

    def accounts(where: str) -> list[str]:
        return [row[0] for row in conn.execute(
            "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
            f" WHERE {where} ORDER BY account_id").fetchall()]

    business = accounts("c.segment = 'business'")
    retail = accounts("c.segment IN ('salaried','student')")
    nri = accounts("c.segment = 'nri'") or business
    rng = random.Random(seed + 4)
    window = date(2026, 7, 3)

    for i in range(count("structuring", 0)):
        structuring.inject(conn, f"S{i}", rng.choice(business), window, rng,
                           target_total=2_600_000)
    for i in range(count("mule_network", 0)):
        mule_network.inject(conn, f"M{i}", rng.sample(retail, 4), window, rng)
    for i in range(count("shell_company", 0)):
        shell_company.inject(conn, f"H{i}", rng.choice(business), window, rng)
    for i in range(count("round_tripping", 0)):
        round_tripping.inject(conn, f"R{i}", rng.choice(business), window, rng)
    for i in range(count("dormant_reactivation", 0)):
        dormant_reactivation.inject(conn, f"D{i}", rng.choice(retail), rng)
    for i in range(count("high_risk_geography", 0)):
        high_risk_geography.inject(conn, f"G{i}", rng.choice(nri), window, rng)

    scored = risk.score_accounts(conn)
    opened = cases.open_from_queue(conn, scored, actor="system", min_score=min_score)

    tiers = {"graph": 0, "rules": 0, "ml": 0}
    for case in cases.queue(conn, status="open", limit=len(opened) or 1):
        sources = {signal.source for signal in case.signals}
        tiers["graph" if "graph" in sources else
              "rules" if "rules" in sources else "ml"] += 1

    summary = {
        "path": path,
        "transactions": conn.execute("SELECT count(*) FROM transactions").fetchone()[0],
        "accounts": conn.execute("SELECT count(*) FROM accounts").fetchone()[0],
        "schemes": conn.execute(
            "SELECT count(DISTINCT scheme_id) FROM scheme_labels").fetchone()[0],
        "cases": len(opened),
        "tiers": tiers,
        "seconds": round(time.time() - started, 1),
    }
    conn.close()
    return summary


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    path = Path(argv[0]) if argv and not argv[0].startswith("-") else DEFAULT_DEMO_PATH
    try:
        summary = build(path, overwrite="--overwrite" in argv)
    except FileExistsError as exc:
        print(exc)
        return

    print(f"Demo world built in {summary['seconds']}s")
    print(f"  {summary['accounts']:,} accounts, {summary['transactions']:,} transactions")
    print(f"  {summary['schemes']} injected schemes across 6 typologies")
    print(f"  {summary['cases']} cases opened - "
          f"{summary['tiers']['graph']} network, {summary['tiers']['rules']} rule, "
          f"{summary['tiers']['ml']} model")
    print()
    print("Open the workbench on it:")
    print(f"  LAUNDERLAB_DB={summary['path']} "
          f".venv/Scripts/python -m uvicorn launderlab.workbench.api:app --port 8787")
