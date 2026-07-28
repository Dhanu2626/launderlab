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

✅ **Phase 0 — foundations complete.** Core ledger, a 25-customer seeded world with one
believable week of life, and a bank-statement generator are live. See
[`ledger/FCC-PRIMER.md`](ledger/FCC-PRIMER.md) for the money-laundering concepts every
later phase builds against. Next: **Phase 1**, the world engine at 10,000-customer scale.

## Quickstart (Windows)

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m launderlab seed
.venv\Scripts\python -m launderlab statement A001
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
| Sanctions / PEP screening | 100% | 29.4% |
| Adverse media | 100% | 3.7% |

The low precision is the finding, not a defect. Every false positive scored **≥0.986** —
none were sloppy matches. Six were customers *genuinely named* the same as a listed PEP, and
thirty were transliteration-equivalents of a sanctioned name. Nothing in a name separates
those people, which is exactly why real banks screen on date of birth and nationality too,
and why alert triage is where AML teams spend their hours. This is the project's
"false-positive crisis" research thesis reproduced as a measurement rather than a citation.

Caveat kept next to the number: this world generates only 1,049 distinct names across
10,000 customers, so name collisions are denser here than in a real bank. Widening the name
pool is tracked in `PROJECT.md`.

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
