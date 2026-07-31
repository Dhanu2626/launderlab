# LaunderLab

### An Open Adversarial Range for AML Detection Testing

**A self-contained synthetic bank where an automated red team invents money-laundering
schemes and a four-layer detection stack has to catch them — and both sides evolve against
each other.** Cyber ranges exist for security teams; nothing equivalent exists for
financial-crime teams. LaunderLab is that missing range: the bank, the criminal, and the
investigator in one loop.

**Because the injector records ground truth, every detector is scored on real precision and
recall — something no production bank can do, because no bank knows what it missed.** That
single property is what makes the numbers below measurements rather than claims.

**▶ [See it running](https://dhanu2626.github.io/launderlab/)** — an interactive research site:
replay a laundering scheme day by day, watch detection close in, and read every measured result
with its methodology and limits. No install. *(Requires GitHub Pages enabled on this repo:
Settings → Pages → Deploy from a branch → `main` / `docs`.)*

<sub>Built by Dhanush Jangadi. All data synthetic; all typologies from public FATF / FinCEN /
RBI advisories.</sub>

---

## Abstract

Anti-money-laundering detection is evaluated almost entirely in private. Vendors publish
recall figures against proprietary datasets, banks cannot measure what their stacks missed,
and the one experiment that matters most — what happens when the adversary adapts — is run,
if at all, behind closed doors. LaunderLab is an attempt to do that evaluation in the open.

It generates a synthetic retail bank (10,000 customers, 630,755 transactions in 31 seconds),
injects six laundering typologies drawn from public advisories while recording ground truth
for every transaction, and runs four detection layers over the result: a rules engine,
sanctions/PEP screening, graph analytics, and a six-family ML tournament. Alerts flow into a
working investigator workbench that ends in a SAR narrative draft. A red team then mutates its
own typology parameters generation over generation, and the whole world is finally partitioned
across four banks with genuinely separate ledgers.

Three findings are the substance of it, and each contradicted the expectation that preceded it.
**Detection decay is not uniform** — one rule collapses within two generations of adaptation
and stays collapsed, while two others never fully evade across eight. **The cross-bank blind
spot is the network, not the account** — banks flag 75–77% of the individual mule accounts on
their own books and reconstruct 0–6% of the chains those accounts form, and a launderer gains
almost nothing by spreading a chain deliberately, because the blind spot is already near-total
by accident. And **"caught" was never one property**: the typology this stack detects fastest
is caught with 100% of the money already moved, because the rule that catches it structurally
cannot fire until the crime has completed.

An equally important result is negative. Combining four detection layers into one risk score
does **not** rank better than the best single layer; adverse media, measured as a scoring
signal, adds no true positive at any weight and was rejected. Both are reported here rather
than buried, and §*The honesty thread* below lists sixteen occasions where a flattering number
turned out to be an artefact and was corrected.

### The three research questions

| | Question | Answer |
|---|---|---|
| 1 | **Detection decay** — how fast does a stack rot against an adapting adversary? | **Non-uniformly.** `shell_company` collapses to 0% recall by generation 2 and stays there; `structuring` and `round_tripping` never fully evade across 8. A single aggregate recall number could not have shown this. |
| 2 | **False-positive economics** — what does a true alert actually cost? | Measured for every config, never guessed. On the demo world the **top 25 alerts are 100% real**; the next 25 cost 10 false positives — 1.25 reviews per true find at a budget of 50. |
| 3 | **The cross-bank blind spot** — what can one bank not see? | Banks flag **75–77%** of individual mule accounts and reconstruct **0–6%** of the chains. Privacy-preserving co-operation on HMAC'd payment references recovers **69–81%** of hops without sharing customer data. |

```
RED TEAM ──launders through──► SYNTHETIC BANK ──transactions──► BLUE TEAM
   ▲                                                               │
   └────────────── mutates strategy from misses ◄──────────────────┘
                                                                alerts ──► INVESTIGATOR
                                                                           WORKBENCH
```

## Status

✅ **Phases 0–9 complete** — the full AML value chain, end to end, plus both research benchmarks
and the visual layer:

| Phase | What it is | Headline |
|---|---|---|
| 0–1 | World engine | 10,000 customers, 630,755 transactions in 31s, all balances reconciled |
| 2 | Typology injector | 6 laundering typologies, each writing ground truth so detection can be scored |
| 3 | Rules engine | 6 tunable scenarios, re-tuned twice when the world got more honest |
| 4 | Screening | 100% recall; **86% of the false-positive rate was a data artefact**, measured not guessed |
| 5 | Graph analytics | 15/15 mule networks reconstructed at 100% precision — and **only 1 of 6 typologies is visible to a graph at all** |
| 6 | ML tournament | 6 model families on one leaderboard; **they fail differently**, which is the argument for the tournament |
| 7 | Investigator workbench | Alert queue → entity 360 → link graph → disposition → SAR narrative draft |
| 8 | Red team decay benchmark | Detection decay is **not uniform** — one rule collapses in 2 generations of adaptation and stays collapsed; two others never fully evade across 8 |
| 8.5 | Multi-bank blind spot | Banks flag **75-77% of individual mule accounts** and reconstruct **0-6% of the chains** they form. Privacy-preserving co-operation recovers 69-81% |
| 9 | Story Mode + metrics | Replay any scheme day by day. **Detection latency and usefulness are nearly inverted** — see below |

### The newest finding: "caught" was never one property

Every detection number above was scored against the *finished* world — graded once, at the end.
That quietly assumes a bank may wait until the crime is over before deciding it happened. Real
monitoring runs nightly against the ledger so far, so `python -m launderlab story` replays each
day and re-runs the **unmodified** detectors against a view of the ledger truncated to that day.

| typology | caught | median days to first alert | share already moved by then |
|---|---|---|---|
| dormant_reactivation | 3/5 | 0 | **100%** |
| high_risk_geography | 5/5 | 0 | 60% |
| layering | 8/8 | 1 | 46% |
| round_tripping | 5/5 | 4 | **100%** |
| shell_company | 5/5 | 6 | 58% |
| structuring | 8/8 | **9** | 47% |

`round_tripping` is caught in four days with all of the money already moved, because the rule
needs the *return* leg before it can fire — it is structurally incapable of alerting while
anything is stoppable, and no threshold changes that. `structuring` is the slowest to detect and
among the best on the column that matters. Reporting latency alone would have been the
flattering half of the truth.

## Quickstart (Windows)

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,api]"
.venv\Scripts\python -m pytest -q
```

Build a bank with crime in it and open the investigator's workbench on it:

```
.venv\Scripts\python -m launderlab demo-world
set LAUNDERLAB_DB=data\demo.duckdb
.venv\Scripts\python -m uvicorn launderlab.workbench.api:app --port 8787
```

`demo-world` generates 1,200 accounts and 78,556 transactions, injects all six typologies
plus watchlist entities and adverse media, runs the whole detection stack and opens the cases
an analyst would find waiting — 50 of 92 eligible accounts, in about 20 seconds. It reports what
it had to cut, and why. Then open <http://127.0.0.1:8787/>.

Redraw the measured results as charts (recall by typology, the graph blind spot, what
actually reaches an analyst):

```
.venv\Scripts\python -m launderlab charts
```

Replay the crime itself — a scheme picker, a day scrubber, and accounts that light up only when
a real detector actually fires on them (never because they are in the answer key):

```
set LAUNDERLAB_DB=data\demo.duckdb
.venv\Scripts\python -m launderlab story
```

Run the two research benchmarks (each writes its own chart into `charts/`):

```
.venv\Scripts\python -m launderlab redteam      detection decay vs an adapting adversary (~8 min)
.venv\Scripts\python -m launderlab multibank    the cross-bank blind spot (~1 min)
```

Smaller pieces:

```
.venv\Scripts\python -m launderlab seed             25-customer world, one week of life
.venv\Scripts\python -m launderlab statement A001   render an account as a bank statement
```

## AML MCP server

Exposes the ledger and detection stack to an AI agent (Claude Code, Claude Desktop) over
[MCP](https://modelcontextprotocol.io), so an analyst can ask questions in plain language
instead of writing SQL.

```
.venv\Scripts\python -m pip install -e ".[mcp]"
.venv\Scripts\python -m launderlab.mcp_server
```

`.mcp.json` registers it for Claude Code automatically when you open this repo.

| Tool | Returns |
|---|---|
| `screen_name` | Fuzzy sanctions/PEP hits + high-risk jurisdiction flags |
| `adverse_media_check` | Adverse news matching a name (benign coverage excluded) |
| `customer_profile` | KYC identity, risk rating, KYC level, linked accounts |
| `transaction_history` | An account's transactions, newest first (max 500) |
| `run_detection` | Alerts from the same six rules the offline scorer grades |
| `audit_trail` | Every tool call made against this server |

Both screening tools are thin front ends over `launderlab.screening` — the same matcher the
offline scorer grades, so what the agent sees is exactly what the published precision/recall
numbers describe, not a second implementation that drifted.

Three properties are deliberate, not incidental:

- **Read-only.** No tool writes to the ledger. The only write is the audit row.
- **Audited.** Every call is logged with its parameters and outcome, failures included.
  An automated screening decision nobody can reconstruct afterwards is the exact gap
  regulators keep fining firms over.
- **No generic SQL tool.** A raw-query tool would let any agent read `scheme_labels` and
  invalidate every score the range produces. Tools are narrow so that boundary holds.

The bundled watchlist in `src/launderlab/db/watchlist.json` is **synthetic** — a
placeholder shaped like the real thing. Point `LAUNDERLAB_WATCHLIST` at OFAC SDN, the UN
Consolidated List, or EU CFSP data before drawing any real conclusion from a hit.

## Screening (Phase 4) — and what it measures

`launderlab.screening` matches names with Jaro-Winkler plus Metaphone corroboration over
aligned name tokens, so transliterations (`Farhan`/`Farhaan`), phonetic variants
(`Mohammed`/`Muhammad`), initials (`S K Gupta`) and reordered names all still hit. It is
graded against its own ground truth — `entity_labels` and `media_labels` — the same way the
rules engine is graded against `scheme_labels`.

On a 10,000-customer world with 15 watchlist entities and 49 news articles planted:

| Leg | Recall | Precision |
|---|---|---|
| Sanctions / PEP screening | 100% | 75.0% |
| Adverse media | 100% | 15.8% |

Recall is perfect and precision is not, which is the point — but the interesting part is
*why*, and that was measured rather than asserted.

### How much of a false-positive rate is real?

The first run of this scored **29.4%** precision. Before publishing that as evidence of the
industry's false-positive problem, it was worth asking whether it was really a finding or
just an artefact of a synthetic world — so the name pool became a controlled experiment.
Same world seed, same injections, only name diversity varying:

| | Names per customer | Entity precision | Media precision | False positives |
|---|---|---|---|---|
| Narrow pool (40×25) | 9.41 share a name | 29.4% | 3.7% | 36 (6 exact-name) |
| Realistic pool (193×120) | 1.49 share a name | **75.0%** | **15.8%** | 5 (**0** exact-name) |

**86.1% of the false positives were collision density in the generated data. 13.9% is
irreducible name ambiguity** — transliteration-equivalents that no matching algorithm can
separate, only a secondary identifier like date of birth can. Recall stayed at 100% in both
arms, so the diversity fix cost nothing.

That decomposition is the actual result. A raw false-positive rate from a synthetic world
proves very little on its own; knowing which fraction of it survives a realistic name
distribution is what makes it worth quoting.

## Graph analytics (Phase 5) — and the blind spot it measures

`launderlab.graph` rebuilds the internal transfer graph from the ledger (pairing the two
legs of each payment by the reference they share) and walks it forward through time to find
**pass-through chains**: money arriving and leaving again within hours, slightly smaller,
repeatedly down a path. That shape does not exist in any single account's history — only in
the edges between accounts — which is exactly what a per-account rule cannot see.

On the same 10,000-customer world, with 15 of each typology injected:

| | Result |
|---|---|
| Mule networks reconstructed | **15 / 15** |
| Chains reported | 15 (0 false positives) |
| Precision / recall | **100% / 100%** |
| Graph size | 8,538 nodes, 173,525 edges — built in 1.8s |

Phase 3's `rapid_pass_through` rule had already flagged 47 of the 62 accounts involved. But
62 flagged accounts is 62 separate alerts to triage; *"money moved A→B→C→D over 27 hours,
losing 6% a hop"* is one case with a narrative. Turning the former into the latter is the
whole point of the graph layer.

### The number worth leading with

Of six injected typologies, **only one is visible to a graph at all**:

| Typology | Schemes with internal edges |
|---|---|
| Layering (mule networks) | 15 / 15 |
| Structuring | 0 / 15 |
| Shell company | 0 / 15 |
| Round-tripping | 0 / 15 |
| Dormant reactivation | 0 / 15 |
| High-risk geography | 0 / 15 |

Not a detection failure. Cash deposits, offshore invoices and inbound remittances have
counterparties that bank *somewhere else*, so they leave a single leg in this ledger and no
edge to analyse. A bank's graph can only contain the fraction of a network that happens to
sit inside it — the cross-bank blind spot from the research thesis, measured as 1-in-6, and
the reason Phase 8.5 exists.


## Investigator workbench (Phase 7) — and the three bugs it found

Detection produces an alert. A bank produces a *decision*, and a decision that cannot be
explained, traced or defended a year later is worthless. The workbench is that half of the
job: a queue tiered by kind of evidence, the full customer picture behind any alert, the
money chain drawn as a path you can click through, an append-only audit trail, and a
Suspicious Activity Report narrative drafted from the case record.

**The queue is tiered by evidence, not sorted by one blended score.** Slice 7.1 measured
whether combining four detection layers into a single number ranks better than the best
single layer. It does not — at an alert budget of 25 the ML model alone beat the blend,
because screening dilutes it. Graph evidence alone hit 100% precision. So Tier 1 is network
evidence, Tier 2 is rule alerts, Tier 3 is model-ranked, and the combined score buys
explainability rather than accuracy. That finding is reported rather than buried.

**The SAR narrative is a template, not a language model** — deliberately, and the plan had
allowed the LLM. Every figure in a filing is asserted to a regulator by the bank, so a
generated sentence that rounds ₹26,00,000 to "approximately 2.5 million" is a false
statement in a legal document, not a style problem. The template can only emit numbers it
read from the ledger, and the same case always drafts identically.

### Three defects that only a human reading a screen could find

Every one of these passed a full test suite. None of them was a coding error.

| Where | What was wrong |
|---|---|
| Alert queue (7.4) | Rule strength was `min(n,3)/3`, so a genuine structuring scheme — 27 cash deposits, ₹26 lakh — tripped exactly one rule, scored 11.7/100 and **fell below the queue cut-off**. Confirmed placement cases were invisible to analysts, while mule accounts at 34.2 appeared. 178 tests passed, because every one asserted *relative* behaviour, and that stayed true. |
| Entity 360 (7.5) | The transaction endpoint defaults to the latest 100 rows. An account alerted for **89 cash deposits** rendered a statement starting a week after the account's own history did — the evidence screen was truncating the evidence. Truncation is invisible by construction: it looks like a shorter list. |
| Risk bands (7.8) | Printing a SAR narrative showed a confirmed structuring scheme describing itself to a Financial Intelligence Unit as **"low band"**. Measured across the bank: all 50 cases were low or medium, and the highest score that existed anywhere was 43.5. `high` and `critical` were words describing nothing, because the thresholds assumed a 100 that needs all four layers firing at once on one account. |
| Sanctions screening (7.10) | A screening-only alert scores the layer's weight × the match confidence, so at weight 0.20 its ceiling was *exactly* the threshold at which a case opens. Only a **perfect 1.000 name match** ever reached an analyst — every transliteration and reordered variant, the entire reason a fuzzy matcher exists, scored 0.887-0.984 and was dropped at the gate. **14 of 15 planted watchlist entities.** Phase 4 had measured 100% recall; the layer above it deleted the result. |
| Graph strength (7.10) | The test written to pin the fix above caught the *same bug as 7.4* hiding in the graph layer: chain strength was `min(hops,4)/4`, so a 2-hop chain — the shortest Phase 5 reports, real evidence with both ledger rows behind it — scored half. Invisible for three slices because every chain in the demo world happens to be 3 hops. |

The pattern is the point, and by the end it had a name. Three of these surfaced by rendering
a number where a person had to read it next to a decision — detection metrics grade a
detector against ground truth, but nothing grades whether its output is *usable*. The last two
share a single root cause: **a global threshold applied to a score whose scale depends on which
layers happened to fire.** Every individual number looked reasonable; the defect existed only in
the interaction. So the case-opening threshold is now *derived* rather than chosen — above what
a model alone can score, at or below the faintest thing any control will assert — and a test
pins that window, so changing a weight fails on purpose instead of silently switching off a
control.

## Red team decay benchmark (Phase 8) — and why it isn't one number

Nobody has published this number: how fast does a static detection stack rot against an
adversary that adapts generation over generation? It needs ground truth on both sides at
once — a real bank sees its own catch rate but never the schemes it missed, and no public
dataset contains a criminal who learns. This project has both.

One adversary genome per typology starts at a naive default and takes one step toward whatever
real-world-plausible parameter change plausibly reduces detectability each generation it gets
caught — fewer, larger deposits instead of many small ones; skim more per hop; fewer invoices —
the same inference a real launderer draws from an account being frozen. It never reads
`scheme_labels` (only the accounts it planted this call, held locally) and never reads a rule's
tuned constants, only public facts any real launderer already knows (the cash-reporting line
near ₹1,00,000). `high_risk_geography` is excluded: its only real evasion move is routing
through an unlisted jurisdiction, a categorical choice with no honest continuous knob.

**The result is not a decay curve, it's proof that decay isn't uniform.** Over 8 real
generations: `shell_company` collapses from 70% to 0% recall by generation 2 and never
recovers — confirming, under real adversarial pressure, a rule Phase 6 had already flagged as
structurally unfixable by threshold. `mule_network` — the one typology both the rules engine
and the graph analytics watch — starts at a perfect 100% and still fully collapses by
generation 7. But `structuring` and `round_tripping` never fully evade across all 8
generations, even at genuinely extreme parameter values (a deposit ceiling one rupee under the
cash-reporting line; a round-trip parked for 38 days) — some detection surfaces are
structurally more resistant to this class of evasion, which Phase 3's single aggregate recall
figure could never have shown.

**"Converged" doesn't mean caught 0% forever, and the benchmark says so as a number.** A
genome freezes once it first fully evades, but it still runs against a freshly generated world
every later generation, so a frozen doctrine can still get unlucky. `dormant_reactivation`
converged fastest of all (generation 2) but least *stably* — 12% mean recall in the
generations after, against `shell_company`'s stable 0%. Two typologies both labelled
"converged at generation 2" were not equally caught.

**A harness bug hid the real result before any of this was visible.** The first version
sampled each typology's accounts independently from a shared pool, so structuring and
shell_company sometimes landed on the *same* business account within one generation — the
extra scheme's credits diluted the concentration signal `shell_company`'s detector watches,
so its measured generation-0 recall came out as 1-in-12 instead of the real 7-in-10. Fixed by
carving disjoint account pools that raise an error rather than silently sampling with
replacement when the pool runs low.

Reproduce it: `python -m launderlab redteam` (~8 minutes, writes `charts/redteam.html`).

## The cross-bank blind spot (Phase 8.5)

A mule chain hops through several banks. Each bank sees one hop, privacy law blocks naive data
sharing, and nobody sees the crime. Central banks run this experiment behind closed doors (BIS
Project Aurora); this is the open version.

The world is split across four banks written to **genuinely separate ledger files** — not a
`WHERE` clause. A filter would have been faster, but every detector in the project would then
have to remember to honour it, and one that forgot would silently give a bank sight of another
bank's rows: inventing detection ability and inflating the exact number the experiment exists to
measure. With separate files the isolation is structural and every detector runs unmodified.

**The finding is sharper than "banks are blind".** Each bank still flags **75-77% of the
individual mule accounts** sitting on its own books — an account's entire history is at its own
bank, so the pass-through rule fires perfectly well. What no bank can do is join those hops into
a chain: rebuilding a chain means pairing the two legs of a transfer, and the second leg is at
another institution. Solo chain reconstruction: **0-6%**.

> The blind spot is the **network**, not the account. Six banks each file a suspicious-activity
> report and nobody can see it is one operation.

**And it does not take a sophisticated launderer.** Two arms were run: chains placed *naively*
with no regard to banks, and chains *deliberately* spread so no two consecutive hops share a
bank. Deliberate placement gave 0% solo reconstruction — but naive placement gave only 6%.
Spreading a chain across institutions on purpose buys almost nothing, because seeing a chain
requires two *consecutive* hops inside one bank, and with n banks those odds fall off as 1/n².
The blind spot is already near-total by accident. The case for co-operation does not rest on
facing a clever adversary.

**What co-operation buys.** Each bank publishes, only for accounts it already flagged itself,
`HMAC(shared_secret, payment_reference)` plus direction, amount and timestamp — never a name,
an account number, a balance, or anything at all about an unflagged account. Matching hashed
references across banks rebuilds the cross-boundary links pseudonymously:

| view | naive placement | deliberate placement |
|---|---|---|
| pooled (hypothetical central view) | 100% | 100% |
| a single bank alone | 6% | 0% |
| privacy-preserving co-operation | **81%** | **69%** |

Keyed HMAC rather than a bare hash, deliberately: a plain SHA-256 of a short numeric payment
reference is trivially brute-forced back to the reference, which would hand every participant a
lookup table for payments they were never party to.

**The residual disclosures are stated, not glossed.** The coordinator still learns the *shape*
of the inter-bank graph — who transacts with whom, at what volume — even without identities. And
a flagged account's *entire* payment history is fingerprinted, not just its suspicious legs:
unavoidable, since which leg is the laundering hop is the very thing reconstruction exists to
find, but it means the disclosure covers innocent payments of a suspected customer. Those are the
honest reasons this is a prototype rather than a proposal, and they are where the real
central-bank work spends most of its effort.

Reproduce it: `python -m launderlab multibank` (~1 minute, writes `charts/multibank.html`).

## The honesty thread

The most valuable property of this project is not any single number — it is that repeatedly a
flattering number turned out to be an artefact, and each time it was measured, corrected and
**written down** rather than quietly kept. A representative sample:

| What looked true | What was actually happening |
|---|---|
| Screening's 29.4% precision proved AML's false-positive crisis | **86% of it was collision density** in the generated names. A controlled two-arm experiment moved it to 75.0% |
| Gradient boosting scored a perfect 1.000 average precision | The legitimate world emitted **zero cash transactions**, so the model had learned "cash = crime" |
| The rules engine had 100% precision | That was a property of a world where nobody legitimately banked cash. Fixing it took `structuring_burst` from **0 to 24 false positives**, and two rules were re-tuned |
| Unsupervised models were strong (SVM 0.910) | They had learned "anomalous = large", which held only while honest traffic had no upper tail. Adding realistic large payments **collapsed them to 0.219** |
| CI was green on every push | It was running **178 of 226 tests** — three modules skipped on a missing dependency, including **two of the boundary-rule enforcers**. A skipped *module* counts as one skip, so 48 missing tests hid behind the number "3" |
| The workbench combined four detection layers | It combined two. Screening's ceiling was *exactly* the opening threshold, so **14 of 15 planted entities never reached an analyst** |
| Risk bands ran low → critical | Every case in the bank was low or medium and the highest score achievable was 43.5. **`high` and `critical` described nothing**, until a SAR narrative printed "low band" for a confirmed structuring scheme |
| Adverse media should obviously be scored | Of 21 accounts it flags, 1 is laundering, and the set it *uniquely* reaches is **empty** — so no weighting can add a true positive. Rejected on measurement |
| Every detection figure was honestly measured | They were all scored against the **finished** world, which assumes a bank may wait until the crime is over to decide it happened (Phase 9.1) |

The pattern behind most of them: they surfaced by **rendering a number where a person had to
read it next to a decision**. Detection metrics grade a detector against ground truth; nothing
grades whether its output is usable — or whether it is being graded on the right axis at all.

## Limitations

Stated plainly, because a range whose limits are unclear is worse than no range.

- **The world is synthetic, and its realism bounds every number here.** Four of the findings
  above are corrections to artefacts of *this* generator. Others certainly remain.
- **The watchlist is synthetic**, not OFAC/UN/EU data. Point `LAUNDERLAB_WATCHLIST` at the real
  thing before drawing any real conclusion from a hit.
- **The red team benchmark is one seed.** Convergence generations are a real measured example,
  not a population statistic. Averaging over seeds is future work.
- **The red team measured rules and graph only.** Whether a *trained* model decays faster or
  slower against the same adversary is a real, different, open question.
- **The multi-bank experiment used one seed and exactly four banks**, and measured mule chains
  only — the other five typologies leave no internal edge even inside a single bank.
- **The co-operation prototype is not a protocol proposal.** The coordinator still learns the
  shape of the inter-bank graph, and a flagged account's *entire* payment history is
  fingerprinted, not just its suspicious legs. Making those private is where BIS Project Aurora
  spends most of its effort.
- **`counterparty_concentration` knowingly produces false positives** and was measured as
  unfixable by threshold: shell schemes sit inside the legitimate range.
- **Small structuring is a documented blind spot** — genuinely indistinguishable from a shop
  banking its takings, which is precisely why real structuring works.
- **Detection latency covers rules and graph only.** Screening answers an identity question
  with no firing day; ML emits a ranking, not an event.
- **Alert-to-SAR conversion is not measurable here** — no case has been worked to a
  disposition, and that is reported as unmeasurable rather than as zero.

## What gets built

| Subsystem | Purpose |
|---|---|
| S1 World Engine | Agent-based synthetic bank + realistic bank-statement generator |
| S2 Typology Injector | Parameterized laundering schemes from public FATF/FinCEN/RBI advisories |
| S3 Blue Team | Rules engine, sanctions/PEP fuzzy screening, graph analytics, explainable ML |
| S4 Investigator Workbench | Alert queue → entity 360 → link graph → disposition → SAR draft |
| S5 Red Team | Adversary that mutates its schemes each generation to evade detection |
| S5.5 Multi-bank | Four separate bank ledgers, the cross-bank blind spot, privacy-preserving co-operation |
| S6 Metrics | Detection rate, false-positive rate, alert-to-SAR conversion, cost per alert |
| S7 Story Mode | Scheme replay with a day scrubber, detection latency, and what had already moved |

## Reproduce every figure in this document

```
.venv\Scripts\python -m launderlab demo-world        build the world (~20s)
set LAUNDERLAB_DB=data\demo.duckdb
.venv\Scripts\python -m launderlab metrics           the operating KPIs
.venv\Scripts\python -m launderlab charts            recall, blind spot, queue, KPIs
.venv\Scripts\python -m launderlab story             scheme replay + detection latency
.venv\Scripts\python -m launderlab redteam           decay benchmark (~8 min)
.venv\Scripts\python -m launderlab multibank         cross-bank blind spot (~1 min)
.venv\Scripts\python -m launderlab publish           collect the pages into docs/
```

Every page is built **on the scoring modules**, so a published figure cannot drift from the one
the scorers grade. The test suite (302 tests, zero skips) enforces the boundary that makes all
of it meaningful: **no detection code may read ground truth**, checked by source-level tests in
twelve places.

## Ethics

All data is synthetic. All typologies come from public FATF / FinCEN / RBI advisories.
This is defensive tooling — the same category as adversarial testing in security.
Nothing here teaches real-world evasion beyond what regulators themselves publish.
