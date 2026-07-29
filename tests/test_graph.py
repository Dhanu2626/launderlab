import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.graph import build, motifs, scoring
from launderlab.typology import mule_network, structuring
from launderlab.world.generate import load


def _individuals(conn, limit=40):
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('salaried','student') ORDER BY account_id LIMIT ?", [limit]
    ).fetchall()]


@pytest.fixture(scope="module")
def clean_world(tmp_path_factory):
    conn = connect(tmp_path_factory.mktemp("gclean") / "w.duckdb")
    load(conn, n=500, days=20, seed=31)
    return conn


@pytest.fixture(scope="module")
def mule_world(tmp_path_factory):
    conn = connect(tmp_path_factory.mktemp("gmule") / "w.duckdb")
    load(conn, n=500, days=20, seed=31)
    rng = random.Random(7)
    accounts = _individuals(conn)
    planted = []
    for i in range(5):
        chain = rng.sample(accounts, rng.randrange(3, 6))
        mule_network.inject(conn, f"M{i}", chain, date(2026, 7, 3), rng)
        planted.append(set(chain))
    return conn, planted


def test_graph_and_motifs_never_read_ground_truth():
    import inspect
    import re

    from launderlab.graph import build as build_module
    from launderlab.graph import motifs as motifs_module

    for module in (build_module, motifs_module):
        source = inspect.getsource(module)
        assert not re.search(r"\b(FROM|JOIN)\s+scheme_labels\b", source, re.IGNORECASE)


def test_transfers_pair_both_legs_of_one_payment(clean_world):
    transfers = build.load_transfers(clean_world)
    assert transfers
    for transfer in transfers[:200]:
        assert transfer.src != transfer.dst
        assert transfer.amount > 0


def test_clean_world_produces_no_chains(clean_world):
    graph = build.build_graph(clean_world)
    assert graph.number_of_edges() > 0  # the graph is real, just crime-free
    assert motifs.find_chains(graph) == []


def test_every_planted_chain_is_found(mule_world):
    conn, planted = mule_world
    chains = motifs.find_chains(build.build_graph(conn))
    report = scoring.score_chains(conn, chains)
    assert report.recall == 1.0
    assert report.layering_schemes_detected == report.layering_schemes_total == len(planted)


def test_no_false_positive_chains(mule_world):
    conn, _planted = mule_world
    chains = motifs.find_chains(build.build_graph(conn))
    report = scoring.score_chains(conn, chains)
    assert report.false_positive_chains == 0
    assert report.precision == 1.0


def test_chains_are_reported_once_not_as_overlapping_fragments(mule_world):
    conn, planted = mule_world
    chains = motifs.find_chains(build.build_graph(conn))
    # growing from every edge finds a long chain again from its 2nd, 3rd... account;
    # only maximal chains should survive
    assert len(chains) == len(planted)
    for shorter in chains:
        for longer in chains:
            if shorter is not longer:
                assert not motifs._is_contiguous_within(shorter.accounts, longer.accounts)


def test_chain_amounts_decay_and_time_moves_forward(mule_world):
    conn, _planted = mule_world
    for chain in motifs.find_chains(build.build_graph(conn)):
        assert chain.started < chain.ended
        assert chain.hops >= motifs.DEFAULT_MIN_HOPS
        assert 0.0 < chain.retained <= 1.0
        for earlier, later in zip(chain.amounts, chain.amounts[1:]):
            assert later <= earlier  # a mule keeps a cut, never adds money


def test_every_hop_traces_back_to_the_two_ledger_rows_that_made_it(mule_world):
    """A chain an analyst cannot open in the statement is an assertion, not
    evidence — and 7.8's SAR narrative has to cite the rows it describes. Each
    hop carries the (DR, CR) pair it was reconstructed from, and those rows must
    really exist, on the two accounts the hop claims, for the hop's amount."""
    conn, _planted = mule_world
    for chain in motifs.find_chains(build.build_graph(conn)):
        assert len(chain.hop_txns) == chain.hops
        for i, (dr, cr) in enumerate(chain.hop_txns):
            rows = conn.execute(
                "SELECT txn_id, account_id, direction, amount::DOUBLE FROM transactions"
                " WHERE txn_id IN (?, ?) ORDER BY direction", [dr, cr]).fetchall()
            assert len(rows) == 2, f"hop {i} points at rows that do not exist"
            (_, cr_acct, cr_dir, cr_amt), (_, dr_acct, dr_dir, dr_amt) = rows
            assert (cr_dir, dr_dir) == ("CR", "DR")
            assert dr_acct == chain.accounts[i], "DR leg is not on the paying account"
            assert cr_acct == chain.accounts[i + 1], "CR leg is not on the receiving account"
            assert dr_amt == cr_amt == chain.amounts[i]


def test_structuring_is_invisible_to_the_graph(tmp_path):
    """Cash deposits have no counterparty account, so they form no edge at all.

    Not a detection failure — a scheme whose other side banks elsewhere is exactly
    the cross-bank blind spot this project's thesis is about.
    """
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=300, days=20, seed=12)
    business = conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' LIMIT 1").fetchone()[0]
    structuring.inject(conn, "S1", business, date(2026, 7, 3), random.Random(1))

    report = scoring.score_chains(conn, motifs.find_chains(build.build_graph(conn)))
    detected, total = report.schemes_with_internal_edges["structuring"]
    assert total == 1
    assert detected == 0


def test_scoring_is_deterministic(mule_world):
    conn, _planted = mule_world
    graph = build.build_graph(conn)
    first = scoring.score_chains(conn, motifs.find_chains(graph))
    second = scoring.score_chains(conn, motifs.find_chains(graph))
    assert first == second
