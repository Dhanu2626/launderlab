# LaunderLab

**An open adversarial simulation range for AML detection.**

A self-contained synthetic bank where an automated red team invents money-laundering
schemes and a detection stack has to catch them — and both sides evolve against each other.
Cyber ranges exist for security teams; nothing like them exists for financial-crime teams.
LaunderLab is that missing range: the bank, the criminal, and the investigator in one loop.

```
RED TEAM ──launders through──► SYNTHETIC BANK ──transactions──► BLUE TEAM
   ▲                                                               │
   └────────────── mutates strategy from misses ◄──────────────────┘
                                                                alerts ──► INVESTIGATOR
                                                                           WORKBENCH
```

## Status

✅ **Phases 0–8.5 complete** — the full AML value chain, end to end, plus both research benchmarks:

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

Next: **Phase 9** — Story Mode, whitepaper, demo video and launch.

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
| S7 Story Mode | Visual finale: animated money-flow maps, scheme replay, red-vs-blue evolution |

## Ethics

All data is synthetic. All typologies come from public FATF / FinCEN / RBI advisories.
This is defensive tooling — the same category as adversarial testing in security.
Nothing here teaches real-world evasion beyond what regulators themselves publish.
