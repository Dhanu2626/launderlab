"""Plant screening ground truth into a generated world.

Phase 2's injectors label *transactions* by crime typology. Screening asks a
different question -- "is this customer actually the listed person?" -- so it
needs its own answer key, which is what this module creates:

  * `inject_entities`   renames real customers to (variants of) watchlist entries
                        and records them in `entity_labels`
  * `inject_adverse_media` writes synthetic news, some genuinely about those
                        planted entities (`media_labels`), some about unrelated
                        people who merely share a customer's name

The false-positive traps are mostly not fabricated here -- the population
generator already produces them, because it draws from a small name pool, so
customers who share a first name or surname with a listed entity occur naturally.
Those customers are simply left unlabelled, which is exactly what makes the
precision number mean something.
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path

import duckdb

# Ordered longest-first so multi-character rules win over single-character ones.
_TRANSLITERATIONS = [
    ("ph", "f"), ("kh", "k"), ("gh", "g"), ("ee", "i"), ("oo", "u"),
    ("ei", "ai"), ("ie", "i"), ("aa", "a"), ("ss", "s"), ("ll", "l"),
    ("mm", "m"), ("nn", "n"), ("dd", "d"), ("tt", "t"), ("y", "i"),
]

ADVERSE_TEMPLATES = [
    ("fraud", "{name} named in {city} investment fraud probe",
     "Investigators in {city} have named {name} in connection with an alleged "
     "investment scheme said to have taken deposits from retail savers."),
    ("corruption", "Anti-corruption bureau questions {name}",
     "The state anti-corruption bureau has questioned {name} over the award of "
     "procurement contracts, according to officials familiar with the matter."),
    ("money_laundering", "Enforcement agency searches premises linked to {name}",
     "Officials searched premises linked to {name} as part of a money laundering "
     "inquiry, seizing documents and electronic records."),
    ("trafficking", "{name} charged in cross-border trafficking case",
     "Prosecutors have charged {name} in a case involving the movement of goods "
     "across borders without declaration."),
    ("terrorism_financing", "Assets tied to {name} frozen pending review",
     "A tribunal has ordered assets connected to {name} frozen while a financing "
     "review is completed."),
]

BENIGN_TEMPLATES = [
    ("none", "{name} opens second outlet in {city}",
     "Local trader {name} has opened a second outlet in {city}, citing steady demand."),
    ("none", "{name} wins small business award",
     "{name} was recognised at a regional small business awards evening in {city}."),
    ("none", "{name} to speak at {city} trade meet",
     "Organisers confirmed {name} will address a session at the {city} trade meet."),
]


def _watchlist() -> list[dict]:
    """The same synthetic watchlist the screening engine uses, minus its banner row."""
    path = os.environ.get("LAUNDERLAB_WATCHLIST")
    source = Path(path) if path else resources.files("launderlab.db").joinpath("watchlist.json")
    entries = json.loads(Path(str(source)).read_text(encoding="utf-8"))
    return [e for e in entries if e.get("type") != "notice"]


def make_variant(name: str, kind: str, rng: random.Random) -> str:
    """Produce a realistic spelling variant of `name` for the given `kind`."""
    tokens = name.split()
    if kind == "exact":
        return name
    if kind == "reordered":
        shuffled = tokens[:]
        rng.shuffle(shuffled)
        return " ".join(shuffled)
    if kind == "initials":
        if len(tokens) < 2:
            return name
        return " ".join([t[0] for t in tokens[:-1]] + [tokens[-1]])
    # transliteration: perturb the spelling of one token that a rule actually fits
    candidates = [
        (i, old, new) for i, t in enumerate(tokens)
        for old, new in _TRANSLITERATIONS if old in t.lower()
    ]
    if not candidates:
        # no rule applies -- double a vowel instead, the Farhan/Farhaan pattern
        i = rng.randrange(len(tokens))
        token = tokens[i]
        for pos, ch in enumerate(token.lower()):
            if ch in "aeiou":
                tokens[i] = token[:pos + 1] + ch + token[pos + 1:]
                break
        return " ".join(tokens)
    i, old, new = rng.choice(candidates)
    tokens[i] = tokens[i].lower().replace(old, new, 1).title()
    return " ".join(tokens)


def inject_entities(conn: duckdb.DuckDBPyConnection, rng: random.Random,
                    n: int = 15) -> int:
    """Rename `n` individual customers to variants of watchlist entities and label them.

    Returns the number of entities planted. Individuals only -- business and
    merchant names in this world are trade names, not people, so planting a
    sanctioned individual's name on one would not resemble anything real.
    """
    watchlist = _watchlist()
    candidates = [r[0] for r in conn.execute(
        "SELECT customer_id FROM customers WHERE segment IN ('salaried','student','nri')"
        " ORDER BY customer_id"
    ).fetchall()]
    if not candidates:
        return 0

    n = min(n, len(candidates), len(watchlist))
    chosen_customers = rng.sample(candidates, n)
    chosen_entries = rng.sample(watchlist, n)
    kinds = ["exact", "transliteration", "initials", "reordered"]

    planted = 0
    for customer_id, entry in zip(chosen_customers, chosen_entries):
        kind = kinds[planted % len(kinds)]
        variant = make_variant(entry["name"], kind, rng)
        conn.execute("UPDATE customers SET full_name = ? WHERE customer_id = ?",
                     [variant, customer_id])
        conn.execute(
            "INSERT INTO entity_labels VALUES (?, ?, ?, ?)",
            [customer_id, entry["name"], entry.get("type", "sanctions"), kind],
        )
        planted += 1
    return planted


def inject_adverse_media(conn: duckdb.DuckDBPyConnection, rng: random.Random,
                         n_true: int = 10, n_trap: int = 10, n_benign: int = 20,
                         start: datetime | None = None) -> int:
    """Write synthetic news articles and link the genuine ones to their customer.

    Three kinds, deliberately mixed:
      * `n_true`   adverse article naming a planted entity  -> linked in media_labels
      * `n_trap`   adverse article naming an unrelated person who happens to share a
                   customer's name -> NOT linked (same name, different human)
      * `n_benign` ordinary business news -> not adverse at all, must never alert
    """
    start = start or datetime(2026, 7, 1)

    labelled = conn.execute(
        "SELECT c.customer_id, c.full_name, c.city FROM entity_labels l"
        " JOIN customers c USING (customer_id) ORDER BY c.customer_id"
    ).fetchall()
    others = conn.execute(
        "SELECT customer_id, full_name, city FROM customers"
        " WHERE customer_id NOT IN (SELECT customer_id FROM entity_labels)"
        " AND segment IN ('salaried','student','nri') ORDER BY customer_id"
    ).fetchall()

    written = 0

    def _write(name: str, city: str, adverse: bool) -> int:
        nonlocal written
        category, headline_t, body_t = rng.choice(
            ADVERSE_TEMPLATES if adverse else BENIGN_TEMPLATES)
        ts = start + timedelta(days=rng.randrange(0, 30), hours=rng.randrange(0, 24))
        conn.execute(
            "INSERT INTO adverse_media (ts, headline, body, mentioned_name, category)"
            " VALUES (?, ?, ?, ?, ?)",
            [ts, headline_t.format(name=name, city=city or "Hyderabad"),
             body_t.format(name=name, city=city or "Hyderabad"), name, category],
        )
        written += 1
        return conn.execute("SELECT max(article_id) FROM adverse_media").fetchone()[0]

    for customer_id, full_name, city in rng.sample(labelled, min(n_true, len(labelled))):
        article_id = _write(full_name, city, adverse=True)
        conn.execute("INSERT INTO media_labels VALUES (?, ?)", [article_id, customer_id])

    for _customer_id, full_name, city in rng.sample(others, min(n_trap, len(others))):
        # adverse article about a *different* human who shares this name -- no label
        _write(full_name, city, adverse=True)

    for _customer_id, full_name, city in rng.sample(others, min(n_benign, len(others))):
        _write(full_name, city, adverse=False)

    return written
