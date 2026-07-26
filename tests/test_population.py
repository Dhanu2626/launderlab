from launderlab.world.population import SEGMENT_WEIGHTS, generate


def test_count_and_unique_ids():
    people = generate(2000)
    assert len(people) == 2000
    assert len({p.customer_id for p in people}) == 2000


def test_deterministic():
    a = generate(500, seed=7)
    b = generate(500, seed=7)
    assert [p.customer_id for p in a] == [p.customer_id for p in b]
    assert [p.full_name for p in a] == [p.full_name for p in b]


def test_segment_distribution_within_tolerance():
    people = generate(8000, seed=1)
    counts = {seg: 0 for seg in SEGMENT_WEIGHTS}
    for p in people:
        counts[p.segment] += 1
    for seg, weight in SEGMENT_WEIGHTS.items():
        share = counts[seg] / len(people)
        assert abs(share - weight) < 0.03, f"{seg}: {share:.3f} vs target {weight}"


def test_segment_specific_fields():
    people = generate(3000, seed=3)
    by_segment = {}
    for p in people:
        by_segment.setdefault(p.segment, p)

    assert by_segment["salaried"].salary > 0
    assert by_segment["salaried"].employer
    assert by_segment["salaried"].pocket_money == 0

    assert by_segment["student"].pocket_money > 0
    assert by_segment["student"].salary == 0

    assert by_segment["nri"].remittance > 0
    assert by_segment["nri"].remit_from

    for seg in ("business", "merchant"):
        assert by_segment[seg].monthly_revenue > 0
        assert by_segment[seg].account_type == "current"


def test_account_type_matches_segment():
    people = generate(1000, seed=9)
    for p in people:
        expected = "current" if p.segment in ("business", "merchant") else "savings"
        assert p.account_type == expected


def test_opening_balance_always_positive():
    people = generate(1000, seed=11)
    assert all(p.opening_balance > 0 for p in people)
