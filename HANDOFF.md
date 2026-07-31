# LaunderLab — project handoff

**Rewritten from scratch 2026-07-31, after Phase 8.5 and the pre-Phase-9 audit.**
This file is the single authoritative handoff. A Claude session with none of the previous
conversation should be able to read this alone and continue immediately.

Read order for a new session: **this file** → `PROJECT.md` (slice log with every number) →
the last entry of `ledger/FIELD-NOTES.md`.

---

## 1. What this is

**LaunderLab is an open adversarial simulation range for anti-money-laundering (AML)
detection.** A synthetic bank; an injector that hides real laundering typologies inside it; a
four-layer detection stack that tries to catch them; an investigator workbench where a human
works the resulting alerts; a red team that adapts to what got caught; and a multi-bank
experiment that measures what no single institution can see.

Because the injector records ground truth, every detector is scored on real precision and
recall — something no actual bank can do with production data, because no bank knows what it
missed.

Built by **Dhanush Jangadi** (Hyderabad, FinCrime/AML fresh grad) as his flagship portfolio
project. Claude is the build partner. It is a career asset first and a research tool second:
the point is that he can walk into a Financial Crime Analyst interview having built every box
in the AML value chain and having measured each one honestly.

**The differentiating property of this project is intellectual honesty.** Repeatedly a
flattering number turned out to be an artefact, and each time it was measured, corrected and
*written down* rather than quietly kept. §7 is the full list. That pattern is the most valuable
thing here — preserve it.

- **Repo:** `C:\Users\DELL\OneDrive\Documents\CareerForge\launderlab`
- **GitHub:** https://github.com/Dhanu2626/launderlab (public, branch `main`)
- **Master plan:** `../LAUNDERLAB-PLAN.md` (in the CareerForge parent folder)

### The three research questions

1. **Detection decay** — how fast does a stack rot against an adapting adversary?
   **Answered by Phase 8, non-uniformly**: one rule collapses in 2 generations and stays
   collapsed; two never fully evade across 8.
2. **False-positive economics** — cost per true alert, measured for every config, not guessed.
   Threaded through Phases 3–7 and decided the adverse-media question in 7.12.
3. **The cross-bank blind spot** — what one bank cannot see, and what co-operation buys.
   **Answered by Phase 8.5**: banks flag 75–77% of individual mule accounts and reconstruct
   0–6% of the chains those accounts form. BIS Project Aurora does this privately; this is the
   open version.

---

## 2. Current state — verified 2026-07-31

| | |
|---|---|
| Last code change | `f263385` — "Fix six defects found auditing Phases 8 and 8.5 before Phase 9". Commits after it are documentation only. Run `git log --oneline -5` for the true head — a doc that pins its own hash is stale the moment it is committed |
| Working tree | clean, in sync with `origin/main` |
| Commits | 57 |
| Tests | **302 passing, zero skips** (~4-9 min locally, ~2:30 in CI) |
| Lint | `ruff` clean |
| CI | GitHub Actions green on every push, and **actually runs everything** — see §3 |
| Phases complete | 0, 2, 3, 4, 5, 6, 7, 8, 8.5, **9**; **1 core** (slice 1.3 deferred, non-blocking). **All phases done.** |

| Phase | Name | Status |
|---|---|---|
| 0 | Foundations | ✅ complete |
| 1 | World Engine | ✅ core proven at 10k scale; slice **1.3** open, non-blocking |
| 2 | Typology Injector | ✅ complete — all 7 typologies + capstone |
| 3 | Rules Engine | ✅ complete (re-tuned twice in Phase 6) |
| 4 | Screening | ✅ complete; slice **4.1** open (re-scoped, low value) |
| 5 | Graph Analytics | ✅ complete |
| 6 | ML Tournament | ✅ complete — all 6 model families |
| 7 | Investigator Workbench | ✅ complete — 7.1–7.12 |
| 8 | Red Team co-evolution | ✅ complete — decay benchmark |
| 8.5 | Multi-bank experiment | ✅ complete — blind spot + co-operation prototype |
| 9 | Story Mode + launch | ✅ **complete — 9.1 Story Mode, 9.2 metrics, 9.3 whitepaper+docs/, 9.4–9.6 launch assets drafted. Recording and posting are Dhanush's, see §13** |

---

## 3. Environment — exact, verified

- **Python 3.14.3**, venv at `launderlab/.venv`
- Run everything as `.venv/Scripts/python -m ...` (Windows; Bash tool available via Git Bash)
- **GitHub CLI 2.96** at `C:\Program Files\GitHub CLI\gh.exe`, authenticated as `Dhanu2626`
- **Node v24.18** at `C:\Program Files\nodejs\`
- ⚠️ `node` and `gh` are often **not on PATH** — call them by full path.

**Dependencies** (`pyproject.toml`)
- Core: `duckdb`, `jellyfish` (fuzzy name matching), `networkx` (graph), `scikit-learn` (ML)
- `[dev]`: `pytest>=8`, `ruff>=0.5`
- `[api]`: `fastapi`, `uvicorn`, `httpx` — the workbench backend
- `[mcp]`: **`mcp>=1.28,<2`** — the cap is load-bearing, see §8
- `[deep]`: `torch` — LSTM + GraphSAGE only. **Install the CPU build**:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu` (~200MB vs ~2.5GB CUDA;
  these models are far too small to want a GPU).

**CI** (`.github/workflows/ci.yml`) — Python 3.12, installs `.[dev,api,mcp]` **plus CPU torch**,
runs `ruff`, then pytest **and fails if any test skips at all**. That guard exists because CI
silently ran 178 of 226 tests for eight days (§7, finding 8). With every extra installed there
is no legitimate reason to skip, so a skip now means a dependency stopped resolving.

