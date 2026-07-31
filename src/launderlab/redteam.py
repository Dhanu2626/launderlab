"""Phase 8 — a red team that adapts to what got caught.

THE RESEARCH QUESTION (PROJECT.md thesis #1): how fast does a static detection
stack rot against an adversary that learns from its own failures? Nobody has
published this number, because it needs ground truth on both sides at once — a
real bank sees its own catch rate but never the schemes it missed, and no public
dataset contains a criminal who adapts generation over generation. This project
has both, so this module is the one place that can finally produce the number.

HOW THE ADVERSARY LEARNS, and why this is fair rather than a leak of the answer
key. Each typology gets a small number of continuous parameters — the same
keyword arguments the Phase 2 injectors already expose (`deposit_ceiling`,
`cut_pct`, `n_invoices`...). Generation 0 uses each injector's own default: an
unsophisticated launderer running the naive version of the scheme. Each
following generation, the adversary re-injects using the SAME detection surface
blue-team code already exposes — `detect.rules.run_all()` and, for mule
networks, `graph.motifs.find_chains()` — and checks whether the account(s) IT
JUST PLANTED were flagged. If yes, it takes one step of its own parameters
toward whichever direction plausibly reduces detectability (fewer/larger
deposits instead of many small ones; skim more per hop; fewer invoices...) — the
same inference a real launderer draws from an account being frozen, without
ever seeing a rule's source or its tuned constants. If no, the configuration is
kept: the adversary has converged, and the generation and cost of that
convergence are the headline numbers.

"CONVERGED" MEANS FIRST FULL EVASION, NOT A PERMANENT GUARANTEE. The genome
freezes there, but every later generation still runs it against a freshly
regenerated world — so a scheme can still trip a rule by chance if a random gap
or timestamp happens to land the wrong side of a threshold. `report()` prints
this as a measured "post-convergence mean recall" rather than letting the word
"converged" imply zero-forever; in the real run, dormant_reactivation converged
at generation 2 and still showed 20% recall two generations later.

WHAT THE ADVERSARY IS NOT ALLOWED TO KNOW, and this is the whole boundary rule
pointed the other direction. It never reads `scheme_labels`, `entity_labels` or
`media_labels` — the account ids it checks are the ones it planted in this same
function call, held in local memory, never looked up from a ground-truth table.
It never inspects `detect/rules.py`'s source or its tuned numeric constants
(`min_count=24`, `min_total=1_400_000`...) — those are the BANK's internal
tuning, and a real adversary does not have them. The one thing it IS allowed to
know is public regulatory fact any real launderer already knows — the
cash-reporting threshold near Rs 1,00,000 that `structuring_burst`'s ceiling
happens to sit near, because banks and criminals both design around the same
published rule. `KNOB.bound` values are documented below with which kind of
fact justified them.

WHAT IS DELIBERATELY OUT OF SCOPE. The adversary tunes CONTINUOUS parameters of
an EXISTING typology shape — it does not invent a new shape (spreading
structuring across many mule accounts, i.e. real smurfing, is a different
typology, not a parameter). And `high_risk_geography` is excluded entirely: its
only real evasion move is routing through a jurisdiction NOT on the FATF-style
watchlist, which is a categorical choice the injector does not expose as a
number, and `rules.HIGH_RISK_WATCHLIST` already covers every country the
injector can select from — there is no honest continuous knob to mutate here,
so none is invented. This slice also measures decay of the RULES layer (plus
Phase 5's graph, the one layer that can see mule_network at all) — whether a
TRAINED model decays faster or slower than static SQL thresholds is a real and
different question, left to a later slice rather than guessed at here.

    python -m launderlab redteam
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import duckdb

from launderlab.db.ledger import connect
from launderlab.detect import rules
from launderlab.graph import build as graph_build
from launderlab.graph import motifs
from launderlab.typology import (
    dormant_reactivation,
    mule_network,
    round_tripping,
    shell_company,
    structuring,
)
from launderlab.world.generate import load

WINDOW_START = date(2026, 7, 3)


@dataclass(frozen=True)
class Knob:
    """One continuous parameter the adversary can turn, and the real-world limit
    on it. `bound` is never the detector's own threshold — see the module
    docstring for what the adversary is and isn't allowed to know.
    """
    name: str            # the injector kwarg this controls
    start: float          # generation-0 value: today's naive launderer
    bound: float          # the plausible real-world limit; mutation clips here
    step: float           # how far one generation moves
    why_bound: str        # the real-world fact that justifies the limit


# One shared "standard operating parameters" genome per typology, not one per
# scheme instance -- this is what makes the per-generation number a criminal
# organisation's evolving playbook rather than fifteen independent coin flips,
# and matches the master plan's "red team win-rate vs blue team config version".
TYPOLOGY_KNOBS: dict[str, list[Knob]] = {
    "structuring": [
        Knob("deposit_ceiling", start=95_000, bound=99_999, step=500,
             why_bound="Rs 99,999 is one rupee under the public cash-reporting "
                       "line every launderer designs around -- not this bank's "
                       "tuned rule threshold, which sits at the same public line "
                       "for the same reason."),
    ],
    "mule_network": [
        # retain fraction = 1 - cut_pct. Two independent surfaces watch this
        # typology, and they disagree about how much retention is safe:
        # rapid_pass_through wants retain >= 0.85, the graph's chain detector
        # wants retain in [0.80, 1.00]. A cut_pct pushed past 0.20 clears both,
        # but at a real cost -- the mule keeps less of what it laundered.
        Knob("cut_pct", start=0.055, bound=0.35, step=0.02,
             why_bound="beyond roughly a third skimmed per hop the mule is "
                       "keeping most of the money rather than passing it on -- "
                       "the layering chain stops being economically worth "
                       "running for the principal, independent of detection."),
        Knob("hop_hours", start=16.0, bound=60.0, step=6.0,
             why_bound="a hop stretched past a couple of days stops looking "
                       "like an active layering chain and starts looking like "
                       "money quietly parked -- which invites the dormancy "
                       "rule's attention instead."),
    ],
    "shell_company": [
        Knob("n_invoices", start=5, bound=1, step=-1,
             why_bound="a single invoice is the floor -- an invoice-based "
                       "scheme needs at least one payment to exist at all."),
    ],
    "round_tripping": [
        Knob("hop_days", start=6.0, bound=45.0, step=4.0,
             why_bound="capital parked outside the account for over a month "
                       "and a half carries its own liquidity cost to whoever "
                       "owns it, real-trip or not."),
    ],
    "dormant_reactivation": [
        Knob("gap_days", start=6.5, bound=0.5, step=-1.0,
             why_bound="under half a day the account was barely dormant at "
                       "all -- there has to be SOME quiet stretch for this to "
                       "be reactivation rather than ongoing activity."),
    ],
}

# hop_hours/hop_days/cut_pct/gap_days feed the injector as a (low, high) RANGE,
# not a scalar -- this is how wide a band the adversary samples around its
# current standard, held constant across mutation so only the centre moves.
# (half_width, floor, is_int_tuple)
_RANGE_PARAMS = {
    "cut_pct": (0.025, 0.005, False),
    "hop_hours": (14.0, 0.5, False),
    "hop_days": (4.0, 1.0, True),
    "gap_days": (3.5, 0.1, False),
}


@dataclass
class Genome:
    """One typology's current standard operating parameters."""
    typology: str
    values: dict[str, float]
    converged_at: int | None = None  # generation of first full evasion, or None

    def kwargs(self) -> dict:
        """The injector kwargs this genome produces, ranges reconstructed
        around the centre value each knob actually mutates."""
        out = {}
        for name, value in self.values.items():
            if name in _RANGE_PARAMS:
                half, floor, as_int = _RANGE_PARAMS[name]
                lo, hi = max(value - half, floor), value + half
                out[name] = (int(lo), max(int(hi), int(lo) + 1)) if as_int else (lo, hi)
            elif name == "n_invoices":
                out[name] = max(int(round(value)), 1)
            elif name == "deposit_ceiling":
                out[name] = int(value)
            else:
                out[name] = value
        return out


