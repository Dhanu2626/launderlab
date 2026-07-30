import inspect
import re

import pytest

from launderlab import redteam as rt


def test_redteam_never_reads_ground_truth():
    """Same boundary as every detection layer, pointed the other direction: the
    adversary must never read `scheme_labels`, `entity_labels` or `media_labels`.
    It already knows the accounts it planted this generation -- that is data it
    holds locally, not a lookup against the answer key."""
    source = inspect.getsource(rt)
    for table in ("scheme_labels", "entity_labels", "media_labels"):
        assert not re.search(rf"\b(FROM|JOIN)\s+{table}\b", source, re.IGNORECASE)


def test_redteam_bounds_are_not_copied_from_the_rule_they_evade():
    """The adversary is allowed to know PUBLIC regulatory facts (the cash
    reporting line near Rs 1,00,000 any real launderer designs around) but never
    the bank's own tuned thresholds -- those are internal tuning a real
    adversary does not have. Checked precisely, one knob against the SPECIFIC
    threshold of the rule it is meant to evade (unit-for-unit; a global bag of
    "suspicious numbers" would false-positive on coincidence, as an earlier
    version of this test did comparing 0.5 days against an unrelated 0.5 ratio)."""
    # (typology, knob name) -> the corresponding rule's own tuned threshold
    corresponding_rule_threshold = {
        ("structuring", "deposit_ceiling"): 100_000,       # structuring_burst's ceiling
        ("mule_network", "hop_hours"): 48.0,               # rapid_pass_through's hop_hours
        ("shell_company", "n_invoices"): 4,                # counterparty_concentration's min_count
        ("round_tripping", "hop_days"): 12.0,               # round_trip's hop_days
        ("dormant_reactivation", "gap_days"): 7.0,          # dormancy_burst's min_gap_days
    }
    for typology, knobs in rt.TYPOLOGY_KNOBS.items():
        for knob in knobs:
            key = (typology, knob.name)
            if key in corresponding_rule_threshold:
                assert knob.bound != corresponding_rule_threshold[key], (
                    f"{typology}.{knob.name}'s bound equals the exact rule threshold "
                    f"it evades -- that is copying the answer key, not real-world "
                    f"plausibility")


def test_high_risk_geography_is_deliberately_excluded():
    """Its only real evasion move -- routing through a jurisdiction not on the
    watchlist -- is categorical, not a number the injector exposes. Inventing a
    fake continuous knob for it would be dishonest, so none exists."""
    assert "high_risk_geography" not in rt.TYPOLOGY_KNOBS


def test_partition_gives_disjoint_chunks_of_the_right_sizes():
    import random
    pool = [f"A{i:03d}" for i in range(40)]
    rng = random.Random(1)
    a, b, c = rt._partition(pool, rng, 10, 15, 5)
    assert len(a) == 10 and len(b) == 15 and len(c) == 5
    assert not (set(a) & set(b) & set(c))
    assert not (set(a) & set(b))
    assert not (set(b) & set(c))
    assert not (set(a) & set(c))


def test_partition_refuses_a_pool_too_small_to_stay_disjoint():
    """Silently sampling WITH replacement when the pool runs out would recreate
    the exact contamination bug this function exists to prevent -- two
    typologies landing on the same account and diluting each other's signal."""
    import random
    with pytest.raises(ValueError, match="too small"):
        rt._partition(["A1", "A2"], random.Random(1), 5, 5)


def test_mutation_steps_toward_the_bound_and_clips_there():
    genome = rt.Genome("shell_company", {"n_invoices": 5})
    for generation in range(20):
        genome = rt._mutate(genome, generation)
    assert genome.values["n_invoices"] == rt.TYPOLOGY_KNOBS["shell_company"][0].bound

    genome = rt.Genome("structuring", {"deposit_ceiling": 95_000})
    for generation in range(3):
        genome = rt._mutate(genome, generation)
    knob = rt.TYPOLOGY_KNOBS["structuring"][0]
    assert genome.values["deposit_ceiling"] == pytest.approx(95_000 + 3 * knob.step)
    assert genome.values["deposit_ceiling"] <= knob.bound