**Commands**

```bash
.venv/Scripts/python -m pytest -q                    # full suite, ~5-9 min
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m launderlab                   # table counts
.venv/Scripts/python -m launderlab seed              # 25-customer demo world
.venv/Scripts/python -m launderlab statement A001    # render a bank statement
.venv/Scripts/python -m launderlab demo-world        # 1200 accts + 6 typologies + entities
                                                     # + media + detection + 50 cases (~21s)
.venv/Scripts/python -m launderlab charts            # KPIs + Phase 3/5/7 -> charts/results.html
                                                     # (honours LAUNDERLAB_DB)
.venv/Scripts/python -m launderlab media-experiment  # 7.12: does adverse media earn a weight?
.venv/Scripts/python -m launderlab redteam           # Phase 8 decay benchmark (~8 min)
.venv/Scripts/python -m launderlab multibank         # Phase 8.5 blind spot (~1 min)

LAUNDERLAB_DB=data/demo.duckdb \
    .venv/Scripts/python -m launderlab story         # 9.1 Story Mode -> charts/story.html
                                                     # (~1 min; reads LAUNDERLAB_DB)

.venv/Scripts/python -m launderlab metrics           # 9.2 the FCC operating KPIs (text)
.venv/Scripts/python -m launderlab publish           # 9.3 collect pages -> docs/ (files only)

LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m uvicorn \
    launderlab.workbench.api:app --port 8787         # workbench UI on that world
```

⚠️ **`.claude/launch.json` inside `launderlab/` is NOT picked up** by the browser preview tool —
the session root is `CareerForge`, whose `.claude/launch.json` belongs to RefundRadar. Start
uvicorn manually and open `http://127.0.0.1:8787/`.

⚠️ **DuckDB locks the file.** A running uvicorn holds a world open; a second process cannot
connect, and DuckDB refuses to `ATTACH` a file this process already has open. Close first.

⚠️ **Check the port before trusting what you see.** Stale uvicorn processes from earlier
sessions survive on 8787/8788 serving *old code against an old world*, and the page looks fine.
`netstat -ano | grep LISTENING | grep 87` before assuming the page is your build.

⚠️ **Do not run two heavy things at once.** Two concurrent full suites once took 72 minutes;
running the suite alongside `redteam` costs several minutes of CPU contention.

---

## 4. Architecture

```
src/launderlab/
  __main__.py           the CLI: seed, statement, demo-world, charts,
                        media-experiment, redteam, multibank
  db/ledger.py          connect(), bulk_insert(), bulk_update(), reverse_opening(),
                        account_opening_balance(), account_true_minimum(),
                        safe_debit_ceiling(), recompute_account_balances()
  db/schema.sql         ALL tables (ledger + ground truth + case management)
  db/watchlist.json     synthetic sanctions/PEP list (NOT real OFAC data)

  world/population.py   procedural customer profiles (193 first x 120 surnames)
  world/generate.py     transaction generation at any scale
  world/seed.py         original hand-crafted 25-customer cast (still used by tests)
  statement.py          renders any account as an HTML bank statement

  typology/             SIX injectors, each writing ground truth to scheme_labels:
                        structuring, mule_network, shell_company, round_tripping,
                        dormant_reactivation, high_risk_geography

  detect/rules.py       6 rules (Phase 3)          detect/scoring.py    scorer-only
  screening/matcher.py  Jaro-Winkler + Metaphone over aligned tokens (Phase 4)
  screening/inject.py   plants watchlist entities + adverse media
  screening/engine.py   both legs bank-wide; media_for_name() shared with MCP
  screening/scoring.py  scorer-only
  graph/build.py        rebuilds transfer graph (Phase 5); edges carry dr_txn/cr_txn
  graph/motifs.py       pass-through chains; Chain.hop_txns names the ledger rows
  graph/scoring.py      scorer-only
  ml/features.py        31 label-free behavioural features (Phase 6)
  ml/dataset.py         labels + stratified split + sequences + adjacency
  ml/models.py          gradient boosting, isolation forest, one-class SVM, autoencoder
  ml/deep.py            LSTM + GraphSAGE (plain PyTorch, hand-written)
  ml/tournament.py      leaderboard scored at an ALERT BUDGET, average precision not ROC

  workbench/risk.py     combines 4 layers -> one 0-100 score (7.1); TIER_ORDER,
                        BANDS, MIN_CASE_SCORE, corroboration_strength all live here
  workbench/evaluate.py scorer-only: does combining actually help? (answer: not for ranking)
  workbench/cases.py    case store, append-only audit trail (7.2)
  workbench/api.py      FastAPI (7.3) — queue, entity 360, lifecycle, /narrative
  workbench/narrative.py  SAR narrative draft — template, never an LLM (7.8)
  workbench/media_experiment.py  scorer-only: does adverse media earn a weight? (7.12: no)
  workbench/static/index.html    the whole UI: tiered queue (7.4), entity 360 (7.5),
                        link-graph SVG (7.6), disposition workflow (7.7), SAR draft (7.8)

  demo.py               `demo-world` — world + crime + entities + media + cases (7.9)
  viz.py                `charts` — SVG from the SCORERS; also render_redteam() and
                        render_multibank() for the two benchmark pages
  web.py                THE SHARED DESIGN SYSTEM (Phase 9.7) — tokens, page shell, nav,
                        components and the chart primitives. Five pages, one language.
                        Generated rather than hand-authored for the same reason every
                        figure is: a static site with results pasted in cannot be kept
                        honest. Motion is scoped to a `.js` class so nothing is hidden
                        when script is unavailable
  metrics.py            Phase 9.2 — the four FCC operating KPIs; conversion reported as
                        NOT MEASURABLE rather than 0% when nothing has been worked
  publish.py            Phase 9.3 — copies the generated pages into docs/ for GitHub
                        Pages. Writes files ONLY: never commits, pushes or changes settings
  story.py              Phase 9.1 — Story Mode: replays each scheme day by day against
                        the UNMODIFIED detectors (a `transactions` view shadowed via
                        search_path), measures detection latency + moved_before_alert
  redteam.py            Phase 8 — Knob/Genome per typology, run_decay_benchmark(), report()
  multibank.py          Phase 8.5 — 4 banks as SEPARATE DuckDB files, blind spot,
                        HMAC fingerprint co-operation prototype
  mcp_server.py         AML MCP server — 6 read-only tools, every call audited
```