def _initial_genomes() -> dict[str, Genome]:
    return {name: Genome(name, {k.name: k.start for k in knobs})
            for name, knobs in TYPOLOGY_KNOBS.items()}


def _mutate(genome: Genome) -> Genome:
    """One step toward evasion for every knob this typology has. Frozen once
    the genome has fully converged -- there is no reason for a rational
    adversary to keep pushing past the point that already works.

    Takes no generation number on purpose: mutation is a fixed step, and an
    unused `generation` parameter (which this had) advertises schedule-dependent
    behaviour that does not exist. Add it back only alongside a step size that
    actually varies with it.
    """
    if genome.converged_at is not None:
        return genome
    knobs = TYPOLOGY_KNOBS[genome.typology]
    new_values = dict(genome.values)
    for knob in knobs:
        current = genome.values[knob.name]
        moved = current + knob.step
        # clip toward the bound, in whichever direction step points
        new_values[knob.name] = (min(moved, knob.bound) if knob.step > 0
                                 else max(moved, knob.bound))
    return replace(genome, values=new_values)


@dataclass(frozen=True)
class GenerationResult:
    generation: int
    typology: str
    schemes: int
    caught: int

    @property
    def recall(self) -> float:
        return self.caught / self.schemes if self.schemes else 0.0


def _accounts(conn: duckdb.DuckDBPyConnection, where: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        f" WHERE {where} ORDER BY account_id").fetchall()]


