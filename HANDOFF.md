# LaunderLab — project handoff

**Written 2026-07-29, updated 2026-07-31 (Phase 8.5 complete) for a Claude session that has
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

## 2. Current state — verified 2026-07-31

| | |
|---|---|
| Latest commit | `99bee2d` — "Phase 8.5: the cross-bank blind spot, quantified" |
| Working tree | clean, in sync with `origin/main` |
| Tests | **274 passing**, zero skips (~5-9 min) |
| Lint | `ruff` clean |
| CI | GitHub Actions green on every push — installs `[dev,api,mcp]` + CPU torch and **fails if any test skips** |
| Phases complete | 0, 2, 3, 4, 5, 6, 7, 8, **8.5** fully; 1 core (polish deferred) |

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
| 8 | Red Team co-evolution | ✅ complete — 8-generation decay benchmark, non-uniform decay across typologies (see §13) |
| 8.5 | Multi-bank experiment | ✅ complete — cross-bank blind spot quantified + privacy-preserving co-operation prototype (see §13) |
| 9 | Story Mode + launch | ⬜ **not started — this is next, and it is the last one** |

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
  workbench/static/index.html   the whole UI: tiered queue (7.4), entity 360 (7.5),
                        link-graph SVG (7.6), disposition workflow (7.7), SAR draft (7.8)
  demo.py               `python -m launderlab demo-world` — world + crime + cases (7.9)
  viz.py                `python -m launderlab charts` — SVG charts from the SCORERS (7.11);
                        also `render_redteam()` — Phase 8's decay chart, own page
  redteam.py            `python -m launderlab redteam` — Phase 8 co-evolution benchmark:
                        one mutating Knob/Genome per typology, `run_decay_benchmark()`,
                        `report()` incl. post-convergence stability
  multibank.py          `python -m launderlab multibank` — Phase 8.5 cross-bank blind spot:
                        splits the world into 4 banks as SEPARATE DuckDB files, measures
                        solo vs pooled vs co-operative reconstruction, HMAC fingerprints

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
- **Adverse media is surfaced, never scored — final, confirmed by Dhanush 2026-07-30.** Not a
  provisional default awaiting revisit: it is architecture. `risk.collect(media_mode="off")` is
  the production default; `"separate"` and `"folded"` exist for the experiment only, never for
  production code. Do not give media a weight without re-running `media-experiment` and finding
  a NON-empty unique-reach set — and even then, that is new evidence for a new decision, not a
  quiet reversal of this one.
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
- **Each bank in Phase 8.5 gets a SEPARATE DuckDB file, never a `WHERE` clause.** A filter
  would need every detector to remember to honour it, and one that forgot would silently give
  a bank sight of another bank's rows — inventing detection ability and inflating the very
  number the phase measures. Isolation is structural; a test asserts each ledger holds only
  its own accounts, transactions AND customers.
- **Banks publish `HMAC(secret, reference)`, never a bare hash.** A plain SHA of a short
  numeric payment reference is trivially brute-forced back, which would hand every participant
  a lookup table for payments they were never party to.
- **`Fingerprint`'s field list IS the privacy boundary** — a test asserts it contains no
  account id, customer name or balance, so an edit that tries to share more has to change the
  type and trip the test.
- **The co-operative view counts intra-bank hops too** (`cooperative_total_hops`). Scoring
  cross-boundary recoveries alone penalised a carelessly placed chain for hops its own bank
  already held both legs of, and made a deliberately spread chain look BETTER covered —
  backwards, which is how the bug was caught.

---

## 9. Known open items

