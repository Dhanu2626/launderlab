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

import numpy as np

from launderlab.db.ledger import connect
from launderlab.ml import features, models
from launderlab.screening import inject as screening_inject
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


def unsupervised_ml_scores(conn, budget: int = 100) -> dict[str, float]:
    """Rank accounts by how unusual they look, and return only the top `budget`.

    WHY A BUDGET AND NOT EVERY ACCOUNT. Returning a score for all 1,200 accounts
    was the first version and it was wrong twice over. A model that scores
    everything is not evidence about anyone — and because the aggregation adds
    weight x score, a mid-ranked account picked up ~7 free points and borderline
    accounts crossed the opening threshold on nothing but "the model mildly
    dislikes you". It also swallowed the queue: every case that was not a chain or
    a rule carried an ml signal, so sanctions hits were filed under "model-ranked".
    An alert budget is how Phase 6 scored these models and how a bank runs one.

    WHY UNSUPERVISED, and it is not a shortcut. The strongest model in the Phase 6
    tournament is supervised, but it has to be trained on labels — and in a demo
    there is only ONE world, so a supervised model would be scoring the same
    accounts it was fitted on. Every training account would get a flattered
    score and the queue would look sharper than the method really is. An
    unsupervised model never sees a label at all, so fitting and scoring on the
    same population leaks nothing: there is no answer key in the loop.

    The honest cost is that these scores are weak — Phase 6 measured isolation
    forest at 0.155 average precision once the world gained a realistic upper
    tail of legitimate large payments. That is the true state of the art here,
    and Tier 3 in the queue says so.
    """
    account_ids, _names, matrix = features.extract(conn)
    if len(account_ids) < 2:
        return {}

    model = models.Isolation()
    assert not model.needs_labels, "the demo must never fit a labelled model to itself"
    raw = model.fit(np.asarray(matrix, dtype=float)).score(np.asarray(matrix, dtype=float))

    # risk.collect expects 0-1. Min-max rather than a z-score: the aggregation
    # treats the value as "how strong is this evidence", and an unsupervised
    # score has no calibrated meaning beyond its rank within the population.
    low, high = float(min(raw)), float(max(raw))
    if high <= low:
        return {}
    ranked = sorted(zip(account_ids, (float(v) for v in raw)),
                    key=lambda pair: pair[1], reverse=True)[:budget]
    return {account: (value - low) / (high - low) for account, value in ranked}


def build(path: Path = DEFAULT_DEMO_PATH, customers: int = 1200, days: int = 30,
          seed: int = 7, min_score: float | None = None, overwrite: bool = False,
          mix: dict[str, int] | None = None, entity_count: int = 15) -> dict:
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

    # Phase 4's leg needs its own planting: screening looks for sanctioned
    # IDENTITIES, so without listed entities and adverse media in the world the
    # screening weight contributes nothing and the demo shows a four-layer
    # workbench exercising two.
    entities = screening_inject.inject_entities(conn, rng, n=entity_count)
    screening_inject.inject_adverse_media(conn, rng)

    ml_scores = unsupervised_ml_scores(conn)
    scored = risk.score_accounts(conn, ml_scores=ml_scores)
    threshold = risk.MIN_CASE_SCORE if min_score is None else min_score
    opened = cases.open_from_queue(conn, scored, actor="system", min_score=threshold)
    # How many cleared the bar versus how many an analyst can actually be given.
    # Reported because the gap is where sanctions alerts go to die: they score
    # 17.6-19.7 alone, so under ONE shared budget every behavioural case outranks
    # them and they are never worked. Real banks queue screening separately for
    # exactly this reason -- a sanctions match is a blocking obligation with its
    # own clock, not a "review when you reach it".
    eligible = sum(1 for entry in scored if entry.score >= threshold)

    # Same tiering the queue uses, from the one place that owns the measurement.
    tiers = dict.fromkeys(risk.TIER_ORDER, 0)
    layers = dict.fromkeys(risk.TIER_ORDER, 0)
    for case in cases.queue(conn, status="open", limit=len(opened) or 1):
        sources = {signal.source for signal in case.signals}
        tier = next((t for t in risk.TIER_ORDER if t in sources), risk.TIER_ORDER[-1])
        tiers[tier] += 1
        for source in sources:
            if source in layers:
                layers[source] += 1

    summary = {
        "path": path,
        "transactions": conn.execute("SELECT count(*) FROM transactions").fetchone()[0],
        "accounts": conn.execute("SELECT count(*) FROM accounts").fetchone()[0],
        "schemes": conn.execute(
            "SELECT count(DISTINCT scheme_id) FROM scheme_labels").fetchone()[0],
        "entities": entities,
        "eligible": eligible,
        "cases": len(opened),
        "tiers": tiers,
        "layers": layers,
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
    print(f"  {summary['entities']} watchlist entities planted + adverse media")
    tiers, layers = summary["tiers"], summary["layers"]
    print(f"  {summary['cases']} of {summary['eligible']} eligible accounts opened "
          f"as cases (alert budget), by tier: "
          + ", ".join(f"{name} {tiers[name]}" for name in tiers))
    print("  layers contributing to any case: "
          + ", ".join(f"{name} {layers[name]}" for name in layers))
    if not summary["tiers"]["ml"]:
        # Not a build failure: an ml-only case tops out at 15.0 (weight 0.15) and
        # the opening threshold sits above that deliberately, because a model-only
        # alert has no reason to give an analyst.
        print("  note: the model tier is empty by arithmetic, not for lack of signal;")
        print(f"        model scores lifted {layers['ml']} cases another layer had "
              f"already flagged")
    if summary["cases"] < summary["eligible"]:
        print(f"  note: {summary['eligible'] - summary['cases']} eligible accounts did not "
              f"fit the budget - sanctions-only")
        print("        hits score lowest and are cut first, which is why real banks queue "
              "screening separately")
    print()
    print("Open the workbench on it:")
    print(f"  LAUNDERLAB_DB={summary['path']} "
          f".venv/Scripts/python -m uvicorn launderlab.workbench.api:app --port 8787")