def _partition(pool: list[str], rng: random.Random, *chunk_sizes: int) -> list[list[str]]:
    """Split `pool` into DISJOINT chunks of the given sizes.

    Sampling each typology's account independently with replacement from a
    shared pool (the first version of this function) let structuring and
    shell_company land on the SAME business account inside one generation --
    the extra scheme's credits diluted `counterparty_concentration`'s "one
    counterparty is most of my money" signal, so shell_company's recall was
    measuring cross-contamination between typologies, not the adversary.
    Disjoint partitions make every typology's recall comparable across
    generations, which is the entire point of the benchmark.
    """
    needed = sum(chunk_sizes)
    if len(pool) < needed:
        raise ValueError(
            f"account pool too small: need {needed} disjoint accounts, have {len(pool)}. "
            f"Increase `customers` or lower `schemes_per_typology`.")
    shuffled = rng.sample(pool, needed)
    chunks, start = [], 0
    for size in chunk_sizes:
        chunks.append(shuffled[start:start + size])
        start += size
    return chunks


def _inject_generation(conn: duckdb.DuckDBPyConnection, genomes: dict[str, Genome],
                       schemes_per_typology: int, rng: random.Random
                       ) -> dict[str, list]:
    """Plant this generation's schemes and return, per typology, the account(s)
    each one used -- held locally, never re-derived from a ground-truth table.

    Every account used this generation is disjoint, both across typologies and
    across scheme instances within one typology -- see `_partition`.
    """
    business = _accounts(conn, "c.segment = 'business'")
    retail = _accounts(conn, "c.segment IN ('salaried','student')")

    structuring_accts, shell_accts, roundtrip_accts = _partition(
        business, rng, schemes_per_typology, schemes_per_typology, schemes_per_typology)
    mule_pool, dormant_accts = _partition(
        retail, rng, schemes_per_typology * 4, schemes_per_typology)
    mule_chains = [mule_pool[i * 4:(i + 1) * 4] for i in range(schemes_per_typology)]

    planted: dict[str, list] = {name: [] for name in TYPOLOGY_KNOBS}
    kw = {name: genome.kwargs() for name, genome in genomes.items()}

    for i in range(schemes_per_typology):
        structuring.inject(conn, f"RT-S{i}", structuring_accts[i], WINDOW_START, rng,
                           target_total=1_200_000, **kw["structuring"])
        planted["structuring"].append([structuring_accts[i]])

        mule_network.inject(conn, f"RT-M{i}", mule_chains[i], WINDOW_START, rng,
                            **kw["mule_network"])
        planted["mule_network"].append(mule_chains[i])

        shell_company.inject(conn, f"RT-H{i}", shell_accts[i], WINDOW_START, rng,
                             **kw["shell_company"])
        planted["shell_company"].append([shell_accts[i]])

        round_tripping.inject(conn, f"RT-R{i}", roundtrip_accts[i], WINDOW_START, rng,
                              **kw["round_tripping"])
        planted["round_tripping"].append([roundtrip_accts[i]])

        dormant_reactivation.inject(conn, f"RT-D{i}", dormant_accts[i], rng,
                                    **kw["dormant_reactivation"])
        planted["dormant_reactivation"].append([dormant_accts[i]])

    return planted


def _caught_by_rule(alerts: list, accounts: list[str]) -> bool:
    flagged = {a.account_id for a in alerts}
    return any(acct in flagged for acct in accounts)


def _caught_by_graph(chains: list, accounts: list[str]) -> bool:
    account_set = set(accounts)
    return any(account_set & set(chain.accounts) for chain in chains)


def run_generation(conn: duckdb.DuckDBPyConnection, genomes: dict[str, Genome],
                   schemes_per_typology: int, rng: random.Random,
                   generation: int) -> list[GenerationResult]:
    """Plant one generation, detect, and report each typology's recall."""
    planted = _inject_generation(conn, genomes, schemes_per_typology, rng)

    rule_alerts = {
        "structuring": rules.structuring_burst(conn),
        "mule_network": rules.rapid_pass_through(conn),
        "shell_company": rules.counterparty_concentration(conn),
        "round_tripping": rules.round_trip(conn),
        "dormant_reactivation": rules.dormancy_burst(conn),
    }
    chains = motifs.find_chains(graph_build.build_graph(conn))

    results = []
    for typology, schemes in planted.items():
        caught = 0
        for accounts in schemes:
            hit = _caught_by_rule(rule_alerts[typology], accounts)
            if typology == "mule_network":
                hit = hit or _caught_by_graph(chains, accounts)
            caught += hit
        results.append(GenerationResult(generation, typology, len(schemes), caught))
    return results


