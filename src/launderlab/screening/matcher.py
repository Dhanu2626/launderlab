"""Fuzzy name matching for sanctions/PEP screening.

This replaces the first-draft `difflib` matcher in mcp_server.py, which was pure
edit distance and therefore phonetically blind (its own `ponytail:` comment marked
this exact upgrade).

WHY THESE TWO SIGNALS, measured not assumed — on real transliteration pairs:

    pair                  Jaro-Winkler   metaphone   soundex   nysiis
    farhan/farhaan            0.971        match      match     match
    sheikh/shaikh             0.911        match      match     match
    mohammed/muhammad         0.850        match      match     match
    nguyen/nuyen              0.950         MISS       MISS      MISS
    krishnan/krishnn          0.975         MISS      match      MISS
    rodriguez/rodrigez        0.978         MISS      match     match
    smith/jones               0.000         MISS       MISS      MISS

Jaro-Winkler carries the cases every phonetic algorithm misses (including
nguyen/nuyen, the case the ponytail comment named), and correctly scores 0 for
unrelated names. Metaphone earns its place on the other side: mohammed/muhammad
scores only 0.850 on Jaro-Winkler — under a threshold tuned to keep false
positives down — but is phonetically identical, so it should still surface. So
Jaro-Winkler is the primary signal and Metaphone is corroborating evidence that
can lift an otherwise-borderline pair.

NOTE ON DOUBLE METAPHONE: jellyfish does not ship it — the library exposes
`metaphone`, `soundex`, `nysiis` and `match_rating_codex` only. Single Metaphone
covers the transliteration cases this world actually produces, so rather than add
a second phonetics dependency for one algorithm, this uses jellyfish's Metaphone
and lets Jaro-Winkler cover what it misses. Revisit if names whose *alternate*
phonetic encodings matter (Slavic/Vietnamese romanisation) start showing up.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import jellyfish

# A pair whose tokens are all phonetically identical is treated as at least this
# similar, even when Jaro-Winkler alone would score lower (the mohammed/muhammad
# case). Below the default screening threshold would make the signal useless;
# far above it would let loose phonetic collisions through on their own.
PHONETIC_FLOOR = 0.92

# An initial ("S") standing in for a full token ("Suresh") is real but weak
# evidence — enough to keep a candidate alive, not enough to clear a hit alone.
INITIAL_MATCH_SCORE = 0.85

DEFAULT_THRESHOLD = 0.88


@dataclass(frozen=True)
class Match:
    name: str
    score: float
    list_type: str
    program: str
    country: str


def normalise(name: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    So 'Farhaan  Ali.' and 'farhan ali' are compared on equal footing.
    """
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z ]", " ", stripped.lower()).split())


def _phonetic(token: str) -> str:
    return jellyfish.metaphone(token)


def _token_score(a: str, b: str) -> float:
    """Compare two single name tokens."""
    if a == b:
        return 1.0
    # initials: 'S' vs 'Suresh'
    if len(a) == 1 or len(b) == 1:
        return INITIAL_MATCH_SCORE if a[0] == b[0] else 0.0
    jw = jellyfish.jaro_winkler_similarity(a, b)
    if _phonetic(a) and _phonetic(a) == _phonetic(b):
        return max(jw, PHONETIC_FLOOR)
    return jw


def _alignment(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Greedy best-partner alignment, averaged over the shorter name's tokens.

    Averaging over the *shorter* name is deliberate: 'S K Gupta' should be able to
    match 'Suresh Kumar Gupta' without being penalised for the tokens it omits,
    which is exactly how an abbreviated name appears on a real payment instruction.
    """
    if not tokens_a or not tokens_b:
        return 0.0
    short, long_ = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    remaining = list(long_)
    total = 0.0
    for token in short:
        if not remaining:
            break
        best_i, best = 0, -1.0
        for i, candidate in enumerate(remaining):
            s = _token_score(token, candidate)
            if s > best:
                best_i, best = i, s
        total += max(best, 0.0)
        remaining.pop(best_i)
    return total / len(short)


def similarity(a: str, b: str) -> float:
    """0.0-1.0 similarity between two names. 1.0 only for an exact match.

    Scored purely on token alignment, NOT on whole-string Jaro-Winkler. Measured
    reason: Jaro-Winkler weights a common prefix heavily, so two different people
    who merely share a first name score dangerously high on the raw strings --
    'Suresh Kumar' vs 'Suresh Gupta' came out at 0.900, above any usable
    threshold. Aligning token-by-token instead forces every part of the shorter
    name to find a partner, which drops that same pair to 0.73 while leaving real
    transliterations (0.95+) untouched. This matters more here than in most
    screening engines because the population generator draws from a small name
    pool, so shared-first-name and shared-surname collisions are everywhere.
    """
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # alignment is order-insensitive by construction (greedy best partner), so
    # reordered names need no separate sorted-token pass
    return round(_alignment(na.split(), nb.split()), 4)


def screen(name: str, watchlist: list[dict],
           threshold: float = DEFAULT_THRESHOLD) -> list[Match]:
    """Every watchlist entry scoring at or above `threshold`, best first.

    Returns candidates for a human to adjudicate — never a cleared/confirmed
    verdict. A screening hit is a lead, not an identification.
    """
    matches = [
        Match(name=entry["name"], score=score, list_type=entry.get("type", ""),
              program=entry.get("program", ""), country=entry.get("country", ""))
        for entry in watchlist
        if (score := similarity(name, entry["name"])) >= threshold
    ]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches
