# LaunderLab — project handoff

**Written 2026-07-29, updated 2026-07-30 (Phase 7 complete) for a Claude session that has
none of the previous conversation.**
Everything needed to continue is here or is pointed at from here. Read this file first,
then `PROJECT.md`, then the last entry in `ledger/FIELD-NOTES.md`.

---

## 1. Orientation — what this is

**LaunderLab is an adversarial simulation range for anti-money-laundering (AML) detection.**
A synthetic bank, an injector that hides real laundering typologies inside it, a four-layer
detection stack that tries to catch them, and an investigator workbench where a human works
the resulting alerts. Because the injector records ground truth, every detector can be scored
on real precision and recall — something no actual bank can do with production data.

Built by **Dhanush Jangadi** (Hyderabad, FinCrime/AML fresh grad) as his flagship portfolio
project. Claude is the build partner. It is a career asset first and a research tool second:
the point is that he can walk into a Financial Crime Analyst interview having built every box
in the AML value chain.

**The differentiating property of this project is intellectual honesty.** Repeatedly, a
flattering result turned out to be an artefact of the synthetic data, and each time it was
measured, corrected and *written down* rather than quietly kept. That pattern is the most
valuable thing here — preserve it. Details in §7.

- **Repo:** `C:\Users\DELL\OneDrive\Documents\CareerForge\launderlab`
- **GitHub:** https://github.com/Dhanu2626/launderlab (public, branch `main`)
- **Master plan:** `../LAUNDERLAB-PLAN.md` (in the CareerForge parent folder)

---

## 2. Current state — verified 2026-07-30

| | |
|---|---|
| Latest commit | `f40ae75` — "Pre-Phase-8 audit: five claims that were not true" |
| Working tree | clean, in sync with `origin/main` |
| Tests | **242 passing**, zero skips (~9 min) |
| Lint | `ruff` clean |
| CI | GitHub Actions green on every push — **and since 2026-07-30 it actually runs everything**: installs `[dev,api,mcp]` + CPU torch and **fails if any test skips**. Before that it installed only `[dev]` and ran 178 of 226 tests |
| Phases complete | 0, 2, 3, 4, 5, 6, **7** fully; 1 core (polish deferred) |

**Phase status at a glance**

| Phase | Name | Status |
|---|---|---|
| 0 | Foundations | ✅ complete |
| 1 | World Engine | ✅ core proven at 10k scale; slice **1.3** (realism polish) open, non-blocking |
| 2 | Typology Injector | ✅ complete — all 7 typologies + capstone |
| 3 | Rules Engine | ✅ complete (re-tuned twice in Phase 6) |
| 4 | Screening | ✅ complete; slice **4.1** open (re-scoped, low value) |
| 5 | Graph Analytics | ✅ complete |
| 6 | ML Tournament | ✅ complete — all 6 model families |
| 7 | Investigator Workbench | ✅ complete — 7.1–7.12, queue → entity 360 → link graph → disposition → SAR draft, all four layers reaching an analyst |
| 8 | Red Team co-evolution | ⬜ **not started — this is next** |
| 8.5 | Multi-bank experiment | ⬜ not started |
| 9 | Story Mode + launch | ⬜ not started |

---

## 3. Environment — exact, verified

- **Python 3.14.3**, venv at `launderlab/.venv`
- Run anything as `.venv/Scripts/python -m ...` (Windows paths; Bash tool available via Git Bash)
- **Node v24.18** at `C:\Program Files\nodejs\`
- **GitHub CLI 2.96** at `C:\Program Files\GitHub CLI\gh.exe`, authenticated as `Dhanu2626`
- ⚠️ `node` and `gh` are often **not on PATH** in a session — call them by full path.

**Dependencies** (`pyproject.toml`)
- Core: `duckdb`, `jellyfish` (fuzzy name matching), `networkx` (graph), `scikit-learn` (ML)
- `[dev]`: `pytest`, `ruff`
- `[mcp]`: `mcp` — the AML MCP server
- `[api]`: `fastapi`, `uvicorn`, `httpx` — the workbench backend
- `[deep]`: `torch` — LSTM + GraphSAGE only. **Install the CPU build**:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu` (~200MB vs ~2.5GB CUDA;
  these models are far too small to want a GPU). Tests skip cleanly if absent.

**Commands**

```bash
.venv/Scripts/python -m pytest -q                      # full suite (~3-9 min)
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m launderlab seed                # 25-customer demo world
.venv/Scripts/python -m launderlab statement A001      # render a bank statement
.venv/Scripts/python -m launderlab demo-world          # 1200 accounts + all 6 typologies
                                                       # + entities/media + detection
                                                       # + 50 open cases (~21s)
.venv/Scripts/python -m launderlab charts              # redraw the measured-results charts
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m uvicorn \
    launderlab.workbench.api:app --port 8787           # workbench UI on that world
LAUNDERLAB_DB=<path> ... # point any of the above at a specific world
```

⚠️ **`.claude/launch.json` in `launderlab/` is NOT picked up** by the browser preview tool —
the session root is `CareerForge`, whose `.claude/launch.json` belongs to RefundRadar. Start
uvicorn manually and open `http://127.0.0.1:8787/` directly.

⚠️ **DuckDB locks the file.** A running uvicorn holds the world open; a second process cannot
connect. Stop the server before inspecting the same `.duckdb` from a script.

⚠️ **Check the port before trusting what you see.** Stale uvicorn processes from earlier
sessions survive on 8787/8788 serving *old code against an old world*, and the page looks
fine. `netstat -ano | grep LISTENING | grep 87` before assuming the page is your build.

---

## 4. Architecture

```
src/launderlab/
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

  detect/rules.py       6 rules (Phase 3)      detect/scoring.py   scorer-only
  screening/matcher.py  Jaro-Winkler+Metaphone (Phase 4)
  screening/inject.py   plants watchlist entities + adverse media
  screening/engine.py   both legs, bank-wide   screening/scoring.py scorer-only
  graph/build.py        rebuilds transfer graph (Phase 5); edges carry dr_txn/cr_txn
  graph/motifs.py       pass-through chain detection; Chain.hop_txns names the rows
                        graph/scoring.py scorer-only
  ml/features.py        31 label-free features (Phase 6)
  ml/dataset.py         labels + stratified split + sequences + adjacency
  ml/models.py          gradient boosting, isolation forest, one-class SVM, autoencoder
  ml/deep.py            LSTM + GraphSAGE (plain PyTorch)
  ml/tournament.py      leaderboard scored at an ALERT BUDGET

  workbench/risk.py     combines all 4 layers -> one 0-100 score (Phase 7.1)
  workbench/evaluate.py scorer-only: does combining actually help?
  workbench/cases.py    case store — the audit trail (7.2)
  workbench/api.py      FastAPI (7.3) — incl. GET /cases/{id}/narrative
  workbench/narrative.py  SAR narrative draft, template not LLM (7.8)
  workbench/media_experiment.py  scorer-only: does adverse media earn a weight? (7.12 - no)
  viz.py                `python -m launderlab charts` - SVG charts from the SCORERS
  workbench/static/index.html   the whole UI: tiered queue (7.4), entity 360 (7.5),
                        link-graph SVG (7.6), disposition workflow (7.7), SAR draft (7.8)
  demo.py               `python -m launderlab demo-world` — world + crime + cases (7.9)
  viz.py                `python -m launderlab charts` — SVG charts from the SCORERS (7.11)

  mcp_server.py         AML MCP server — 6 read-only tools, every call audited
```

**Database tables** (all in `db/schema.sql`)
- Ledger: `customers`, `accounts`, `transactions`
- Ground truth (**scorer-only**): `scheme_labels`, `entity_labels`, `media_labels`, `adverse_media`
- Case management: `cases`, `case_events` (append-only), `case_signals`
- MCP: `audit_log`

---

## 5. THE BOUNDARY RULE — most important invariant in the project

> **No detection code may read `scheme_labels`, `entity_labels` or `media_labels`.
> Only `*/scoring.py` and `workbench/evaluate.py` may.**

If a detector could see the answer key, every precision and recall number the project has
produced would be meaningless — and it would fail silently. This is enforced by **source-level
regex tests** in `test_detect_rules.py`, `test_screening_pipeline.py`, `test_graph.py`,
`test_ml.py`, `test_mcp_server.py`, `test_workbench_api.py` and `test_workbench_risk.py`.
**Never weaken these.**

**One legitimate exception, documented in `ml/dataset.py`:** supervised ML must train on
labels — a real bank trains on past confirmed SARs. The requirement there becomes **no
test-set leakage**, enforced by returning train/test as separate objects. The three
unsupervised models never see a label at all.

---

## 6. Phase-by-phase — what exists and what it proved

Full detail lives in `PROJECT.md`'s **slice log** (every slice, dated, with numbers). Summary:

**Phase 0 — Foundations.** DuckDB ledger, 25-customer seeded world, statement generator,
`ledger/FCC-PRIMER.md` mapping placement→layering→integration onto subsystems.

**Phase 1 — World Engine.** Procedural population (5 segments, lognormal income, 9 cities);
transaction generation. **10k customers × 30 days = 630,755 transactions in 31s.**
`bulk_insert()` (temp CSV + DuckDB COPY) after measuring `executemany` took **8,224s (2.3h)**
for 200k rows vs **4.5s** — 1,900x.
*Open: slice 1.3 — weekday/weekend variation, holidays. Non-blocking.*

**Phase 2 — Typology Injector.** All 7 typologies, each injecting into an *already-generated*
history and recomputing downstream balances. Capstone test proves all six compose on
overlapping accounts. Real proof: 60 schemes, 414 labels, full-ledger reconciliation across
631,169 transactions.

**Phase 3 — Rules Engine.** 6 tunable rules. Original proof: **93.3% recall, 100% precision.**
⚠️ **That precision was later shown to be an artefact** — see Phase 6. Two rules were re-tuned
and one (`counterparty_concentration`) is now documented as producing genuine false positives.

**Phase 4 — Screening.** Jaro-Winkler + Metaphone over aligned name tokens.
**100% recall; entity precision 75.0%, adverse media 15.8%.**
Slice 4.2 ran a controlled two-arm experiment on name-pool width: **86.1% of false positives
were collision density in the generated data; 13.9% is irreducible name ambiguity.**
*Note: jellyfish has NO Double Metaphone — only `metaphone`, `soundex`, `nysiis`.*

**Phase 5 — Graph Analytics.** Rebuilds the internal transfer graph (pairs DR/CR legs by the
**reference number in the narration** — joining on timestamp+amount cross-pairs unrelated
payments). **15/15 mule networks reconstructed, 100% precision, 100% recall.**
**Headline finding: only 1 of 6 typologies is visible to a graph at all** — the other five have
counterparties outside the bank, leaving one leg and no edge. That is the cross-bank blind spot
(research thesis #3) measured as 1-in-6. *Fan-in/fan-out detectors were built and deleted —
measured 0 hits at usable thresholds, 72/76 merchants when loosened.*

**Phase 6 — ML Tournament.** All six families. Latest leaderboard (1200-account world):
gradient boosting 0.983 · GraphSAGE 0.885 · autoencoder 0.537 · LSTM 0.428 ·
isolation forest 0.266 · one-class SVM 0.234.
**Real result: they fail differently** — isolation forest caught shell companies 8/8 but
layering only 7/18; one-class SVM caught layering 18/18. A bank running one model is blind
where that model is weak, and only ground-truth-by-crime-type reveals it.

**Phase 7 — Workbench (half done).**
- 7.1 risk aggregation — **measured that combining does NOT out-rank ML alone** (worse at
  budget 25, because screening dilutes). Value is explainability and tiering, not accuracy.
- 7.2 case store — append-only audit trail, evidence snapshotted at open time.
- 7.3 FastAPI backend.
- 7.4 tiered alert queue UI.
- 7.5 entity 360 screen — click an alert, get the customer: KYC profile, whole-history
  activity totals, Phase 5 chains, full statement, above the audit trail.

---

## 7. The honesty thread — findings that overturned earlier results

**Preserve this pattern.** Each of these began as a flattering number.

1. **Phase 4 → 4.2.** 29.4% screening precision looked like proof of AML's false-positive
   crisis. Testing whether the *data* had manufactured it: widening the name pool moved
   precision to 75%. **86% of the headline was an artefact.**
2. **Phase 6.1.** Gradient boosting scored a perfect AP of 1.000. Cause: the legitimate world
   emitted **zero CASH and zero INT transactions**, so both channels existed only inside
   injected crime — the model learned "cash = crime".
3. **Phase 6.1 → Phase 3 collapse.** Fixing that broke the rules engine: `structuring_burst`
   went **0 → 24 false positives** on a clean world. **Phase 3's 100% precision had been a
   property of a world where nobody legitimately banked cash.**
4. **Phase 6.2.** Adding legitimate large payments **collapsed the unsupervised models** —
   one-class SVM 0.910 → 0.219. They had learned "anomalous = large", which only held while
   honest traffic had no upper tail. Real banking has an enormous one.
5. **Phase 6.2.** `counterparty_concentration` measured as **unfixable**: shell schemes sit at
   6 payments/50% concentration, *inside* the legitimate 5–9/51–63% range.
6. **Phase 7.1.** Fixed a bug in the project's own evaluator — recall divided by all dirty
   accounts while ranking a held-out slice, understating it ~3x.
7. **Phase 7.4.** The UI caught a bug **178 passing tests missed**: rule strength was
   `min(n,3)/3`, so a genuine structuring scheme (one rule) scored 11.7/100 and **fell below
   the queue cut-off, never reaching an analyst.** Tests all asserted *relative* behaviour,
   which stayed true. Fixed with a diminishing-returns curve.
8. **Phase 7.5.** Same family again, one slice later. The entity endpoint defaults to the
   latest 100 transactions, so an account alerted for **89 cash deposits** rendered a
   statement starting a week after the account's own history did — **the evidence screen was
   truncating the evidence**, and nothing failed because the API did exactly what it was
   asked. Truncation is invisible by construction: it looks like a shorter list.
9. **Phase 7.8.** Printing the first SAR narrative showed a confirmed structuring scheme (50
   cash deposits, Rs 33,43,000) describing itself to an FIU as **"low band"**. Measured: all
   50 cases in the bank were low or medium and the top score anywhere was **43.5** — `high`
   and `critical` described nothing reachable, because the thresholds assumed a 100 that
   needs all four layers firing at once. Re-derived from the signal algebra to 60/40/18/0.
   **Three phases running, the bug was found by rendering a number for a human, not by a
   test** (7.4 queue, 7.5 statement, 7.8 narrative).
10. **Phase 7.10 — the biggest one, and the same defect four times.** Wiring the two
   unused detection layers into the demo world exposed that **screening was being discarded
   wholesale**: a screening-only case scores weight × match, so at weight 0.20 its ceiling
   is *exactly* 20.0, which was the case-opening threshold. Only a perfect 1.000 name match
   ever reached an analyst — every transliteration and reordered variant (0.887-0.984,
   the whole reason a fuzzy matcher exists) landed at 17.7-19.7 and was dropped at the gate.
   **14 of 15 planted entities.** Phase 4 measured 100% recall; the layer above deleted it.
   The threshold is now derived from both sides (`risk.MIN_CASE_SCORE`), and the test pinning
   that window immediately caught **7.4's bug living in the graph layer** — chain strength
   was `min(hops,4)/4`, so a 2-hop chain (Phase 5's shortest reportable) scored 15.0, exactly
   the model's ceiling. Hidden for three slices because every chain in the demo world happens
   to be 3 hops. One root cause behind all four: **a global threshold applied to a score whose
   scale depends on which layers fired.**

---

## 8. Load-bearing design decisions (do not silently reverse)

- **Edge reconstruction joins on the narration reference number**, not (timestamp, amount).
- **Chains are suffix-collapsed** — growing from every edge rediscovers a long chain from its
  2nd and 3rd accounts; an investigator wants the path once.
- **Name matching uses token alignment, NOT whole-string Jaro-Winkler** — JW's prefix bonus
  scored "Suresh Kumar" vs "Suresh Gupta" at 0.900.
- **`ml/tournament.py` scores at an ALERT BUDGET**, and reports **average precision, not
  ROC-AUC** (ROC flatters everything at a 1.4% positive rate).
- **Risk score is a weighted sum, not a meta-model** — "the model said so" is not a SAR.
- **`case_events` is append-only**; reopening clears the disposition but never its history.
- **Case evidence is snapshotted at open time** — detectors get retuned.
- **API lifecycle violations return 409, not 500**; every mutation requires a named actor.
- **The queue is tiered by evidence, not sorted by the blended score** — 7.1 measured the blend
  doesn't rank better while graph alone hit 100% precision.
- **New name/list values are APPENDED, never reordered** — that is what made 4.2's controlled
  before/after possible by slicing.
- **Account totals on the entity screen are computed in SQL over the whole history**, never
  summed from the transaction window the page holds — a window number presented as a whole
  number under-reports silently. The UI requests the endpoint's maximum window for the same
  reason.
- **Chains carry the ledger rows they were built from** (`Chain.hop_txns`). A chain nobody can
  trace to transactions is an assertion, not evidence — and the SAR narrative has to cite rows.
- **The SAR narrative is a template, never a language model.** Every figure is asserted to a
  regulator; a generated sentence that rounds a number is a false statement in a filing.
- **The narrative never asserts that laundering occurred** — "consistent with", never "the
  customer laundered". The bank reports suspicion; it is not the finder of fact.
- **Risk bands describe corroboration, not a percentage** (60/40/18/0): medium is one named
  piece of evidence, high is two independent layers agreeing, critical is strong corroboration.
  Derived from the signal algebra — do not re-fit them to one world's histogram.
- **The disposition list is served by the API, never hardcoded in the UI**, and a test asserts
  no disposition string appears in the page.
- **Adverse media is surfaced, never scored** (7.12, measured). `risk.collect(media_mode="off")`
  is the production default; `"separate"` and `"folded"` exist for the experiment only. Do not
  give it a weight without re-running `media-experiment` and finding a NON-empty unique-reach set.
- **`aggregate()` breaks ties on account id.** Not cosmetic: 45 accounts tie at 21.00 and the
  budget cut falls inside that cluster, so without it the queue's membership — and any
  budget-capped measurement — is decided by dict insertion order.
- **`risk.MIN_CASE_SCORE` (17.5) is DERIVED, not chosen**: above the model's 15.0 ceiling (a
  model-only alert has no reason to give an analyst) and at or below the faintest thing any
  control will assert (screening's 0.88 accept threshold × 0.20 = 17.6). A test pins that
  window — **if you change any weight, that test fails on purpose.** Do not widen it to make
  it pass; re-derive.
- **Evidence strength uses one shared diminishing-returns curve** (`corroboration_strength`,
  `1 - 0.4^n`) for rules AND graph hops. Linear-in-count made the minimum reportable case
  score a fraction of a signal — the 7.4 bug, which was found twice in two different layers.
- **`risk.TIER_ORDER` is canonical** and ordered by *how specific a reason the analyst gets*
  (graph names a path, a rule names a scenario, screening names a person, a model names
  nothing), NOT by 7.1's standalone precisions — those measure each layer as a lone ranker,
  and using them filed sanctions hits under a "model-ranked" heading. A test pins the page to
  this list.
- **The demo's ML scores are unsupervised and budgeted** (isolation forest, top 100). One
  world means a supervised model would score the accounts it was fitted on; and scoring
  *every* account gave mid-ranked ones ~7 free points toward the opening threshold.

---

## 9. Known open items

| Item | Status |
|---|---|
| Statement ceiling | The entity screen requests 500 transactions, the endpoint's max. A busier account still truncates — it says so in a caption, but paginate when a world produces one (`ponytail:` comment in `index.html`) |
| Only graph can cite its own rows | Rules emit a reason string, screening answers an identity question, ML emits a score — none records *which* transactions made it fire, so the SAR annex is ranked by value and says so. Making rules record their triggering txn ids would upgrade every narrative |
| **The model tier cannot fill** | By arithmetic, and deliberately: the ml weight is 0.15, so a model-only case tops out at 15.0 and the opening threshold sits above it, because an alert with no explainable reason should not open a case. The UI says this in the empty tier rather than looking quiet. **Letting it fill is a re-weighting decision — and it is the tier that matters most against a red team that has learned to evade the named scenarios, so Phase 8 will have to face it.** |
| **Sanctions lose the shared alert budget** | Screening-only hits score 17.6-19.7, the lowest of any control, so under one budget every behavioural case outranks them — 42 of 92 eligible accounts did not fit. Real banks queue screening separately under its own obligation clock; a per-tier budget in `open_from_queue` would model that |
| ~~Adverse media leg unscored~~ | **Settled by 7.12: measured and rejected as a scoring signal, weight 0.0.** Of 21 accounts it flags, 1 is laundering, and the set of laundering accounts only media reaches is **empty** — so no weighting can add a true positive, and every weighting displaced real cases. It now surfaces on the entity-360 screen as "context, not evidence". `risk.collect(media_mode=...)` keeps the experiment reproducible; production stays `"off"`. Re-run: `python -m launderlab media-experiment` |
| **Single-rule cases are all tied** | Every one scores exactly 0.35 × 0.60 = 21.00, so a 27-deposit structuring scheme and an 89-deposit one are indistinguishable to the queue — and on the demo world 45 accounts sit on that value with the budget cut inside the cluster. Ties now break on account id so the queue is at least *reproducible*, but giving rules a magnitude-aware confidence is a real scoring change needing its own measurement |
| **1.3 world realism** | Weekday/weekend variation, holidays. Open since 2026-07-26, non-blocking, and has blocked nothing across five phases. The only reason Phase 1's roadmap box is unchecked |
| **4.1 secondary identifiers** | DOB/nationality disambiguation. Re-scoped by 4.2 to a realism item rather than a precision fix |
| **1.3** | World realism polish — weekday/weekend, holidays. Non-blocking |
| **4.1** | Secondary-identifier (DOB/nationality) disambiguation. **Re-scoped by 4.2** — exact-name FPs went to 0 on their own, so this is realism, not a precision fix |
| ~~UI is not React~~ | **Settled 2026-07-30: Dhanush chose the single page. Do not reopen this.** One self-contained HTML file, no bundler, no `node_modules`, no extra CI stage. The API stays the contract regardless, so nothing downstream depends on the choice. |
| `counterparty_concentration` | Knowingly produces false positives; measured as unfixable by threshold |
| Small structuring | Documented blind spot — indistinguishable from a shop banking takings |
| `dormant_reactivation` recall | 60% (9/15) — injector's gap parameter sometimes lands too close to normal weekly cadence |
| Watchlist | **Synthetic**, not real OFAC/UN data. Swap via `LAUNDERLAB_WATCHLIST` |
| MCP server demo | Fixed by 7.9 + 7.10 — point it at `data/demo.duckdb`: typologies, watchlist entities AND adverse media are all planted, so `run_detection`, `screen_name` and `adverse_media_check` all surface real hits |
| Test suite runtime | ~9 min (242 tests). Do not run two full suites concurrently (once took 72 min). `test_demo.py` is the slowest file — a structuring injection costs ~4s |

---

## 10. Working discipline — non-negotiable

From `PROJECT.md`'s quality bar:
- **`main` never breaks** — every slice runs end-to-end before commit
- **pytest + ruff green before every commit**; CI on every push, always verified after
- **Every phase ships a visual artifact**, never just tables
- **Blue-team code never reads ground truth**

**Rituals:** `"start day"` → read `PROJECT.md` + last Field Notes entry → agree ONE slice →
build it. `"close day"` → commit, push, append three insights to `ledger/FIELD-NOTES.md`
(🏦 FCC domain · 🔧 engineering · 🎯 interview line) and one line to `ledger/INTERVIEW-AMMO.md`.
New jargon goes to `ledger/GLOSSARY.md`.

**Method that produced everything good here:** measure, don't guess. Before publishing a
number, ask whether the synthetic data manufactured it. When a result looks perfect, hunt the
leak. Report negative results.

---

## 11. Dhanush's preferences (stored in Claude memory)

- **Explain everything in plain, beginner-level language.** He is a domain expert in FinCrime,
  not a software engineer. Give a plain-English summary of what changed and why *in addition
  to* the technical detail. Define terms in the same sentence; spell out acronyms every time.
- **He wants genuine reasoning and honest pushback, not agreement.** He has explicitly thanked
  a "why not this" answer. If a suggestion has a real tradeoff, say so with reasons — a
  comparison table lands well. Don't soften into "both are fine".
- He proposes architecture ideas himself and they are usually sound — validate against what's
  already planned before agreeing or extending.

---

## 12. Canonical docs in the repo

| File | Contents |
|---|---|
| `PROJECT.md` | Roadmap + **slice log** (every slice, dated, with real numbers) + rituals + pending |
| `ledger/FIELD-NOTES.md` | Every day's 3 insights — the learning record |
| `ledger/INTERVIEW-AMMO.md` | ~30 STAR-ready interview sentences harvested from real work |
| `ledger/GLOSSARY.md` | ~40 FCC terms decoded |
| `ledger/FCC-PRIMER.md` | The three laundering stages mapped to subsystems |
| `ledger/PITCH.md` | How to explain the project to any audience |
| `README.md` | Public face — includes Phase 4/5 results and the honest caveats |
| `../LAUNDERLAB-PLAN.md` | The 18-week master plan, research thesis, all phases |

---

## 13. Exact next steps

**Phase 7 is complete. Next is Phase 8 — red-team co-evolution, the project's crown jewel.**

Phase 8 is the detection-decay benchmark: an adversary that mutates its schemes each
generation against the blue team, measuring how fast a detection stack rots. Everything it
needs now exists — six parameterised typology injectors, four detection layers, a scoring
module per layer, and `demo.build()` (7.9) which already composes generate → inject → detect
→ open cases into one call and is the natural skeleton for a generation loop.

The first design call is what the red team is allowed to mutate: injector *parameters*
(amounts, gaps, hop counts, chain lengths) is the honest version, because those are the knobs
a real launderer has. Letting it mutate against the detectors' own thresholds would be
training on the answer key — the same boundary violation the whole project is built to avoid.

**Phase 8 will force the model-tier decision.** The adversary's whole purpose is evading named
scenarios; when it succeeds, rules and graph go quiet and the model is the only layer left. At
the current weights a model-only alert cannot open a case (15.0 vs a 17.5 threshold), so the
decay benchmark would measure the stack going blind while the model was in fact still ranking
the adversary highly. Decide the weighting deliberately *before* running the benchmark, or the
headline number will be an artefact of the aggregation rather than of detection decay — which
is exactly the class of mistake §7 is a list of.

**The React question is settled** — Dhanush chose the single page on 2026-07-30. The one
front-end question still open is whether the SAR narrative should get an LLM *polish* pass on
top of the template (7.8 deliberately shipped template-only, because a generated figure in a
regulatory filing is a false statement; polishing prose an analyst then verifies is a different
and safer feature).

**To see the workbench with real data:**
```
.venv/Scripts/python -m launderlab demo-world
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m uvicorn launderlab.workbench.api:app --port 8787
```

**To start a session:**
1. Read `PROJECT.md` and the last entry of `ledger/FIELD-NOTES.md`
2. Confirm the tree is clean and CI is green
3. Agree ONE slice
4. Build → test → lint → real-scale proof → docs → commit → push → verify CI
5. Close with three Field Notes insights

**After Phase 7:** Phase 8 (red-team co-evolution — the detection-decay benchmark, and the
project's crown jewel), Phase 8.5 (multi-bank experiment — Phase 5 already measured the
blind spot at 1-in-6, which is the setup for this), Phase 9 (Story Mode + whitepaper + demo
video + launch).
