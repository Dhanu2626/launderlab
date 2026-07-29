"""Flow-motif detection over the transfer graph.

The motif that matters for layering is the **chain**: money arriving at an account
and leaving again shortly after, slightly smaller, then repeating. Phase 3's
`rapid_pass_through` rule already sees one hop of this from a single account's
point of view. What it structurally cannot see is that the account it flagged
sits in the middle of a longer path — that fact does not exist in any one
account's history, only in the edges between accounts. This module is the part
of the stack that can see it.

Community detection is deliberately NOT used here. It clusters densely connected
groups, which suits laundering *rings* (cycles, tight mutual clusters); the
typology this project actually injects is a directed chain, where path-following
is both more precise and more explainable to an investigator. Worth revisiting if
a ring-shaped typology is ever added.

Fan-in / fan-out detectors were built and then REMOVED rather than shipped. They
are standard AML motifs, but measured against this world they fired zero times at
any useful threshold, and loosening the threshold until they fired produced only
merchants -- 72 of 76 hits were shops legitimately receiving many small customer
payments, i.e. pure false positives. None of the six injected typologies is
fan-shaped: mule chains are linear, and structuring/shell/round-trip/dormant all
have counterparties outside the bank. Shipping a detector that has never detected
anything would be decoration. Add it back alongside a fan-shaped typology.

BOUNDARY: nothing here may read `scheme_labels`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import networkx as nx

# Injected mule hops skim 3-8% and land 2-30 hours apart. The windows below sit
# just outside that so detection is not tuned to the exact generator constants --
# a rule that only works against its own simulator's parameters proves nothing.
DEFAULT_MAX_HOP_HOURS = 36
DEFAULT_RETAIN_MIN = 0.80
DEFAULT_RETAIN_MAX = 1.00
DEFAULT_MIN_AMOUNT = 50000
DEFAULT_MIN_HOPS = 2


@dataclass(frozen=True)
class Chain:
    accounts: tuple[str, ...]
    amounts: tuple[float, ...]
    started: datetime
    ended: datetime
    # One (DR row, CR row) pair per hop, in order. A chain the analyst cannot
    # trace back to statement lines is an assertion rather than evidence, and the
    # SAR narrative in 7.8 has to cite the rows it is describing.
    hop_txns: tuple[tuple[int, int], ...] = ()

    @property
    def hops(self) -> int:
        return len(self.accounts) - 1

    @property
    def retained(self) -> float:
        """Fraction of the entry amount that reached the final account."""
        return self.amounts[-1] / self.amounts[0] if self.amounts[0] else 0.0


def _forward_edges(graph: nx.MultiDiGraph, node: str):
    for _u, v, data in graph.out_edges(node, data=True):
        yield v, data


def find_chains(graph: nx.MultiDiGraph, max_hop_hours: int = DEFAULT_MAX_HOP_HOURS,
                retain_min: float = DEFAULT_RETAIN_MIN,
                retain_max: float = DEFAULT_RETAIN_MAX,
                min_amount: float = DEFAULT_MIN_AMOUNT,
                min_hops: int = DEFAULT_MIN_HOPS) -> list[Chain]:
    """Find pass-through chains: money forwarded onward, promptly and mostly intact.

    A hop qualifies when the outgoing transfer happens after the incoming one,
    within `max_hop_hours`, and carries between `retain_min` and `retain_max` of
    what came in — i.e. the account kept a cut rather than spending the money.
    Chains are grown depth-first and only maximal ones are returned, so a 3-hop
    chain is reported once rather than also as its two 2-hop prefixes.
    """
    window = timedelta(hours=max_hop_hours)
    chains: list[Chain] = []

    def _rows(data: dict) -> tuple[int, int]:
        return (data.get("dr_txn", -1), data.get("cr_txn", -1))

    def extend(path: list[str], amounts: list[float], times: list[datetime],
               txns: list[tuple[int, int]]) -> bool:
        """Returns True if the path was extended at least once."""
        extended = False
        for nxt, data in _forward_edges(graph, path[-1]):
            if nxt in path:  # never revisit -- a cycle is a different motif
                continue
            gap = data["ts"] - times[-1]
            if not (timedelta(0) < gap <= window):
                continue
            ratio = data["amount"] / amounts[-1] if amounts[-1] else 0.0
            if not (retain_min <= ratio <= retain_max):
                continue
            extended = True
            grew = extend(path + [nxt], amounts + [data["amount"]], times + [data["ts"]],
                          txns + [_rows(data)])
            if not grew:  # maximal -- record it here
                full = path + [nxt]
                if len(full) - 1 >= min_hops:
                    chains.append(Chain(
                        accounts=tuple(full),
                        amounts=tuple(amounts + [data["amount"]]),
                        started=times[0], ended=data["ts"],
                        hop_txns=tuple(txns + [_rows(data)]),
                    ))
        return extended

    for src, dst, data in graph.edges(data=True):
        if data["amount"] < min_amount:
            continue
        extend([src, dst], [data["amount"]], [data["ts"]], [_rows(data)])

    # de-duplicate identical paths, then drop any chain that is only a fragment of
    # a longer one. Growing from every edge means a 4-hop chain is also discovered
    # starting from its 2nd and 3rd accounts; an investigator wants the whole chain
    # once, not four overlapping views of the same money.
    unique: dict[tuple[str, ...], Chain] = {}
    for chain in chains:
        unique.setdefault(chain.accounts, chain)

    longest_first = sorted(unique.values(), key=lambda c: len(c.accounts), reverse=True)
    kept: list[Chain] = []
    for chain in longest_first:
        if not any(_is_contiguous_within(chain.accounts, k.accounts) for k in kept):
            kept.append(chain)
    return sorted(kept, key=lambda c: c.amounts[0], reverse=True)


def _is_contiguous_within(short: tuple[str, ...], long_: tuple[str, ...]) -> bool:
    """True if `short` appears as an unbroken run inside `long_`."""
    if len(short) >= len(long_):
        return False
    return any(long_[i:i + len(short)] == short for i in range(len(long_) - len(short) + 1))