**Database tables** (all in `db/schema.sql`)
- Ledger: `customers`, `accounts`, `transactions`
- Ground truth (**scorer-only**): `scheme_labels`, `entity_labels`, `media_labels`,
  `adverse_media`
- Case management: `cases`, `case_events` (append-only), `case_signals`
- MCP: `audit_log`

---

## 5. THE BOUNDARY RULE — the most important invariant

> **No detection code may read `scheme_labels`, `entity_labels` or `media_labels`.
> Only `*/scoring.py`, `workbench/evaluate.py`, `workbench/media_experiment.py` and `viz.py`
> may — and `viz.py` only *through* the scorers, never with its own query.**

If a detector could see the answer key, every precision and recall number this project has
produced would be meaningless — and it would fail silently. Enforced by **source-level regex
tests** in twelve places:

| Test | Guards |
|---|---|
| `test_detect_rules.py::test_rules_never_reference_scheme_labels` | Phase 3 |
| `test_screening_pipeline.py::test_engine_never_reads_ground_truth` | Phase 4 |
| `test_graph.py::test_graph_and_motifs_never_read_ground_truth` | Phase 5 |
| `test_ml.py::test_features_never_read_ground_truth` | Phase 6 |
| `test_workbench_risk.py::test_risk_module_never_reads_ground_truth` | 7.1 |
| `test_workbench_api.py::test_api_never_exposes_ground_truth` | 7.3 |
| `test_workbench_narrative.py::test_narrative_never_reads_ground_truth` | 7.8 |
| `test_mcp_server.py::test_server_never_reads_scheme_labels` | MCP |
| `test_mcp_server.py::test_server_exposes_no_generic_sql_tool` | MCP |
| `test_redteam.py::test_redteam_never_reads_ground_truth` | Phase 8 |
| `test_multibank.py::test_multibank_never_reads_ground_truth` | Phase 8.5 |
| `test_story.py::test_detection_comes_from_the_detectors_not_the_answer_key` | Phase 9.1 |
| `test_metrics.py::test_metrics_read_ground_truth_only_through_the_scorers` | Phase 9.2 |

**Never weaken these.** Two of them were not executing in CI for eight days and nobody noticed
(§7, finding 8) — which is exactly why the no-skips guard exists now.

**Four legitimate exceptions, each documented at its site:**
1. `ml/dataset.py` — supervised ML must train on labels, as a real bank trains on past
   confirmed SARs. The requirement becomes **no test-set leakage**, enforced by returning
   train/test as separate objects. The three unsupervised models never see a label.
2. Scorer modules (`*/scoring.py`, `evaluate.py`, `media_experiment.py`) — that is their job.
3. `redteam.py` knows which accounts it planted **because it planted them**, held in local
   memory in the same function call. It never looks them up in a ground-truth table, and never
   reads a rule's tuned constants.
4. `story.py` — narrating what really happened next to what detection said IS its job, so it
   reads `scheme_labels` in exactly one function. The invariant runs the **other** direction and
   has its own test: the *caught* side comes only from `rules.run_all()` and
   `motifs.find_chains()`. An account lit up for appearing in the answer key would animate a
   detection that never happened — the most flattering artefact this project could ship.

---

## 6. Phase-by-phase — what exists and what it proved

Full numbers live in `PROJECT.md`'s slice log. Summary:

**Phase 0 — Foundations.** DuckDB ledger, 25-customer seeded world, statement generator,
`ledger/FCC-PRIMER.md` mapping placement→layering→integration onto subsystems.

**Phase 1 — World Engine.** Procedural population (5 segments, lognormal income, 9 cities).
**10k customers × 30 days = 630,755 transactions in 31s.** `bulk_insert()` (temp CSV + DuckDB
COPY) after measuring `executemany` at **8,224s (2.3h)** for 200k rows vs **4.5s** — 1,900×.
*Open: slice 1.3 (weekday/weekend, holidays). Non-blocking; has blocked nothing in eight
phases, and is the only reason Phase 1's roadmap box is unchecked.*

**Phase 2 — Typology Injector.** All 7 typologies, each injecting into an *already generated*
history and recomputing downstream balances. Capstone proves all six compose on deliberately
overlapping accounts. Proof: 60 schemes, 414 labels, full reconciliation across 631,169 rows.

**Phase 3 — Rules Engine.** 6 tunable rules. Original proof: 93.3% recall, 100% precision.
⚠️ **That precision was later shown to be an artefact** (§7, finding 3). Two rules re-tuned;
`counterparty_concentration` is documented as producing genuine, unfixable false positives.
Current reproducible figures on the demo world: **86.1% recall at 65.3% precision**.

**Phase 4 — Screening.** Jaro-Winkler + Metaphone over aligned name tokens. **100% recall on
both legs; entity precision 75.0%, adverse media 15.8%.** Slice 4.2's controlled two-arm
experiment on name-pool width: **86.1% of false positives were collision density in the
generated data; 13.9% is irreducible name ambiguity.**
*Note: jellyfish has NO Double Metaphone — only `metaphone`, `soundex`, `nysiis`.*