| Item | Status |
|---|---|
| Statement ceiling | The entity screen requests 500 transactions, the endpoint's max. A busier account still truncates — it says so in a caption, but paginate when a world produces one (`ponytail:` comment in `index.html`) |
| Only graph can cite its own rows | Rules emit a reason string, screening answers an identity question, ML emits a score — none records *which* transactions made it fire, so the SAR annex is ranked by value and says so. Making rules record their triggering txn ids would upgrade every narrative |
| **The model tier cannot fill** | By arithmetic, and deliberately: the ml weight is 0.15, so a model-only case tops out at 15.0 and the opening threshold sits above it, because an alert with no explainable reason should not open a case. The UI says this in the empty tier rather than looking quiet. **Phase 8 confirmed why this matters, concretely rather than hypothetically**: `mule_network` recall fell from 100% to 0% by generation 7 against a real adaptive adversary, and `shell_company` fell from 70% to 0% by generation 2 and stayed there. When rules and graph go quiet like that, the model is the only layer left that could still see something — and at the current weights it cannot open a case alone. **Letting it fill is a re-weighting decision that is now overdue, not hypothetical.** |
| **Phase 8 measured rules + graph decay only** | Deliberately (see `redteam.py` docstring) — whether a TRAINED model (Phase 6) decays faster or slower than static SQL thresholds against the same adaptive adversary is a real, different question, left open for a later slice |
| **Phase 8's numbers are from one seed** | `run_decay_benchmark` ran once (seed 41, 8 generations). The generation-of-convergence figures are a real measured data point, not yet a stable population statistic. Average over several seeds before treating a specific generation count as more than an example |
| **Phase 8.5's co-operation is a prototype, not a protocol proposal** | The coordinator still learns the SHAPE of the inter-bank graph (who transacts with whom, at what volume) even without identities. Making that private too — secure set intersection, differential privacy on volumes — is the real next question and where BIS Project Aurora spends most of its effort |
| **Phase 8.5 used one seed and exactly 4 banks** | The 1/n² mechanism predicts the blind spot deepens as banks multiply; sweeping `n_banks` would turn a stated mechanism into a measured curve. Cheap to do (`run_arm(n_banks=...)`) and would strengthen the whitepaper |
| **Phase 8.5 measured mule chains only** | The other five typologies have counterparties outside the bank by construction (Phase 5's finding), so they are already invisible to a graph even in ONE bank — splitting into four changes nothing for them. Stated so nobody re-measures it expecting a result |
| **Sanctions lose the shared alert budget** | Screening-only hits score 17.6-19.7, the lowest of any control, so under one budget every behavioural case outranks them — 42 of 92 eligible accounts did not fit. Real banks queue screening separately under its own obligation clock; a per-tier budget in `open_from_queue` would model that |
| ~~Adverse media leg unscored~~ | **FINAL ARCHITECTURAL DECISION — confirmed by Dhanush 2026-07-30. Do not reopen without a new measurement.** Adverse media stays investigator context on the Entity-360 screen ("context, not evidence") and carries weight 0.0 in the risk score, permanently. 7.12 measured it: of 21 accounts it flags, 1 is laundering, and the set of laundering accounts only media reaches is **empty** — so no weighting can add a true positive, and every weighting tried displaced real cases out of the alert budget. `risk.collect(media_mode=...)` keeps the experiment reproducible; production stays `media_mode="off"`. If a future world or a future analyst ever makes the unique-reach set non-empty, that is new evidence and re-running `python -m launderlab media-experiment` is the correct way to revisit this — but the decision itself does not get re-argued casually. |
| **Single-rule cases are all tied** | Every one scores exactly 0.35 × 0.60 = 21.00, so a 27-deposit structuring scheme and an 89-deposit one are indistinguishable to the queue — and on the demo world 45 accounts sit on that value with the budget cut inside the cluster. Ties now break on account id so the queue is at least *reproducible*, but giving rules a magnitude-aware confidence is a real scoring change needing its own measurement |
| **1.3 world realism** | Weekday/weekend variation, holidays. Open since 2026-07-26, non-blocking, and has blocked nothing across eight phases. The only reason Phase 1's roadmap box is unchecked |
| **4.1 secondary identifiers** | DOB/nationality disambiguation. Re-scoped by 4.2 to a realism item rather than a precision fix |
| ~~UI is not React~~ | **Settled 2026-07-30: Dhanush chose the single page. Do not reopen this.** One self-contained HTML file, no bundler, no `node_modules`, no extra CI stage. The API stays the contract regardless, so nothing downstream depends on the choice. |
| `counterparty_concentration` | Knowingly produces false positives; measured as unfixable by threshold |
| Small structuring | Documented blind spot — indistinguishable from a shop banking takings |
| `dormant_reactivation` recall | 60% (9/15) — injector's gap parameter sometimes lands too close to normal weekly cadence |
| Watchlist | **Synthetic**, not real OFAC/UN data. Swap via `LAUNDERLAB_WATCHLIST` |
| MCP server demo | Fixed by 7.9 + 7.10 — point it at `data/demo.duckdb`: typologies, watchlist entities AND adverse media are all planted, so `run_detection`, `screen_name` and `adverse_media_check` all surface real hits |
| Test suite runtime | ~5-9 min (274 tests). Do not run two full suites concurrently (once took 72 min) — also true of running the suite alongside `python -m launderlab redteam`, which cost this run several extra minutes of CPU contention. `test_redteam.py`'s small live run and `test_demo.py` are the slowest files |

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

**Phase 8.5 is complete. Next is Phase 9 — Story Mode, whitepaper, demo video and launch —
and it is the last phase.**

**What Phase 8.5 found**: the blind spot is the NETWORK, not the account. Split across 4 banks
with separate ledgers, each bank still flags 75-77% of the individual mule accounts on its own
books (an account's whole history is at its own bank, so `rapid_pass_through` works fine) while
reconstructing only 0-6% of the chain hops those accounts form. Rebuilding a chain means pairing
two legs of a transfer, and the second leg is at another institution. **Deliberately spreading a
chain across banks buys the launderer almost nothing** (6% → 0%) — with n banks the odds of even
one reportable same-bank stretch fall as 1/n², so the blind spot is already near-total by
accident. Privacy-preserving co-operation (HMAC'd payment references only, published only for
accounts a bank already flagged itself) recovers **81% of hops for naive placement, 69% for
deliberate**. Reproduce: `python -m launderlab multibank` (~1 min; writes `charts/multibank.html`).

**What Phase 8 actually found, in one paragraph**: decay is not uniform across typologies.
`shell_company` collapses fastest and most completely (70%→0% recall by generation 2, stable
at 0% after — confirming 6.2's "measured as unfixable by threshold" finding under real
adversarial pressure rather than a static test). `mule_network` — the one typology both rules
AND the graph watch — starts at a perfect 100% and still fully collapses by generation 7.
`structuring` and `round_tripping` never fully converge across 8 generations even at realistic
parameter extremes, genuinely more resistant to this evasion class. `dormant_reactivation`
converges fastest (generation 2) but least *stably* — 12% mean recall afterward, which is why
the report measures post-convergence stability as its own number rather than trusting the word
"converged" to mean permanent. Full numbers, the harness bugs found building it, and the
methodology are in PROJECT.md's Phase 8 slice-log entry and `ledger/FIELD-NOTES.md`.
Reproduce: `python -m launderlab redteam` (~8 min; writes `charts/redteam.html`).

**The model-tier decision from §9 is now the most concrete open item, not a hypothetical
one.** Phase 8 showed rules and graph actually going to 0% recall against a real adversary. At
the current weights (ml=0.15, threshold 17.5) a model-only alert still cannot open a case. If
Phase 8.5 or a future decay run needs the aggregated risk score (not just the raw rules+graph
layers Phase 8 measured directly) to reflect what happens once an adversary has evaded the
named scenarios, that re-weighting has to happen first — deliberately, and measured the way
7.10 and 7.12 measured their own changes, not guessed at.

**Two honest limits on Phase 8, logged rather than hidden**: it is one random seed's
realisation of one adaptive trajectory (average over seeds before treating a specific
generation-of-convergence number as more than a real example), and it measures rules + graph
decay only — whether a *trained* ML model (Phase 6) decays faster or slower against the same
adversary is a different, real question left open.

**The React question is settled** — Dhanush chose the single page on 2026-07-30.
**The adverse-media question is settled** — Dhanush confirmed 2026-07-30: context on Entity-360,
weight 0.0 in scoring, permanently (see §8, §9). The one front-end question still open is
whether the SAR narrative should get an LLM *polish* pass on top of the template (7.8
deliberately shipped template-only, because a generated figure in a regulatory filing is a false
statement; polishing prose an analyst then verifies is a different and safer feature).

**To see the workbench with real data:**
```
.venv/Scripts/python -m launderlab demo-world
LAUNDERLAB_DB=data/demo.duckdb .venv/Scripts/python -m uvicorn launderlab.workbench.api:app --port 8787
```

**To reproduce the Phase 8 benchmark and its chart:**
```
.venv/Scripts/python -m launderlab redteam
```

**To reproduce the Phase 8.5 multi-bank experiment and its chart:**
```
.venv/Scripts/python -m launderlab multibank
```

**To start a session:**
1. Read `PROJECT.md` and the last entry of `ledger/FIELD-NOTES.md`
2. Confirm the tree is clean and CI is green
3. Agree ONE slice
4. Build → test → lint → real-scale proof → docs → commit → push → verify CI
5. Close with three Field Notes insights

**Phase 9 is the whole remaining scope** (see `../LAUNDERLAB-PLAN.md`): Story Mode (animated
money-flow Sankey, link graph lighting up as detection closes in, timeline scrubber, red-vs-blue
evolution chart), a metrics dashboard, the README rewritten as a whitepaper, a 3-minute demo
video driven by Story Mode, a LinkedIn launch post, and resume bullets into
`job hunt/db/profile.md` so CareerForge starts using this immediately.

Phase 8.5's chart is the whitepaper's headline per the master plan — `charts/multibank.html`
already renders it, and `charts/redteam.html` is the Phase 8 companion.
