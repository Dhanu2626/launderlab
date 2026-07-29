"""Reconstruct the internal transfer graph from the ledger.

The ledger stores transactions, not transfers: an internal payment is two rows
(payer DR + payee CR) that share a reference number, an amount and a timestamp.
This module pairs them back into directed edges.

WHY REFERENCE NUMBERS, not just (timestamp, amount): joining on time and amount
alone cross-pairs unrelated transfers that happen to coincide — on a 400-customer
world that produced visibly wrong edges. The narration carries the same reference
on both legs (`UPI/DR/519377/...` and `UPI/CR/519377/...`), which is the only field
that actually identifies *one* payment.

WHAT THE GRAPH CANNOT SEE, and why that matters: only transfers where BOTH parties
bank here become edges. Cash deposits, shell-company invoices, offshore
round-trips and international remittances all have counterparties outside this
bank, so they leave a single leg and no edge at all. Of the six injected
typologies only mule networks are visible here — which is not a limitation of the
algorithm but a miniature of the cross-bank blind spot in the project's research
thesis (see PROJECT.md).

BOUNDARY: nothing here may read `scheme_labels`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb
import networkx as nx

# Both legs of an internal payment carry the same reference in field 3 of the
# narration. Rows without that shape (ATM withdrawals, cash deposits) can't pair.
_EDGE_SQL = """
WITH legs AS (
    SELECT txn_id, account_id, direction, amount, ts,
           split_part(narration, '/', 3) AS ref
    FROM transactions
    WHERE narration LIKE '%/%/%/%'
)
SELECT dr.account_id AS src, cr.account_id AS dst, dr.amount::DOUBLE AS amount,
       dr.ts AS ts, dr.txn_id AS dr_txn, cr.txn_id AS cr_txn
FROM legs dr
JOIN legs cr
  ON dr.ref = cr.ref AND dr.amount = cr.amount AND dr.ts = cr.ts
 AND dr.direction = 'DR' AND cr.direction = 'CR'
 AND dr.account_id <> cr.account_id
"""


@dataclass(frozen=True)
class Transfer:
    src: str
    dst: str
    amount: float
    ts: datetime
    # The two ledger rows this edge was reconstructed FROM. Carried rather than
    # discarded so an investigator can get back from a detected chain to the
    # actual statement lines that make it up -- a chain an analyst cannot trace
    # to transactions is an assertion, not evidence, and a SAR narrative has to
    # cite rows. The pairing SQL already computes both ids.
    dr_txn: int
    cr_txn: int


def load_transfers(conn: duckdb.DuckDBPyConnection) -> list[Transfer]:
    """Every internal account-to-account transfer, as directed edges."""
    return [
        Transfer(src=src, dst=dst, amount=amount, ts=ts, dr_txn=dr, cr_txn=cr)
        for src, dst, amount, ts, dr, cr in conn.execute(_EDGE_SQL).fetchall()
    ]


def build_graph(conn: duckdb.DuckDBPyConnection) -> nx.MultiDiGraph:
    """Directed multigraph of internal transfers.

    A MultiDiGraph, not a DiGraph: two accounts can transact repeatedly and each
    payment is its own edge with its own timestamp and amount. Collapsing them
    would destroy exactly the timing information mule-chain detection depends on.
    """
    graph = nx.MultiDiGraph()
    for transfer in load_transfers(conn):
        graph.add_edge(transfer.src, transfer.dst,
                       amount=transfer.amount, ts=transfer.ts,
                       dr_txn=transfer.dr_txn, cr_txn=transfer.cr_txn)
    return graph