**Phase 5 — Graph Analytics.** Rebuilds the internal transfer graph by pairing DR/CR legs on
the **reference number in the narration** (joining on timestamp+amount cross-pairs unrelated
payments). **15/15 mule networks reconstructed, 100% precision, 100% recall.**
**Headline: only 1 of 6 typologies is visible to a graph at all** — the other five have
counterparties outside the bank, leaving one leg and no edge. That is thesis #3 measured at
1-in-6, and the direct setup for Phase 8.5. *Fan-in/fan-out detectors were built and deleted —
0 hits at usable thresholds, 72/76 merchants when loosened.*

**Phase 6 — ML Tournament.** All six families on one leaderboard, scored at an **alert budget**
and reported as **average precision, not ROC-AUC** (ROC flatters everything at a 1.4% positive
rate). **Real result: they fail differently** — isolation forest caught shell companies 8/8 but
layering only 7/18; one-class SVM caught layering 18/18. A bank running one model is blind
where that model is weak, and only ground-truth-by-crime-type reveals it.

**Phase 7 — Investigator Workbench (7.1–7.12).**
- **7.1 risk aggregation** — measured that combining does **not** out-rank ML alone. Value is
  explainability and tiering, not accuracy. Reported rather than buried.
- **7.2 case store** — append-only audit trail; evidence snapshotted at open time.
- **7.3 FastAPI backend** — a transport, not a second implementation. 409 not 500.
- **7.4 tiered alert queue** — tiered by evidence, per 7.1's measurement.
- **7.5 entity 360** — click an alert, get the customer: KYC profile, whole-history activity
  totals, Phase 5 chains, full statement, above the audit trail.
- **7.6 link-graph view** — chains drawn as the path the money took, every node clickable,
  every hop traceable to its two ledger rows.
- **7.7 disposition workflow** — assign / note / close / reopen in the UI, every action named.
- **7.8 SAR narrative draft** — template, never an LLM.
- **7.9 `demo-world`** — one command from empty to a queue with real cases in it.
- **7.10 four-layer audit** — the workbench was combining two of its four layers.
- **7.11 pre-Phase-8 audit** — five claims that were not true.
- **7.12 adverse media** — measured as a scoring signal and **rejected**; see §8.

**Phase 8 — Red team co-evolution.** One adversary genome per typology mutating its own
injector parameters each generation it gets caught, frozen once a generation fully evades.
8 generations, 450 accounts, 10 schemes/typology:

| typology | gen0 → gen7 | convergence |
|---|---|---|
| shell_company | 70% → **0% by gen 2** | stable 0% after — confirms 6.2's "unfixable by threshold" under adversarial pressure |
| mule_network | 100% → **0% by gen 7** | the one typology *both* rules and the graph watch |
| structuring | 90% → 90% | **never fully evades**, even at ₹99,000 (₹1 under the reporting line) |
| round_tripping | 100% → 10% | **never fully evades**, even at hop_days 38 |
| dormant_reactivation | 40% → 20% | converged gen 2, but **12% mean recall after** — least stable |

**Headline: decay is not uniform.** Phase 3's single aggregate could never have shown that some
detectors collapse completely and others hold.

**Phase 8.5 — Multi-bank experiment.** The world split across 4 banks as **genuinely separate
DuckDB files**. Two arms: `naive` (chains placed without regard to banks) and `deliberate`
(consecutive hops always at different banks).

| view | naive | deliberate |
|---|---|---|
| pooled (hypothetical central view) | 100% | 100% |
| a single bank alone | **6%** | **0%** |
| privacy-preserving co-operation | **81%** | **69%** |
| individual mule accounts flagged locally | 75% | 77% |

**Headline: the blind spot is the NETWORK, not the account.** Banks flag three-quarters of the
mule accounts on their own books and reconstruct almost none of the chains — because an
account's whole history is at its own bank, but the second leg of a cross-bank transfer is not.
**And it does not take a sophisticated launderer**: deliberate spreading buys almost nothing
over naive placement, since seeing a chain needs two *consecutive* hops inside one bank and
those odds fall as 1/n².

---

## 7. The honesty thread — findings that overturned earlier results

**Preserve this pattern.** Each began as a flattering number or a claim nobody had checked.

1. **Phase 4 → 4.2.** 29.4% screening precision looked like proof of AML's false-positive
   crisis. Widening the name pool moved it to 75%. **86% of the headline was an artefact.**
2. **Phase 6.1.** Gradient boosting scored a perfect AP of 1.000. Cause: the legitimate world
   emitted **zero CASH and zero INT transactions**, so both channels existed only inside
   injected crime — the model learned "cash = crime".
3. **Phase 6.1 → Phase 3 collapse.** Fixing that broke the rules engine: `structuring_burst`
   went **0 → 24 false positives** on a clean world. **Phase 3's 100% precision had been a
   property of a world where nobody legitimately banked cash.**
4. **Phase 6.2.** Adding legitimate large payments **collapsed the unsupervised models** —
   one-class SVM 0.910 → 0.219. They had learned "anomalous = large", which only held while
   honest traffic had no upper tail.
5. **Phase 6.2.** `counterparty_concentration` measured as **unfixable**: shell schemes sit at
   6 payments / 50% concentration, *inside* the legitimate 5–9 / 51–63% range.
6. **Phase 7.1.** Fixed a bug in the project's own evaluator — recall divided by all dirty
   accounts while ranking a held-out slice, understating it ~3×.
7. **Phase 7.4.** The UI caught a bug **178 passing tests missed**: rule strength was
   `min(n,3)/3`, so a genuine structuring scheme (one rule) scored 11.7/100 and **fell below
   the queue cut-off, never reaching an analyst.** Every test asserted *relative* behaviour,
   which stayed true.
