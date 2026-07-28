"""Run screening across the whole customer base.

Two legs, both producing candidates for human adjudication:

  * `screen_customers`  every customer against the sanctions/PEP watchlist
  * `screen_media`      every adverse news article against every customer name

CRITICAL BOUNDARY, same as detect/rules.py: nothing here may read `entity_labels`
or `media_labels`. The engine earns its hits from names alone; scoring.py is the
only module allowed to see the answer key.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import duckdb

from launderlab.screening.matcher import DEFAULT_THRESHOLD, similarity

# An article with this category is ordinary business news, not an adverse hit.
BENIGN_CATEGORY = "none"


@dataclass(frozen=True)
class EntityHit:
    customer_id: str
    customer_name: str
    matched_name: str
    score: float
    list_type: str
    program: str


@dataclass(frozen=True)
class MediaHit:
    customer_id: str
    customer_name: str
    article_id: int
    category: str
    headline: str
    score: float


def load_watchlist() -> list[dict]:
    """Watchlist entries, minus the provenance banner row (data, not a person)."""
    path = os.environ.get("LAUNDERLAB_WATCHLIST")
    source = Path(path) if path else resources.files("launderlab.db").joinpath("watchlist.json")
    entries = json.loads(Path(str(source)).read_text(encoding="utf-8"))
    return [e for e in entries if e.get("type") != "notice"]


def screen_customers(conn: duckdb.DuckDBPyConnection,
                     threshold: float = DEFAULT_THRESHOLD) -> list[EntityHit]:
    """Screen every customer name against the watchlist."""
    watchlist = load_watchlist()
    customers = conn.execute(
        "SELECT customer_id, full_name FROM customers ORDER BY customer_id"
    ).fetchall()

    hits = []
    for customer_id, full_name in customers:
        for entry in watchlist:
            score = similarity(full_name, entry["name"])
            if score >= threshold:
                hits.append(EntityHit(
                    customer_id=customer_id, customer_name=full_name,
                    matched_name=entry["name"], score=score,
                    list_type=entry.get("type", ""), program=entry.get("program", ""),
                ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def screen_media(conn: duckdb.DuckDBPyConnection,
                 threshold: float = DEFAULT_THRESHOLD) -> list[MediaHit]:
    """Link adverse news articles to customers by name.

    Benign articles are skipped outright -- an article has to actually allege
    something before matching a customer to it means anything.
    """
    articles = conn.execute(
        "SELECT article_id, mentioned_name, category, headline FROM adverse_media"
        " WHERE category != ? ORDER BY article_id", [BENIGN_CATEGORY]
    ).fetchall()
    customers = conn.execute(
        "SELECT customer_id, full_name FROM customers ORDER BY customer_id"
    ).fetchall()

    hits = []
    for article_id, mentioned_name, category, headline in articles:
        for customer_id, full_name in customers:
            score = similarity(mentioned_name, full_name)
            if score >= threshold:
                hits.append(MediaHit(
                    customer_id=customer_id, customer_name=full_name,
                    article_id=article_id, category=category,
                    headline=headline, score=score,
                ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits
