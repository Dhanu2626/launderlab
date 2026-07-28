"""Score graph motif detection against ground truth.

The only module in the graph package allowed to read `scheme_labels`, matching
detect/scoring.py and screening/scoring.py.

A reported chain counts as a true positive when it shares at least two accounts
with one injected layering scheme. Two, not one: a chain necessarily spans
several accounts, and a single shared account could be coincidence — the claim
being tested is "this detector found the *path*", not "it happened to touch
someone involved".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import duckdb

from launderlab.graph.motifs import Chain

MIN_SHARED_ACCOUNTS = 2


@dataclass(frozen=True)
class GraphReport:
    chains_reported: int
    true_positive_chains: int
    false_positive_chains: int
    precision: float
    layering_schemes_total: int
    layering_schemes_detected: int
    recall: float
    # How much of the injected crime the graph could see at all, by typology --
    # the blind-spot measurement, not a detection failure.
    schemes_with_internal_edges: dict = field(default_factory=dict)


def _scheme_accounts(conn: duckdb.DuckDBPyConnection) -> dict[str, tuple[str, set[str]]]:
    """scheme_id -> (typology, set of accounts it touched)."""
    rows = conn.execute(
        "SELECT DISTINCT l.scheme_id, l.typology, t.account_id"
        " FROM scheme_labels l JOIN transactions t USING (txn_id)"
    ).fetchall()
    schemes: dict[str, tuple[str, set[str]]] = {}
    for scheme_id, typology, account_id in rows:
        if scheme_id not in schemes:
            schemes[scheme_id] = (typology, set())
        schemes[scheme_id][1].add(account_id)
    return schemes


def score_chains(conn: duckdb.DuckDBPyConnection, chains: list[Chain]) -> GraphReport:
    schemes = _scheme_accounts(conn)
    layering = {sid: accts for sid, (typ, accts) in schemes.items() if typ == "layering"}

    detected_schemes = set()
    true_positive_chains = 0
    for chain in chains:
        accounts = set(chain.accounts)
        matched = [sid for sid, accts in layering.items()
                   if len(accounts & accts) >= MIN_SHARED_ACCOUNTS]
        if matched:
            true_positive_chains += 1
            detected_schemes.update(matched)

    reported = len(chains)
    precision = true_positive_chains / reported if reported else 0.0
    recall = len(detected_schemes) / len(layering) if layering else 0.0

    # Which typologies produce internal account-to-account edges at all? A scheme
    # touching fewer than two accounts inside this bank cannot form a path here.
    visibility: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for _sid, (typology, accts) in schemes.items():
        visibility[typology][1] += 1
        if len(accts) >= 2:
            visibility[typology][0] += 1

    return GraphReport(
        chains_reported=reported,
        true_positive_chains=true_positive_chains,
        false_positive_chains=reported - true_positive_chains,
        precision=precision,
        layering_schemes_total=len(layering),
        layering_schemes_detected=len(detected_schemes),
        recall=recall,
        schemes_with_internal_edges={k: tuple(v) for k, v in visibility.items()},
    )