8. **Phase 7.5.** Same family, one slice later. The entity endpoint defaults to the latest 100
   transactions, so an account alerted for **89 cash deposits** rendered a statement starting a
   week after the account's own history did — **the evidence screen truncating the evidence.**
   Nothing failed; the API did exactly what it was asked.
9. **Phase 7.8.** Printing a SAR narrative showed a confirmed structuring scheme describing
   itself to a Financial Intelligence Unit as **"low band"**. Measured: all 50 cases were low
   or medium and the highest score in the bank was 43.5 — **`high` and `critical` were words
   describing nothing.** Bands re-derived from the signal algebra.
10. **Phase 7.10 — four instances of one root cause.** Wiring the two unused layers into the
    demo exposed that **screening was being discarded wholesale**: a screening-only case's
    ceiling was *exactly* the opening threshold, so only a perfect 1.000 name match ever
    reached an analyst. **14 of 15 planted entities never got there.** The test written to pin
    that fix immediately caught **7.4's bug living in the graph layer** (a 2-hop chain scored
    half). Root cause of all four: *a global threshold applied to a score whose scale depends
    on which layers happened to fire.*
11. **Phase 7.11 — CI was running 178 of 226 tests.** The workflow installed only `.[dev]`, so
    three `importorskip` modules skipped entirely — and a skipped *module* counts as **one**
    skip, so 48 missing tests hid behind the number 3. Among them **two of the boundary-rule
    enforcers**. Green CI was not saying what it appeared to say. Also found: no code in the
    repo could draw a chart while the quality bar demanded one per phase; PROJECT.md still
    advertised the artefact precision; the MCP audit decorator accepted keywords only.
12. **The no-skips guard immediately found a worse one.** `mcp` was pinned `>=1.28` with no
    ceiling; mcp 2.0.0 moved `mcp.server.fastmcp`, so a fresh install produced an MCP server
    **that could not start** — and the README's documented install was broken for anyone new.
    It worked locally only because this machine already had 1.28.1.
13. **Phase 7.12 — adverse media rejected on measurement.** Of 21 accounts it flags, 1 is
    laundering, and the set of laundering accounts **only** media reaches is **empty**. No
    weighting can add a true positive; every weighting tried displaced real cases. Also found:
    `aggregate()` had **no tie-break**, and 45 accounts tie at exactly 21.00 with the budget cut
    inside that cluster — so which 24 of 45 an analyst worked was decided by dict insertion
    order, and it moved the experiment's own baseline between identical runs.
14. **Phase 8.5 — a backwards metric.** Scoring co-operation on cross-boundary recoveries
    *alone* made a chain deliberately spread across banks look **better** covered than a
    careless one. A backwards ordering is the cheapest possible signal a metric is wrong.
15. **Pre-Phase-9 audit — six defects in the two newest modules.** Two genuine correctness
    bugs in `PrivacyNotes` (counting intra-bank hops as needing cross-bank co-operation), and
    **both survived because the report had stopped printing them.** A number nobody looks at is
    a number nobody checks. Plus dead code, an unused `generation` parameter advertising
    behaviour that did not exist, and a silently dropped disclosure-volume line.

16. **Phase 9.1 — every published detection number was scored against the finished world.**
    Recall, precision, the decay benchmark, the blind spot: all graded once, at the end, over
    all 39 days. That silently assumes a bank may wait until the crime is over before deciding
    it happened. Replaying day by day showed **latency and usefulness are nearly inverted
    orderings**: `round_tripping` is caught in a median 4 days with **100% of its value already
    moved**, because `round_trip` needs the return leg before it can fire — structurally
    incapable of alerting while anything is stoppable, and no threshold fixes it. `structuring`
    is the *slowest* to detect (9 days) and the best on the chart that matters (53% still to
    come). "Caught" was never one property.

17. **Phase 9.2 — `charts` published "detection rate 0.0%".** It called `connect()` bare while
    `story` and `metrics` honoured `LAUNDERLAB_DB`, so it drew against the 25-customer seed
    ledger, which has no crime in it. Arithmetically true, and a statement about nothing: 0 of 0
    schemes caught reads as a totally failed detection stack. Found by publishing the page and
    then reading it. Root cause was four call sites each writing their own env lookup, one of
    which forgot — there is one `ledger.connect_configured()` now. The first guard only covered
    the KPI section and left the Phase 3 chart still publishing "0.0% recall across 0 schemes",
    so the guard moved to the single point every ground-truth chart passes through — and the
    project's own boundary test caught that guard doing its own `SELECT scheme_labels`.

**The pattern, named:** most of these surfaced by *rendering a number where a person had to
read it next to a decision*. Detection metrics grade a detector against ground truth; nothing
grades whether its output is usable. Finding 16 extends it: a metric can also be graded on the
wrong *axis* entirely, and be perfectly measured on that one.

---

## 8. Load-bearing design decisions (do not silently reverse)

**Detection & scoring**
- **Edge reconstruction joins on the narration reference number**, not (timestamp, amount) —
  the latter cross-pairs unrelated coincident transfers.
- **Chains are suffix-collapsed** — growing from every edge rediscovers a long chain from its
  2nd and 3rd accounts; an investigator wants the path once.
- **Name matching uses token alignment, NOT whole-string Jaro-Winkler** — JW's prefix bonus
  scored "Suresh Kumar" vs "Suresh Gupta" at 0.900.
- **`ml/tournament.py` scores at an ALERT BUDGET** and reports **average precision, not
  ROC-AUC**.
