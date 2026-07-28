"""Score the screening engine against ground truth.

The only module allowed to read `entity_labels` / `media_labels` -- engine.py and
matcher.py must never see them, exactly as detect/scoring.py is the only module
allowed to read `scheme_labels`.

Scored at the level a decision actually gets made: per customer, not per candidate
pair. One customer matching three watchlist spellings is one alert on an analyst's
queue, not three, and counting it three times would flatter precision.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import duckdb

from launderlab.screening.engine import EntityHit, MediaHit


@dataclass(frozen=True)
class ScreeningReport:
    flagged_customers: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    false_positive_rate: float
    by_match_kind: dict = field(default_factory=dict)  # kind -> (detected, total)


@dataclass(frozen=True)
class MediaReport:
    flagged_pairs: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float


def _prf(true_positives: int, flagged: int, actual: int) -> tuple[float, float, float]:
    precision = true_positives / flagged if flagged else 0.0
    recall = true_positives / actual if actual else 0.0
    fp_rate = (flagged - true_positives) / flagged if flagged else 0.0
    return precision, recall, fp_rate


def score_entities(conn: duckdb.DuckDBPyConnection,
                   hits: list[EntityHit]) -> ScreeningReport:
    """Grade sanctions/PEP screening. A customer is a true positive when they are
    genuinely a planted watchlist entity, regardless of which spelling matched."""
    flagged = {h.customer_id for h in hits}

    labels = conn.execute(
        "SELECT customer_id, match_kind FROM entity_labels"
    ).fetchall()
    truth = {customer_id for customer_id, _ in labels}
    kind_of = dict(labels)

    true_positives = flagged & truth
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for customer_id, kind in kind_of.items():
        by_kind[kind][1] += 1
        if customer_id in true_positives:
            by_kind[kind][0] += 1

    precision, recall, fp_rate = _prf(len(true_positives), len(flagged), len(truth))
    return ScreeningReport(
        flagged_customers=len(flagged),
        true_positives=len(true_positives),
        false_positives=len(flagged - truth),
        false_negatives=len(truth - flagged),
        precision=precision,
        recall=recall,
        false_positive_rate=fp_rate,
        by_match_kind={k: (d, t) for k, (d, t) in by_kind.items()},
    )


def score_media(conn: duckdb.DuckDBPyConnection, hits: list[MediaHit]) -> MediaReport:
    """Grade adverse-media linkage. Scored per (article, customer) pair, since the
    question is whether THIS article is about THIS customer."""
    flagged = {(h.article_id, h.customer_id) for h in hits}
    truth = {
        (article_id, customer_id) for article_id, customer_id in
        conn.execute("SELECT article_id, customer_id FROM media_labels").fetchall()
    }

    true_positives = flagged & truth
    precision, recall, _ = _prf(len(true_positives), len(flagged), len(truth))
    return MediaReport(
        flagged_pairs=len(flagged),
        true_positives=len(true_positives),
        false_positives=len(flagged - truth),
        false_negatives=len(truth - flagged),
        precision=precision,
        recall=recall,
    )