def test_a_converged_genome_stops_mutating():
    genome = rt.Genome("shell_company", {"n_invoices": 2}, converged_at=1)
    mutated = rt._mutate(genome, 2)
    assert mutated.values == genome.values


def test_genome_kwargs_reconstructs_the_types_the_injector_expects():
    genome = rt.Genome("mule_network", {"cut_pct": 0.10, "hop_hours": 20.0})
    kw = genome.kwargs()
    assert isinstance(kw["cut_pct"], tuple) and len(kw["cut_pct"]) == 2
    assert kw["cut_pct"][0] < 0.10 < kw["cut_pct"][1]
    assert isinstance(kw["hop_hours"], tuple)

    genome = rt.Genome("round_tripping", {"hop_days": 6.0})
    kw = genome.kwargs()
    lo, hi = kw["hop_days"]
    assert isinstance(lo, int) and isinstance(hi, int)
    assert lo < hi

    genome = rt.Genome("shell_company", {"n_invoices": 2.7})
    assert genome.kwargs()["n_invoices"] == 3  # rounds, and is an int

    genome = rt.Genome("structuring", {"deposit_ceiling": 97_500.0})
    assert genome.kwargs()["deposit_ceiling"] == 97_500 and \
        isinstance(genome.kwargs()["deposit_ceiling"], int)


@pytest.fixture(scope="module")
def small_run():
    """A real, small-scale run -- proves the whole loop end to end rather than
    just its pieces. Two generations, small pools, kept fast for the suite."""
    return rt.run_decay_benchmark(customers=120, days=14, seed=7,
                                  schemes_per_typology=3, generations=2)


def test_the_loop_runs_and_produces_a_result_per_typology_per_generation(small_run):
    results, genomes = small_run
    typologies = set(rt.TYPOLOGY_KNOBS)
    generations = {r.generation for r in results}
    assert generations == {0, 1}
    assert {r.typology for r in results} == typologies
    for r in results:
        assert 0.0 <= r.recall <= 1.0
        assert r.schemes == 3
    assert set(genomes) == typologies


def test_report_reads_as_a_table_with_a_convergence_section(small_run):
    results, genomes = small_run
    text = rt.report(results, genomes)
    assert "RED TEAM DECAY BENCHMARK" in text
    assert "CONVERGENCE" in text
    assert "high_risk_geography" in text  # states the exclusion, doesn't hide it
    for typology in rt.TYPOLOGY_KNOBS:
        assert typology in text


def test_run_decay_benchmark_docstring_was_not_silently_dropped():
    """A second string literal placed directly after the real docstring is not a
    second docstring -- Python keeps only the first and silently evaluates the
    second as a no-op expression statement. That happened here once already and
    dropped the function's actual explanation from __doc__ without an error."""
    assert rt.run_decay_benchmark.__doc__ is not None
    assert "co-evolution loop" in rt.run_decay_benchmark.__doc__
    assert "customers" in rt.run_decay_benchmark.__doc__


def test_report_measures_post_convergence_stability_rather_than_assuming_it():
    """"Converged" means the first generation a frozen playbook fully evaded, not
    a permanent guarantee -- the genome freezes but the world it runs against is
    regenerated every generation, so a scheme can still trip a rule by chance.
    Built from fixed results rather than a live run, so the arithmetic is exact:
    two post-convergence generations at 20% and 0% recall must average to 10%."""
    genome = rt.Genome("shell_company", {"n_invoices": 3}, converged_at=1)
    results = [
        rt.GenerationResult(0, "shell_company", 10, 3),
        rt.GenerationResult(1, "shell_company", 10, 0),
        rt.GenerationResult(2, "shell_company", 10, 2),   # 20% after "convergence"
        rt.GenerationResult(3, "shell_company", 10, 0),
    ]
    text = rt.report(results, {"shell_company": genome})
    assert "POST-CONVERGENCE STABILITY" in text
    assert "10%" in text  # (0.20 + 0.00) / 2