- **Risk score is a weighted sum, not a meta-model** — "the model said so" is not a SAR.
- **`risk.MIN_CASE_SCORE` (17.5) is DERIVED, not chosen**: above the model's 15.0 ceiling (a
  model-only alert has no reason to give an analyst) and at or below the faintest thing any
  control will assert (screening's 0.88 threshold × 0.20 = 17.6). **A test pins that window —
  if you change any weight, that test fails on purpose.** Re-derive; do not widen it.
- **Evidence strength uses one shared diminishing-returns curve** (`corroboration_strength`,
  `1 − 0.4ⁿ`) for rules AND graph hops. Linear-in-count made the minimum reportable case score
  a fraction of a signal — the 7.4 bug, found twice in two different layers.
- **Risk bands describe corroboration, not a percentage** (60/40/18/0). Derived from the signal
  algebra; do not re-fit them to one world's histogram.
- **`aggregate()` breaks ties on account id.** Not cosmetic: 45 accounts tie at 21.00 and the
  budget cut falls inside that cluster.
- **`risk.TIER_ORDER` is canonical**, ordered by *how specific a reason the analyst gets*
  (graph names a path, a rule names a scenario, screening names a person, a model names
  nothing) — NOT by 7.1's standalone precisions, which measure each layer as a lone ranker and
  filed sanctions hits under a "model-ranked" heading.
- **Adverse media is surfaced, never scored — FINAL, confirmed by Dhanush 2026-07-30.** Not a
  provisional default. `risk.collect(media_mode="off")` is production; `"separate"` and
  `"folded"` exist for the experiment only. Do not give it a weight without re-running
  `media-experiment` and finding a **non-empty unique-reach set** — and even then that is new
  evidence for a new decision, not a quiet reversal.

**Workbench**
- **`case_events` is append-only**; reopening clears the disposition but never its history.
- **Case evidence is snapshotted at open time** — detectors get retuned.
- **API lifecycle violations return 409, not 500**; every mutation requires a named actor.
- **The queue is tiered by evidence, not sorted by the blended score.**
- **Account totals on the entity screen are computed in SQL over the whole history**, never
  summed from the transaction window the page holds. The UI requests the endpoint's maximum
  window for the same reason.
- **Chains carry the ledger rows they were built from** (`Chain.hop_txns`). A chain nobody can
  trace to transactions is an assertion, not evidence.
- **The SAR narrative is a template, never a language model.** Every figure is asserted to a
  regulator; a generated sentence that rounds a number is a false statement in a filing.
- **The narrative never asserts laundering occurred** — "consistent with", never "the customer
  laundered". The bank reports suspicion; it is not the finder of fact.
- **The disposition list is served by the API, never hardcoded in the UI**, and a test asserts
  no disposition string appears in the page.
- **The UI is one self-contained HTML file — settled 2026-07-30, do not reopen.** No bundler,
  no `node_modules`, no extra CI stage. The API is the contract regardless.

**Benchmarks**
- **The demo's ML scores are unsupervised and budgeted** (isolation forest, top 100). One world
  means a supervised model would score the accounts it was fitted on.
- **`redteam` knob bounds are justified by PUBLIC facts**, never by the rule they evade. A test
  asserts no bound equals the corresponding rule's tuned threshold.
- **`high_risk_geography` is excluded from the red team** — its only real evasion move is
  categorical (an unlisted jurisdiction), and inventing a fake continuous knob would be
  dishonest.
- **Each bank in Phase 8.5 gets a SEPARATE DuckDB file, never a `WHERE` clause.** A filter
  would need every detector to remember to honour it; one that forgot would silently give a
  bank sight of another bank's rows and inflate the number the phase exists to measure.
- **Banks publish `HMAC(secret, reference)`, never a bare hash** — a plain SHA of a short
  numeric reference is trivially brute-forced back.
- **`Fingerprint`'s field list IS the privacy boundary** — a test asserts it holds no account
  id, customer name or balance.
- **`mcp` is capped `<2`.** `mcp_server.py` uses the 1.x `mcp.server.fastmcp` path. Lift the cap
  only when the code is migrated.
- **CI fails on ANY skipped test.** Do not relax this to make a dependency problem go away.

**Metrics and publishing (9.2–9.3)**
- **Observed and hypothetical conversion never share a field.** `observed_conversion` is `None`
  when nothing has been worked, never `0.0` — "unreviewed" and "reviewed and cleared" are
  opposite facts. Do not "fix" the None away.
- **`ceiling_conversion` is deliberately identical to `queue_precision`.** The equality IS the
  finding: the industry's headline analyst KPI reduces, at best, to a property of the queue.
  Keeping one property would hide it.
- **`reviews_per_true_find` needs no assumption; `review_hours` is one and says so everywhere.**
  Never convert to money — that needs a loaded salary figure this project cannot source.
- **Every entry point opens the world via `ledger.connect_configured()`.** Four call sites each
  wrote their own `LAUNDERLAB_DB` lookup and `charts` forgot, publishing a 0.0% detection rate
  against a crime-free ledger (§7, finding 17). One lookup now; a test pins it.
- **`render()` refuses to draw anything when the ledger has no schemes.** A rate over an empty
  denominator is not a measurement. The guard sits at the one point all four ground-truth
  charts pass through, and takes its count from the *scorer*, never its own label query.
- **`publish.py` writes files and nothing else.** No commit, no push, no repo settings — a test
  asserts no `subprocess`/`git`/network reference. Going public stays a human decision.
- **`docs/index.html` is the landing page; the charts page publishes as `charts.html`.** Both
  wanted `index.html` and one silently destroyed the other, with a working link to the wrong
  page.

**The published site (9.7)**
- **`web.py` owns the design language; no page styles itself.** Five pages that look like
  four different documents is the failure this replaced.
- **`docs/index.html` is the landing page — no generated page may publish as `index.html`.**
  Both claiming it silently destroyed one artifact, with a working link to the wrong page.
- **Every link in the landing page BODY is gated on the target existing.** The persistent nav
  is deliberately constant across pages (it is the product's spine); an incomplete build is
  reported loudly by the CLI instead.
- **Reveal-on-scroll is scoped to `.js`.** An unconditional `opacity:0` made a scroll
  animation load-bearing for whether the page had any content at all.
- **The count-up animation restores the exact original string.** It replays toward a value
  already in the DOM and can never round a published figure into a different one.

**Story Mode (9.1)**
- **The replay truncates with a VIEW, never a second copy of a rule.** `transactions` is
  shadowed by `replay.transactions` through `search_path='replay,main'`, so the SQL every rule
  already contains does the filtering. A day-aware reimplementation could drift from the rule
  actually being graded. `search_path` is restored in a `finally` — leaving it set would give
  every later query in the process a quietly truncated world.
- **A test asserts the row count THROUGH the view, not its effect.** If shadowing ever stopped
  working the detectors would run against the full world every day and report everything caught
  on day one — flattering, and nothing would fail.
- **`moved_before_alert` ships wherever latency does, and a test enforces it.** Latency alone
  says `round_tripping` is caught in 4 days; it omits that 100% of the money is gone. Never
  publish one without the other.
- **"Never caught" is reported as never, not as a 0-day median.** They are opposite findings.
- **Story Mode is a static self-contained page, not an API view.** Its audience is explicitly
  someone who will never run a server; the workbench already serves the analyst.
- **Latency covers rules + graph only.** Screening answers an identity question with no firing
  day; ML emits a ranking, not an event, and re-fitting it 39 times would measure the model's
  own instability. Phase 8 drew the same line.

---

## 9. Known open items — all deliberate, none blocking

| Item | Status |
|---|---|
| **1.3 world realism** | Weekday/weekend variation, holidays. Open since 2026-07-26; has blocked nothing across eight phases. The only reason Phase 1's box is unchecked |
| **4.1 secondary identifiers** | DOB/nationality disambiguation. Re-scoped by 4.2 to a realism item, not a precision fix — exact-name FPs went to 0 on their own |
| **The model tier cannot fill** | By arithmetic and deliberately: ml weight 0.15 → a model-only case tops out at 15.0, below the 17.5 threshold, because an alert with no explainable reason should not open a case. The UI says so in the empty tier. **Phase 8 made this concrete rather than hypothetical**: mule_network went to 0% recall and shell_company to 0% against a real adversary — when rules and graph go quiet, the model is the only layer left. Re-weighting is now an overdue decision |
| **Sanctions lose the shared alert budget** | Screening-only hits score 17.6–19.7, lowest of any control, so under one budget every behavioural case outranks them — 42 of 92 eligible accounts did not fit. Real banks queue screening separately under its own obligation clock; a per-tier budget in `open_from_queue` would model that |
| **Single-rule cases are all tied at 21.00** | A 27-deposit structuring scheme and an 89-deposit one are indistinguishable to the queue. Ties now break on account id so the queue is at least *reproducible*, but giving rules a magnitude-aware confidence is a real scoring change needing its own measurement slice |
| **Only graph can cite its own rows** | Rules emit a reason string, screening answers an identity question, ML emits a score — none records *which* transactions made it fire, so the SAR annex is ranked by value and says so |
| **Statement ceiling** | The entity screen requests 500 transactions, the endpoint's max. A busier account still truncates — it says so in a caption. Paginate when a world produces one |
| **Phase 8 is one seed** | Seed 41, 8 generations. Convergence generations are a real measured example, not a population statistic. Average over seeds before quoting a specific number as more |
| **Phase 8 measured rules + graph only** | Whether a *trained* model decays faster or slower against the same adversary is a real, different question |
| **Phase 8.5 co-operation is a prototype, not a protocol proposal** | The coordinator still learns the inter-bank graph's shape; and a flagged account's *entire* payment history is fingerprinted, not just its suspicious legs. Making those private (secure set intersection, differential privacy on volumes) is where BIS Project Aurora spends most of its effort |
| **Phase 8.5 used one seed and exactly 4 banks** | The 1/n² mechanism predicts the blind spot deepens with more banks; sweeping `n_banks` would turn a stated mechanism into a measured curve. Cheap, and would strengthen the whitepaper |
| **Phase 8.5 measured mule chains only** | The other five typologies leave no internal edge even inside ONE bank (Phase 5), so splitting into four changes nothing for them. Stated so nobody re-measures it expecting a result |
| `counterparty_concentration` | Knowingly produces false positives; measured as unfixable by threshold |
| Small structuring | Documented blind spot — indistinguishable from a shop banking takings |
| `dormant_reactivation` recall | 60% (9/15) — the injector's gap parameter sometimes lands too close to normal weekly cadence |
| Watchlist | **Synthetic**, not real OFAC/UN data. Swap via `LAUNDERLAB_WATCHLIST` |
| Test suite runtime | ~5–9 min (274 tests). `test_redteam.py`'s live run and `test_demo.py` are slowest. Do not run two heavy things concurrently |

**Settled — do not reopen without new evidence:** the React question (single page, 2026-07-30)
and adverse media (context on Entity-360, weight 0.0, 2026-07-30).

---

## 10. Working discipline — non-negotiable

From `PROJECT.md`'s quality bar:
- **`main` never breaks** — every slice runs end-to-end before commit
- **pytest + ruff green before every commit**; CI on every push, **always verified after**
- **Every phase ships a visual artifact**, never just tables
- **Blue-team code never reads ground truth**

**Rituals**
- `"start day"` → read `PROJECT.md` + last Field Notes entry → agree ONE slice → build it
- `"close day"` → commit, push, append three insights to `ledger/FIELD-NOTES.md`
  (🏦 FCC domain · 🔧 engineering · 🎯 interview line) and one line to `ledger/INTERVIEW-AMMO.md`
- New jargon → `ledger/GLOSSARY.md`
- Phase completion → resume bullet into `job hunt/db/profile.md` + LinkedIn post

**Method that produced everything good here:** measure, don't guess. Before publishing a
number, ask whether the synthetic data manufactured it. When a result looks perfect, hunt the
leak. Report negative results. **Render numbers where a human has to read them next to a
decision** — that is what caught most of §7.

---

## 11. Dhanush's preferences

- **Explain everything in plain, beginner-level language.** He is a domain expert in FinCrime,
  not a software engineer. Give a plain-English summary of what changed and why *in addition
  to* the technical detail. Define terms in the same sentence; spell out acronyms every time.
- **He wants genuine reasoning and honest pushback, not agreement.** He has explicitly thanked
  a "why not this" answer. If a suggestion has a real tradeoff, say so with reasons — a
  comparison table lands well. Don't soften into "both are fine".
- He proposes architecture ideas himself and they are usually sound — validate against what is
  already planned before agreeing or extending.
- **He asks "is anything left?" before moving on.** Take it literally and audit rather than
  answering from memory; that habit has found real defects every single time.

---

## 12. Canonical docs

| File | Contents |
|---|---|
| `PROJECT.md` | Roadmap + **slice log** (every slice, dated, with real numbers) + rituals + pending |
| `ledger/FIELD-NOTES.md` | Every day's 3 insights — the learning record |
| `ledger/INTERVIEW-AMMO.md` | ~65 STAR-ready interview sentences harvested from real work |
| `ledger/GLOSSARY.md` | ~50 FCC terms decoded |
| `ledger/FCC-PRIMER.md` | The three laundering stages mapped to subsystems |
| `ledger/PITCH.md` | How to explain the project to any audience |
| `README.md` | **The whitepaper** — abstract, three research questions answered, per-phase results with caveats, the honesty thread, explicit limitations |
| `ledger/DEMO-SCRIPT.md` | 3-minute demo video script + shot list (**recording is Dhanush's**) |
| `ledger/LAUNCH-POST.md` | Two LinkedIn drafts + pre-post checklist (**posting is Dhanush's**) |
| `../LAUNDERLAB-PLAN.md` | The 18-week master plan, research thesis, all phases |
| `../job hunt/db/profile.md` | LaunderLab resume bullets, Tracks 1/2/4 |

Generated artifacts (gitignored): `charts/*.html`, `data/demo.duckdb`.
**Committed** artifacts: `docs/*.html` — the published copies, written by
`python -m launderlab publish`. Regenerate and re-publish whenever a number changes, or the
public pages silently drift from the measured ones.

---

## 13. Where this stands, and what is left

**Every phase is complete.** 0 through 9. The remaining items are things only Dhanush can do,
plus a short list of deliberate deferrals that have never blocked anything.

### Handed over — these need a human, not a session

1. **Enable GitHub Pages.** Repo → Settings → Pages → Deploy from a branch → `main` / `docs`.
   The pages are committed and the landing page links resolve; nothing is public until this is
   flipped. **Verify the URL in a private window before the launch post goes out** — the
   README already links to `https://dhanu2626.github.io/launderlab/`, so that link is dead
   until Pages is on.
2. **Record the demo video.** Script, timings and shot list are in `ledger/DEMO-SCRIPT.md`. The
   slider drag at 1:25 is the shot that carries it.
3. **Post the launch.** Two drafts in `ledger/LAUNCH-POST.md`; option A is the stronger one.
   Read it in his own voice first — he has to defend every sentence in an interview.
4. **Put the resume bullets on the actual resume.** They are staged in
   `../job hunt/db/profile.md` under project 5, split by track. Not yet on the PDF.

### Still deliberately open — none of it blocking

Everything in §9 stands. The two worth restating:

- **The model-tier weighting decision (§9).** Phase 8 showed rules and graph going to 0% recall
  against a real adversary; at current weights a model-only alert still cannot open a case. It
  deserves its own measurement slice, the way 7.10 and 7.12 got theirs — not a rider on another
  slice. This is the most substantive open question in the project.
- **Slice 1.3** (weekday/weekend, holidays) and **4.1** (secondary identifiers). Open since
  Phase 1 and 4 respectively, and have blocked nothing across nine phases.

### If the project continues

The cheapest real extensions, in order of value per hour:

1. **Sweep `n_banks` in Phase 8.5.** The 1/n² mechanism predicts the blind spot deepens with
   more banks; sweeping it turns a stated mechanism into a measured curve. Cheap, and it
   strengthens the whitepaper's headline chart.
2. **Average Phase 8 over several seeds.** The convergence generations are one seed's
   realisation. A distribution would let the decay finding carry a publishable claim rather
   than a portfolio one.
3. **Measure whether a *trained* model decays faster or slower** than static thresholds against
   the same adversary. Phase 8 measured rules and graph only, and the module docstring says so.
4. **Work some cases to disposition** so alert-to-SAR conversion becomes measurable at all —
   right now `metrics` correctly reports it as unmeasurable, and it will keep doing so until a
   human adjudicates a queue.

**To see the whole thing working:**
```
.venv/Scripts/python -m launderlab demo-world
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m launderlab metrics
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m launderlab charts
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m launderlab story
.venv/Scripts/python -m launderlab multibank
.venv/Scripts/python -m launderlab redteam
.venv/Scripts/python -m launderlab publish
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m uvicorn launderlab.workbench.api:app --port 8787
```

**Session discipline, unchanged:** agree ONE slice → build → test → lint → real-scale proof →
docs → commit → push → **verify CI** → three Field Notes insights.
