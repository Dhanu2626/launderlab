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

🚧 **Phase 0 — foundations.** The core banking ledger is live. Next: the world engine
that fills it with 10,000 believable customers.

## Quickstart (Windows)

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m launderlab
```

## What gets built

| Subsystem | Purpose |
|---|---|
| S1 World Engine | Agent-based synthetic bank + realistic bank-statement generator |
| S2 Typology Injector | Parameterized laundering schemes from public FATF/FinCEN/RBI advisories |
| S3 Blue Team | Rules engine, sanctions/PEP fuzzy screening, graph analytics, explainable ML |
| S4 Investigator Workbench | Alert queue → entity 360 → link graph → disposition → SAR draft |
| S5 Red Team | Adversary that mutates its schemes each generation to evade detection |
| S6 Metrics | Detection rate, false-positive rate, alert-to-SAR conversion, cost per alert |
| S7 Story Mode | Visual finale: animated money-flow maps, scheme replay, red-vs-blue evolution |

## Ethics

All data is synthetic. All typologies come from public FATF / FinCEN / RBI advisories.
This is defensive tooling — the same category as adversarial testing in security.
Nothing here teaches real-world evasion beyond what regulators themselves publish.