def run_decay_benchmark(customers: int = 450, days: int = 21, seed: int = 41,
                        schemes_per_typology: int = 10, generations: int = 8,
                        db_dir: Path | None = None
                        ) -> tuple[list[GenerationResult], dict[str, Genome]]:
    """The whole co-evolution loop: fresh small world per generation, so no
    generation's ledger contaminates the next. Returns every generation's
    results plus the final genome each typology converged to (or didn't).

    `customers` defaults to 450 because business accounts are only ~10% of the
    population and three typologies now need disjoint slices of them
    (`_partition`) -- comfortably above the 3 x schemes_per_typology needed.
    """
    import shutil
    import tempfile

    db_dir = Path(db_dir) if db_dir else Path(tempfile.mkdtemp(prefix="redteam_"))
    db_dir.mkdir(parents=True, exist_ok=True)
    genomes = _initial_genomes()
    all_results: list[GenerationResult] = []

    try:
        for generation in range(generations):
            path = db_dir / f"gen{generation}.duckdb"
            conn = connect(path)
            load(conn, n=customers, days=days, seed=seed + generation)
            rng = random.Random(seed + generation)

            results = run_generation(conn, genomes, schemes_per_typology, rng, generation)
            all_results.extend(results)
            conn.close()

            for result in results:
                genome = genomes[result.typology]
                if result.recall == 0.0 and genome.converged_at is None:
                    genome.converged_at = generation
                if genome.converged_at is None:
                    genomes[result.typology] = _mutate(genome)
    finally:
        shutil.rmtree(db_dir, ignore_errors=True)

    return all_results, genomes


def report(results: list[GenerationResult], genomes: dict[str, Genome]) -> str:
    lines = [
        "RED TEAM DECAY BENCHMARK - a static rules engine vs a learning adversary",
        "=" * 78, "",
        f"{'typology':<22}" + "".join(f"gen{g:<5}" for g in
            sorted({r.generation for r in results})),
        "-" * 78,
    ]
    by_typology: dict[str, list[GenerationResult]] = {}
    for r in results:
        by_typology.setdefault(r.typology, []).append(r)

    for typology, rows in by_typology.items():
        rows.sort(key=lambda r: r.generation)
        cells = "".join(f"{r.recall:>7.0%} " for r in rows)
        lines.append(f"{typology:<22}{cells}")

    lines += ["", "CONVERGENCE - the generation each typology first fully evaded", "-" * 78]
    for typology, genome in genomes.items():
        knobs = TYPOLOGY_KNOBS[typology]
        start = ", ".join(f"{k.name}={k.start:g}" for k in knobs)
        final = ", ".join(f"{k.name}={genome.values[k.name]:g}" for k in knobs)
        if genome.converged_at is not None:
            lines.append(f"  {typology:<22} converged at generation {genome.converged_at} "
                         f"| gen0 [{start}] -> converged [{final}]")
        else:
            lines.append(f"  {typology:<22} never fully evaded within the run "
                         f"| gen0 [{start}] -> final [{final}]")

    # "Converged" means the FIRST generation a frozen playbook fully evaded, not
    # a permanent guarantee. The genome stops mutating there, but every later
    # generation still runs it against a freshly generated world, so a scheme can
    # still occasionally trip a rule by chance -- dormant_reactivation converged
    # at generation 2 in the real run and still showed 20% recall at generation
    # 4, purely from where a random gap landed relative to the rule's threshold.
    # Reported as a number rather than left as an asterisk in the prose, because
    # that is the standard this whole project holds every other claim to.
    stability_lines = []
    for typology, rows in by_typology.items():
        genome = genomes[typology]
        if genome.converged_at is None:
            continue
        after = [r for r in rows if r.generation > genome.converged_at]
        if not after:
            continue
        mean_recall = sum(r.recall for r in after) / len(after)
        stability_lines.append(
            f"  {typology:<22} mean recall {mean_recall:>5.0%} over the "
            f"{len(after)} generation(s) after convergence")
    if stability_lines:
        lines += ["", "POST-CONVERGENCE STABILITY - does frozen still mean caught 0% of the time?",
                 "-" * 78, *stability_lines]

    lines += ["", "high_risk_geography: excluded -- see module docstring "
             "(no continuous evasion knob exists; the watchlist already "
             "covers every jurisdiction the injector can select)."]
    return "\n".join(lines)


def main(argv: list[str]) -> None:  # pragma: no cover - CLI wiring
    from launderlab.viz import render_redteam

    generations = 8
    for arg in argv:
        if arg.startswith("--generations="):
            generations = int(arg.split("=", 1)[1])
    results, genomes = run_decay_benchmark(generations=generations)
    print(report(results, genomes))
    if "--no-chart" not in argv:
        # The results are already in memory -- draw straight from them rather
        # than asking `charts` to re-run several minutes of benchmark later.
        path = render_redteam(results, genomes)
        print(f"\nChart written to {path}")
