# LaunderLab — project operating doc

Read this file + the last Field Notes entry at "start day".
Full 18-week plan: `../LAUNDERLAB-PLAN.md` (CareerForge root).

## Research thesis — three unsolved problems we attack

1. **Detection decay** — how fast does a detection stack rot against an adapting adversary? (Phase 8 benchmark; exists nowhere today)
2. **False-positive economics** — cost-per-true-alert measured for every detection config, not guessed (Phases 3–6)
3. **The cross-bank blind spot** — quantify what single banks can't see in multi-bank mule chains, then measure the lift from privacy-preserving co-operation (Phase 8.5; BIS Project Aurora does this privately — no open version exists)

## Quality bar (non-negotiable)

- `main` never breaks: every slice runs end-to-end before commit
- pytest + ruff green before every commit; GitHub Actions CI on every push
- every phase ships a **visual artifact**, never just tables
- blue-team code must never read `scheme_labels` (ground truth is for scoring only)

## Roadmap

- [x] **0.1** — repo scaffold, DuckDB ledger schema (4 tables + ground-truth labels), 5 tests, CI, demo command *(2026-07-22)*
- [x] **0.2** — seed loader: 25-customer cast (salaried/business/student/NRI/merchant) + one believable week of life, balance-reconciled, deterministic *(2026-07-22)*
- [x] **0.3** — statement generator v0: any account renders as an HTML bank statement, opening balance derived, `python -m launderlab statement <id>` opens it in browser *(2026-07-23)*
- [ ] **0.4** — FCC primer doc: placement → layering → integration mapped to subsystems
- [ ] **Phase 1** (wks 1–2) — World Engine: 10k customers, behavior profiles, clean-traffic realism + histogram visual
- [ ] **Phase 2** (wks 3–4) — Typology Injector: structuring, mule chain, shell layering (YAML-driven)
- [ ] **Phase 3** (wks 4–5) — Rules engine: scenario DSL, alerts, tuning workflow
- [ ] **Phase 4** (wk 6) — Screening: sanctions/PEP fuzzy matching
- [ ] **Phase 5** (wks 7–8) — Graph analytics: mule-ring detection
- [ ] **Phase 6** (wks 8–10) — ML tournament: 6 algorithm families (gradient boosting, isolation forest, one-class SVM, autoencoder, LSTM, GraphSAGE GNN) on one leaderboard, all with explainability; later scored on decay vs the red team
- [ ] **Phase 7** (wks 10–12) — Investigator workbench (FastAPI + React)
- [ ] **Phase 8** (wks 12–14) — Red team co-evolution engine → detection-decay benchmark
- [ ] **Phase 8.5** (wks 15–16) — Multi-bank experiment: quantify the cross-bank blind spot, prototype privacy-preserving sharing, measure lift
- [ ] **Phase 9** (wks 17–18) — Story Mode + whitepaper + demo video + launch

## Slice log

| date | slice | what shipped |
|------|-------|--------------|
| 2026-07-22 | 0.1 | ledger schema (customers, accounts, transactions, scheme_labels), 5 passing tests, CI, `python -m launderlab` demo |
| 2026-07-22 | 0.2 | world seed: 25-person cast, one week of life (~salaries, rent, EMIs via NACH, UPI P2P, merchant footfall, business receipts, GST), two-leg internal payments, no-overdraft rule, 5 new tests |
| 2026-07-23 | 0.3 | statement generator v0 (`statement.py`): HTML statement per account, derived opening balance, CLI `statement <id>` opens in browser; sped up test suite 330s→130s by sharing seeded fixtures instead of reseeding per test; 4 new tests |

## Rituals

- **"start day"** — read this + last Field Notes entry → agree one slice → build it
- **"close day"** — commit + push, append 3 insights to `ledger/FIELD-NOTES.md` (🏦 FCC, 🔧 engineering, 🎯 interview line)
- **Sunday** — red-vs-blue tournament, metrics snapshot, `/code-review` on the week's diff
- Phase completion → resume bullet into `job hunt/db/profile.md` + LinkedIn post
