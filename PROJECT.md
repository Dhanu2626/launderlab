# LaunderLab — project operating doc

Read this file + the last Field Notes entry at "start day".
Full 16-week plan: `../LAUNDERLAB-PLAN.md` (CareerForge root).

## Quality bar (non-negotiable)

- `main` never breaks: every slice runs end-to-end before commit
- pytest + ruff green before every commit; GitHub Actions CI on every push
- every phase ships a **visual artifact**, never just tables
- blue-team code must never read `scheme_labels` (ground truth is for scoring only)

## Roadmap

- [x] **0.1** — repo scaffold, DuckDB ledger schema (4 tables + ground-truth labels), 5 tests, CI, demo command *(2026-07-22)*
- [ ] **0.2** — seed loader: ~25 hand-crafted customers + one believable week of transactions
- [ ] **0.3** — statement generator v0: render any account as an HTML bank statement
- [ ] **0.4** — FCC primer doc: placement → layering → integration mapped to subsystems
- [ ] **Phase 1** (wks 1–2) — World Engine: 10k customers, behavior profiles, clean-traffic realism + histogram visual
- [ ] **Phase 2** (wks 3–4) — Typology Injector: structuring, mule chain, shell layering (YAML-driven)
- [ ] **Phase 3** (wks 4–5) — Rules engine: scenario DSL, alerts, tuning workflow
- [ ] **Phase 4** (wk 6) — Screening: sanctions/PEP fuzzy matching
- [ ] **Phase 5** (wks 7–8) — Graph analytics: mule-ring detection
- [ ] **Phase 6** (wks 8–9) — ML scorer with SHAP explanations
- [ ] **Phase 7** (wks 10–12) — Investigator workbench (FastAPI + React)
- [ ] **Phase 8** (wks 12–14) — Red team co-evolution engine
- [ ] **Phase 9** (wks 15–16) — Story Mode + whitepaper + demo video + launch

## Slice log

| date | slice | what shipped |
|------|-------|--------------|
| 2026-07-22 | 0.1 | ledger schema (customers, accounts, transactions, scheme_labels), 5 passing tests, CI, `python -m launderlab` demo |

## Rituals

- **"start day"** — read this + last Field Notes entry → agree one slice → build it
- **"close day"** — commit + push, append 3 insights to `ledger/FIELD-NOTES.md` (🏦 FCC, 🔧 engineering, 🎯 interview line)
- **Sunday** — red-vs-blue tournament, metrics snapshot, `/code-review` on the week's diff
- Phase completion → resume bullet into `job hunt/db/profile.md` + LinkedIn post
