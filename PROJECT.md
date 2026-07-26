# LaunderLab — project operating doc

Read this file + the last Field Notes entry at "start day".
Full 18-week plan: `../LAUNDERLAB-PLAN.md` (CareerForge root).
FCC concepts: `ledger/FCC-PRIMER.md` — the three laundering stages mapped to subsystems.

## Research thesis — three unsolved problems we attack

1. **Detection decay** — how fast does a detection stack rot against an adapting adversary? (Phase 8 benchmark; exists nowhere today)
2. **False-positive economics** — cost-per-true-alert measured for every detection config, not guessed (Phases 3–6)
3. **The cross-bank blind spot** — quantify what single banks can't see in multi-bank mule chains, then measure the lift from privacy-preserving co-operation (Phase 8.5; BIS Project Aurora does this privately — no open version exists)

**Three tracks:** an analyst doesn't just generate data, they investigate it. Track A —
Simulate (phases 0–2). Track B — Detect (phases 3–6). Track C — Investigate (phase 7).

## Quality bar (non-negotiable)

- `main` never breaks: every slice runs end-to-end before commit
- pytest + ruff green before every commit; GitHub Actions CI on every push
- every phase ships a **visual artifact**, never just tables
- blue-team code must never read `scheme_labels` (ground truth is for scoring only)

## Roadmap

- [x] **0.1** — repo scaffold, DuckDB ledger schema (4 tables + ground-truth labels), 5 tests, CI, demo command *(2026-07-22)*
- [x] **0.2** — seed loader: 25-customer cast (salaried/business/student/NRI/merchant) + one believable week of life, balance-reconciled, deterministic *(2026-07-22)*
- [x] **0.3** — statement generator v0: any account renders as an HTML bank statement, opening balance derived, `python -m launderlab statement <id>` opens it in browser *(2026-07-23)*
- [x] **0.4** — FCC primer doc: placement → layering → integration mapped to subsystems, grounded in the seeded cast *(2026-07-26)*
- [x] **1.1** — population generator: 10k customer profiles from distributions (not hand-typed), deterministic, segment mix within 0.5pt of target *(2026-07-26)*
- [x] **1.2** — transaction generator at scale: generalized seed.py's patterns over any population, bulk CSV+COPY loader (needed — executemany didn't finish 200k rows in 10 min, COPY does it in 4.5s); real 10k-customer/30-day run: 630,755 transactions in 31.3s, all balances reconciled, all 10,000 accounts active *(2026-07-26)*
- [ ] **1.3** — realism polish backlog (weekday/weekend variation, holidays, more diversity) — parallel/non-blocking, per Dhanush 2026-07-26
- [ ] **Phase 1** (wks 1–2) — World Engine: 10k customers, behavior profiles, clean-traffic realism + histogram visual — engine proven at scale (1.2); polish (1.3) demoted to backlog, not blocking Phase 2
- [x] **2.1** — typology injection engine + structuring: injects into an already-generated account's history, rewrites balance_after globally correct, writes ground truth to `scheme_labels`; proof run — 20 schemes into the 10k-customer world, ₹2.55cr placed, 397 labels, full ledger reconciliation verified *(2026-07-26)*
- [x] **2.2** — mule network / layering: money hops through a chain of accounts (source → mules → sink), each hop skims 3-8%, timestamps strictly increasing; extended balance recompute to multiple accounts per scheme; proof run — 15 schemes into the 10k-customer world, ₹1.41cr entered, 107 labels, global reconciliation verified after touching ~60 accounts *(2026-07-26)*
- [ ] **Phase 2** (wks 3–4) — Typology Injector, 7 typologies (expanded scope): structuring, layering, mule networks, shell companies, round-tripping, dormant-account activation, high-risk geography — each labels ground truth for later precision/recall/false-positive scoring
- [ ] **Phase 3** (wks 4–5) — Rules engine: scenario DSL, alerts, tuning workflow
- [ ] **Phase 4** (wk 6) — Screening: sanctions/PEP fuzzy matching + high-risk geography + adverse media simulation
- [ ] **Phase 5** (wks 7–8) — Graph analytics: mule-ring detection
- [ ] **Phase 6** (wks 8–10) — ML tournament: 6 algorithm families (gradient boosting, isolation forest, one-class SVM, autoencoder, LSTM, GraphSAGE GNN) on one leaderboard, all with explainability; later scored on decay vs the red team
- [ ] **Phase 7** (wks 10–12) — Investigator workbench (FastAPI + React): alert cards with risk score, "why" bullets, AI-generated case summary
- [ ] **Phase 8** (wks 12–14) — Red team co-evolution engine → detection-decay benchmark
- [ ] **Phase 8.5** (wks 15–16) — Multi-bank experiment: quantify the cross-bank blind spot, prototype privacy-preserving sharing, measure lift
- [ ] **Phase 9** (wks 17–18) — Story Mode + whitepaper + demo video + launch

## Slice log

| date | slice | what shipped |
|------|-------|--------------|
| 2026-07-22 | 0.1 | ledger schema (customers, accounts, transactions, scheme_labels), 5 passing tests, CI, `python -m launderlab` demo |
| 2026-07-22 | 0.2 | world seed: 25-person cast, one week of life (~salaries, rent, EMIs via NACH, UPI P2P, merchant footfall, business receipts, GST), two-leg internal payments, no-overdraft rule, 5 new tests |
| 2026-07-23 | 0.3 | statement generator v0 (`statement.py`): HTML statement per account, derived opening balance, CLI `statement <id>` opens in browser; sped up test suite 330s→130s by sharing seeded fixtures instead of reseeding per test; 4 new tests |
| 2026-07-26 | fix | CI broke on ruff 0.16.0's wider default rule set (unrelated to any diff); pinned `[tool.ruff.lint] select` explicitly, verified against 0.16.0 locally |
| 2026-07-26 | 0.4 | `ledger/FCC-PRIMER.md`: placement/layering/integration mapped to subsystems and phases, examples grounded in the seeded cast — Phase 0 complete |
| 2026-07-26 | 1.1 | `world/population.py`: procedural generator for 10k customer profiles (5 segments, lognormal income, weighted cities, deterministic RNG), 6 new tests; verified against a real 10k run (segment mix within 0.5pt of target, median salaried income ₹54,000) |
| 2026-07-26 | 1.2 | `world/generate.py`: generalized seed.py's event patterns (salary/rent/EMI/P2P/merchant/business) over any population; added `ledger.bulk_insert()` (temp CSV + DuckDB COPY, no new dependency) after measuring executemany took 8,224s (2.3h) for 200k rows while COPY does it in 4.5s (1,900x); 8 new tests; real 10k-customer/30-day run: 630,755 transactions in 31.3s, ₹274cr moved, 0 negative balances, all 10,000 accounts active, channel mix 89% UPI |
| 2026-07-26 | 2.1 | `typology/structuring.py`: injects a structuring scheme into an existing account's history, rewriting balance_after via a new `ledger.bulk_update()` (set-based UPDATE...FROM — the UPDATE-side fix for the same executemany overhead) and labeling ground truth in `scheme_labels`; retrofitted `seed.py` onto `bulk_insert` too, cutting the full test suite from ~150s to 29s; 12 new tests (36 total); real proof: 20 schemes injected into the 10k-customer world, ₹2.55cr placed, 397 ground-truth labels, full-ledger reconciliation verified after injection |
| 2026-07-26 | 2.2 | `typology/mule_network.py`: layering typology — money hops through a chain of accounts (source→mules→sink), 3-8% skimmed per hop, timestamps strictly increasing; extracted `ledger.recompute_account_balances()` from structuring.py (now shared, since layering touches multiple accounts per scheme); 8 new tests (44 total); real proof: 15 schemes into the 10k-customer world, ₹1.41cr entered, 107 ground-truth labels, global reconciliation verified after touching ~60 accounts across 15 schemes |

## Rituals

- **"start day"** — read this + last Field Notes entry → agree one slice → build it
- **"close day"** — commit + push, append 3 insights to `ledger/FIELD-NOTES.md` (🏦 FCC, 🔧 engineering, 🎯 interview line)
- **Sunday** — red-vs-blue tournament, metrics snapshot, `/code-review` on the week's diff
- Phase completion → resume bullet into `job hunt/db/profile.md` + LinkedIn post
