"""Combine four detection layers into one risk score per account.

This is slice 7.1, and it was deliberately left until now. Phases 3-6 each
produce a signal on a different scale — a rule either fires or it does not, a
screening match is 0.88-1.00, a graph chain has a length and an amount, six ML
models emit probabilities, decision-function distances and reconstruction errors.
Designing a formula before those distributions existed would have been guessing.

WHY A WEIGHTED SUM AND NOT A META-MODEL. Stacking a classifier on top of six
classifiers would very likely score better. It would also make every alert
unexplainable, and "the model said so" is not a Suspicious Activity Report — an
investigator has to write down why, and a regulator has to be able to follow it.
So the score is a transparent weighted sum where every point is attributable to a
named signal, and `RiskScore.signals` carries that attribution to the UI.

WHETHER THIS IS WORTH DOING AT ALL is a measurable question, not an assumption:
if the combined score does not rank better than the single best detector, the
aggregation is complexity for nothing. `compare_against_individual()` exists to
answer that honestly rather than take it on faith.

BOUNDARY: this module reads detector *outputs*, never `scheme_labels`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from launderlab.detect import rules
from launderlab.graph import build as graph_build
from launderlab.graph import motifs
from launderlab.screening import engine as screening_engine

# Deliberately readable and tunable rather than learned. Rules and graph carry
# most weight because their hits are explainable in a sentence; ML carries less
# because its contribution is a ranking, not a reason.
DEFAULT_WEIGHTS = {
    "rules": 0.35,
    "graph": 0.30,
    "screening": 0.20,
    "ml": 0.15,
}

# Adverse media is DELIBERATELY ABSENT from the weights above and OFF by default
# in `collect()`. It is a candidate signal under measurement, not a shipped one.
#
# Why it is its own source rather than folded into `screening`: both answer an
# identity question, but Phase 4 measured entity screening at 75% precision and
# adverse media at 15.8%. Folding the noisy leg into the clean leg's weight would
# let it inherit trust it has not earned, and would make the two impossible to
# separate again. An analyst also needs a different sentence for each -- "the name
# matches a sanctions list" and "adverse news names this customer" are different
# claims with different follow-up work.
#
# Why off by default: turning it on changes every account's score, which would
# silently move the numbers every earlier phase published. Media stays opt-in
# until a measurement says it earns a place. `weights_with_media()` builds the
# candidate configurations the experiment compares.
MEDIA_SOURCE = "media"


def weights_with_media(media_weight: float,
                       base: dict[str, float] | None = None) -> dict[str, float]:
    """`base` plus a media weight, renormalised so the total stays 1.0.

    Renormalising rather than appending: the score is documented as 0-100 and the
    bands are calibrated against that, so letting the weights sum past 1.0 would
    push scores over 100 and quietly invalidate every band boundary.

    The catch this creates is real and the experiment has to handle it -- shrinking
    every other weight also lowers what a lone control can score, and 7.10 showed
    that a control whose ceiling falls below the case-opening threshold is switched
    off without anything failing. So the threshold is re-derived per candidate by
    `derive_min_case_score()` rather than assumed to still be 17.5.
    """
    base = dict(base or DEFAULT_WEIGHTS)
    base[MEDIA_SOURCE] = media_weight
    total = sum(base.values())
    return {source: weight / total for source, weight in base.items()}


def derive_min_case_score(weights: dict[str, float]) -> tuple[float, float, float]:
    """(threshold, quietest_control, model_ceiling) for a given weight table.

    Same rule as `MIN_CASE_SCORE`, applied to arbitrary weights so candidate
    configurations are judged the way the shipped one was: a case opens when any
    control asserts something, and never on the model alone. Returns the window as
    well as the number, because a candidate that makes the window empty is
    disqualified rather than quietly rounded into shape.
    """
    from launderlab.graph import motifs
    from launderlab.screening.matcher import DEFAULT_THRESHOLD

    quietest = min(
        weights.get("rules", 0.0) * corroboration_strength(1),
        weights.get("graph", 0.0) * corroboration_strength(motifs.DEFAULT_MIN_HOPS),
        weights.get("screening", 0.0) * DEFAULT_THRESHOLD,
    ) * 100
    ceiling = weights.get("ml", 0.0) * 100
    # sit just under the quietest control, mirroring 17.5 against 17.6
    return round(quietest - 0.1, 2), round(quietest, 2), round(ceiling, 2)

# Bands describe how much INDEPENDENT CORROBORATION a case has, because that is
# what the weighted sum above actually measures.
#
# They were 80/55/30/0 until the SAR narrative in 7.8 printed one out: a
# confirmed structuring scheme -- 50 cash deposits totalling Rs 33,43,000, which
# Phase 3 flags with high confidence -- was described to a Financial Intelligence
# Unit as "low band". Measured across the whole demo bank, every one of 50 cases
# landed in low or medium and the top score in the bank was 43.5. **"high" and
# "critical" described nothing that could exist.**
#
# The cause is that the thresholds read the 0-100 score as a percentage of
# something attainable, and it is not: 100 requires all four layers firing at
# full strength on one account, while most real cases are seen by exactly one
# layer. So the thresholds are set from the signal algebra instead:
#
#   one rule firing        0.35 x 0.60           = 21.0  -> medium
#   one 3-hop chain        0.30 x 0.75           = 22.5  -> medium
#   rules + graph together 0.35x0.60 + 0.30x0.75 = 43.5  -> high
#   three rules + 4 hops   0.35x0.94 + 0.30x1.00 = 62.9  -> critical
#
# Read as: low is below the threshold at which a case is opened at all, medium
# is one named piece of evidence, high is two independent layers agreeing, and
# critical is strong corroboration across layers. Derived from what the formula
# can produce, not fitted to one world's histogram.
BANDS = [(60, "critical"), (40, "high"), (18, "medium"), (0, "low")]

# The order the queue works evidence in. A case is tiered by the FIRST of these
# it has a signal from, so a case with both a chain and a name match is worked as
# network evidence.
#
# ORDERED BY HOW SPECIFIC A REASON THE ANALYST GETS, which is a firmer principle
# than 7.1's precision numbers and gives a different answer. Graph names a path.
# A rule names a scenario. Screening names a listed person. A model names
# *nothing* — it only ranks — so it is genuinely the last resort: "no layer could
# say why, but this account looks unlike its peers".
#
# Using 7.1's standalone precisions (graph 1.000, rules 0.72, ml 0.60, screening
# 0.250) to order this was a stretch, and it broke as soon as the model was wired
# into the demo world: those figures measure each layer as a lone ranker, not the
# value of a signal sitting alongside another. With ml ahead of screening, every
# sanctions hit that also happened to be model-ranked was filed under
# "model-ranked" — the analyst is told a model found it when a watchlist did.
# The precision figures still belong in the tier descriptions, as context.
#
# Canonical here rather than in the page so the two cannot drift; a test pins the
# UI's ordering to this list.
TIER_ORDER = ("graph", "rules", "screening", "ml")

# The score at which an account is worth opening a case on.
#
# This was 20.0 and it silently destroyed most of Phase 4. A screening-only case
# scores weight x match, so with weight 0.20 its ceiling is *exactly* 20.0 — an
# account only opened a case on a PERFECT 1.000 name match. Every transliteration,
# initials and reordered variant the fuzzy matcher exists to catch scored
# 0.887-0.984, landing at 17.7-19.7, and was dropped at the gate. 14 of the 15
# planted watchlist entities never reached an analyst. Phase 4 measured 100%
# recall; the aggregation then threw it away, and nothing failed.
#
# So the threshold is derived from both sides rather than picked:
#
#   floor  — screening's own accept threshold is 0.88, so the least it will ever
#            assert is 0.88 x 0.20 x 100 = 17.6. Anything a control is willing to
#            flag must be able to open a case, or the control is decoration.
#   ceiling— the model's maximum contribution is 0.15 x 1.0 x 100 = 15.0, and the
#            threshold must stay ABOVE it. That is deliberate, not incidental: a
#            model-only alert has no reason to give an analyst, and "the model said
#            so" is not a Suspicious Activity Report. The model corroborates and
#            ranks; it does not open cases by itself.
#
# A test pins this window, so changing any weight forces the decision to be made
# again rather than quietly breaking a layer.
MIN_CASE_SCORE = 17.5

# Evidence saturates with DIMINISHING RETURNS, not linearly.
#
# This was `min(n, 3) / 3` for rules until the queue UI was actually looked at,
# and the bug was only visible there: a real structuring scheme -- 27 cash
# deposits totalling Rs 2.6M, which Phase 3 flags with high confidence -- trips
# exactly ONE rule, so it scored 0.35 x 1/3 = 11.7 out of 100, landed in the "low"
# band and was filtered out of the queue entirely. Meanwhile a mule account
# scored 34.2 and appeared. The system was hiding genuine placement cases.
#
# The flaw was treating one piece of evidence as a fraction of a signal. In
# practice most real cases trip exactly one scenario; a second is meaningful
# corroboration, a third adds little. So: 1 -> 0.60, 2 -> 0.84, 3 -> 0.94.
#
# THE GRAPH LAYER HAD THE IDENTICAL BUG and it survived three more slices, because
# every chain in the demo world happens to be 3 hops long. Chain strength was
# `min(hops, 4) / 4`, so the SHORTEST chain Phase 5 will report -- 2 hops, which
# is real, named, traceable evidence with both ledger rows behind it -- scored
# half. At weight 0.30 that is 15.0 out of 100, exactly the model's own ceiling,
# which made the case-opening threshold unsatisfiable: no single cut could admit a
# minimal chain while excluding a model-only alert. Found by a test written about
# the threshold, not about the graph. Same curve, same reason.
DECAY = 0.4


def corroboration_strength(count: int) -> float:
    """Diminishing-returns weight for `count` independent pieces of one kind of
    evidence: 1 -> 0.60, 2 -> 0.84, 3 -> 0.94, saturating at 1.0."""
    return 1.0 - DECAY ** max(count, 0) if count else 0.0


# Kept as a name because the rules path reads better with it, and because
# `rule_strength` is referenced by 7.4's regression test.
rule_strength = corroboration_strength


@dataclass(frozen=True)
class RiskSignal:
    source: str
    detail: str
    contribution: float  # 0.0-1.0 within its own source


@dataclass(frozen=True)
class RiskScore:
    account_id: str
    score: float  # 0-100
    band: str
    signals: list[RiskSignal] = field(default_factory=list)

    @property
    def sources(self) -> set[str]:
        return {s.source for s in self.signals}


def _band(score: float) -> str:
    return next(name for threshold, name in BANDS if score >= threshold)


MEDIA_MODES = ("off", "separate", "folded")


def collect(conn: duckdb.DuckDBPyConnection,
            ml_scores: dict[str, float] | None = None,
            media_mode: str = "off") -> dict[str, list[RiskSignal]]:
    """Run every detection layer and gather its signals per account.

    `ml_scores` is passed in rather than computed here: the ML layer needs a
    fitted model and a train/test discipline that belongs to the caller, and a
    workbench in production would be scoring against a model trained weeks ago.
    Expected pre-normalised to 0-1.
    """
    signals: dict[str, list[RiskSignal]] = {}

    def add(account_id: str, signal: RiskSignal) -> None:
        signals.setdefault(account_id, []).append(signal)

    # Phase 3 — rules. Each distinct rule that fires is one piece of evidence.
    fired: dict[str, set[str]] = {}
    for alert in rules.run_all(conn):
        fired.setdefault(alert.account_id, set())
        if alert.rule not in fired[alert.account_id]:
            fired[alert.account_id].add(alert.rule)
            add(alert.account_id, RiskSignal(
                source="rules", detail=f"{alert.rule}: {alert.reason}",
                contribution=0.0))  # filled in below, once the count is known
    # rewrite rule contributions now that we know how many fired per account
    for account_id, rule_names in fired.items():
        share = rule_strength(len(rule_names))
        signals[account_id] = [
            RiskSignal(s.source, s.detail, share) if s.source == "rules" else s
            for s in signals[account_id]
        ]

    # Phase 4 — screening. The best match is what an analyst adjudicates.
    best_match: dict[str, tuple[float, str]] = {}
    for hit in screening_engine.screen_customers(conn):
        account = conn.execute(
            "SELECT account_id FROM accounts WHERE customer_id = ?", [hit.customer_id]
        ).fetchone()
        if account is None:
            continue
        current = best_match.get(account[0])
        if current is None or hit.score > current[0]:
            best_match[account[0]] = (hit.score, f"name matches {hit.matched_name} "
                                                  f"({hit.list_type}) at {hit.score:.2f}")
    for account_id, (score, detail) in best_match.items():
        add(account_id, RiskSignal("screening", detail, score))

    # Adverse media -- OFF unless asked for. Same shape as the entity leg: the
    # strongest match is what an analyst adjudicates. Deliberately not corroborated
    # across articles yet, because the question under measurement is whether media
    # belongs in this score at all, and tuning its internal shape at the same time
    # would leave two variables moving in one experiment.
    # "folded" emits media under the SCREENING source instead of its own. That is
    # not a cosmetic difference: `aggregate()` keeps only the strongest signal
    # within a source, so folding caps the total identity contribution at
    # screening's weight and makes it impossible for a name-list hit and a news
    # hit about the same name to STACK. Measured because separate sources let
    # exactly that stacking push confirmed structuring cases out of the queue.
    if media_mode not in MEDIA_MODES:
        raise ValueError(f"media_mode must be one of {MEDIA_MODES}, got {media_mode!r}")
    if media_mode != "off":
        media_source = MEDIA_SOURCE if media_mode == "separate" else "screening"
        best_article: dict[str, tuple[float, str]] = {}
        for hit in screening_engine.screen_media(conn):
            account = conn.execute(
                "SELECT account_id FROM accounts WHERE customer_id = ?", [hit.customer_id]
            ).fetchone()
            if account is None:
                continue
            current = best_article.get(account[0])
            if current is None or hit.score > current[0]:
                best_article[account[0]] = (
                    hit.score,
                    f"adverse media ({hit.category}) names this customer at "
                    f"{hit.score:.2f}: {hit.headline}")
        for account_id, (score, detail) in best_article.items():
            add(account_id, RiskSignal(media_source, detail, score))

    # Phase 5 — graph. Position in a pass-through chain.
    graph = graph_build.build_graph(conn)
    for chain in motifs.find_chains(graph):
        # a longer chain is stronger evidence, with diminishing returns -- and
        # crucially the SHORTEST reportable chain is not worth half a signal. See
        # the note on DECAY: linear-in-hops made a 2-hop chain score exactly as
        # much as a model guess.
        strength = corroboration_strength(chain.hops)
        for account_id in chain.accounts:
            add(account_id, RiskSignal(
                source="graph",
                # plain "Rs" rather than the rupee sign: this string is printed to
                # Windows consoles, which default to cp1252 and cannot encode it
                detail=f"in a {chain.hops}-hop pass-through chain "
                       f"(Rs {chain.amounts[0]:,.0f} entering, {chain.retained:.0%} retained)",
                contribution=strength))

    # Phase 6 — ML, if the caller supplied scores.
    for account_id, score in (ml_scores or {}).items():
        if score > 0:
            add(account_id, RiskSignal("ml", f"model risk score {score:.2f}", score))

    return signals


def aggregate(signals: dict[str, list[RiskSignal]],
              weights: dict[str, float] | None = None) -> list[RiskScore]:
    """Weighted sum across sources, 0-100, highest first.

    Within a source the strongest signal wins rather than accumulating, so an
    account in three chains is not automatically triple-scored — the question an
    analyst asks is "how strong is the graph evidence", not "how much of it is
    there".
    """
    weights = weights or DEFAULT_WEIGHTS
    scored: list[RiskScore] = []

    for account_id, account_signals in signals.items():
        strongest: dict[str, RiskSignal] = {}
        for signal in account_signals:
            current = strongest.get(signal.source)
            if current is None or signal.contribution > current.contribution:
                strongest[signal.source] = signal

        total = sum(weights.get(source, 0.0) * signal.contribution
                    for source, signal in strongest.items())
        score = round(total * 100, 2)
        scored.append(RiskScore(account_id=account_id, score=score, band=_band(score),
                                 signals=sorted(account_signals,
                                                key=lambda s: s.contribution, reverse=True)))

    # Ties break on account id, deliberately, rather than being left to whatever
    # order the signals happened to be collected in.
    #
    # This is not tidiness. Every single-rule case scores exactly 0.35 x 0.60 =
    # 21.00, and on the demo world FORTY-FIVE accounts sit on that one value with
    # the alert budget's cut falling inside the cluster -- so which 24 of 45 an
    # analyst actually works was decided by dictionary insertion order. It moved
    # the measured baseline by two true positives between two runs of the same
    # command, which is how it was noticed at all.
    #
    # A stable order does not make the ranking *right* (see the note below), but an
    # arbitrary one makes every budget-capped measurement partly noise and makes an
    # analyst's queue reshuffle for no reason between refreshes.
    #
    # KNOWN AND UNFIXED: rule strength ignores the rule's own magnitude, so a
    # 27-deposit structuring scheme and an 89-deposit one both score 21.00. Fixing
    # that means giving rules a confidence, which is a scoring change that needs its
    # own measurement rather than a guess bolted on here.
    return sorted(scored, key=lambda r: (-r.score, r.account_id))


def score_accounts(conn: duckdb.DuckDBPyConnection,
                   ml_scores: dict[str, float] | None = None,
                   weights: dict[str, float] | None = None,
                   media_mode: str = "off") -> list[RiskScore]:
    """Convenience: collect every layer's signals and aggregate them.

    `media_mode` defaults to "off" so every figure published before adverse media
    was a candidate reproduces unchanged.
    """
    return aggregate(collect(conn, ml_scores, media_mode=media_mode), weights)
