# Field notes — the daily learning ledger

Three insights per day: 🏦 FCC domain · 🔧 engineering · 🎯 interview line.

---

## Day 1 — 2026-07-22 · slice 0.1 (ledger schema)

🏦 **FCC:** Real banks never know the ground truth — no table in a production system says
"this transaction was crime." That's why AML tuning is guesswork plus slow feedback from
investigators. LaunderLab's superpower is the `scheme_labels` table: the injector records
exactly which transactions are dirty, so detection quality can be measured precisely.
House rule: the blue team must NEVER read it — only the scorer may.

🔧 **Engineering:** The ledger is append-only with `balance_after` stored on every row
(like a real core-banking system) and indexed on `(account_id, ts)` — because almost every
AML question ever asked is "show me this account's behaviour over time."

🎯 **Interview line:** "I designed a core-banking ledger in DuckDB with a hidden
ground-truth label table, so my detection stack's precision and recall could be measured
exactly — something real FIUs can never do with production data."

---

## Day 2 — 2026-07-22 · slice 0.2 (the first residents)

🏦 **FCC:** "Normal" is segment-relative — that's why real monitoring starts with **peer
groups**. ₹50,000 a day flowing through a kirana store is routine; the same flow through a
student's account is an alarm. Our cast (salaried / business / student / NRI / merchant)
bakes peer groups into the world from day one, so thresholds can differ per segment the
way real banks' scenarios do.

🔧 **Engineering:** DuckDB is a *columnar* (analytics-first) database, and it punished
row-by-row inserts: 508 rows via `executemany` took ~30 seconds because each row pays
constraint-check and storage overhead. Analytical databases want **bulk loads** (Appender
API, Arrow, CSV) — noted as an optimization slice before the 10k-customer world arrives.
Second lesson: internal payments must post **two legs** (payer DR + payee CR) atomically,
or one statement lies.

🎯 **Interview line:** "I hand-crafted a synthetic banking week for 25 customer archetypes —
salaries at 6:30 AM on the 1st, rent on the 2nd, NACH EMIs, UPI P2P, merchant footfall,
GST payments — realistic enough that UPI came out at 80% of transactions by count, matching
real Indian payment mix, without my tuning for it."

---

## Day 3 — 2026-07-23 · slice 0.3 (statement generator)

🏦 **FCC:** A statement's "Opening balance" row is usually never stored anywhere — it's
*derived* by walking backward from the first transaction's balance. Real core-banking
systems do the same trick: balance is a running total, not a stored fact per day. This is
also why investigators trust statements over verbal claims — every number is mechanically
re-derivable from the transaction log, not just asserted.

🔧 **Engineering:** Chased yesterday's flagged slowness and found the real cause: it wasn't
the insert code, it was the *tests* — 9 separate tests each reseeding 508 rows from scratch
(330s total). Only one test (`test_deterministic`) actually needs two independent seed
loads; the rest only read. Sharing one seeded fixture across read-only tests cut the suite
to 130s — a 2.5x win from a one-line fixture-scope change, zero production code touched.
Lesson: profile before optimizing the thing you assume is slow — the insert loop was
innocent; the test setup was guilty.

🎯 **Interview line:** "When my test suite hit 5 minutes, I didn't rewrite the database
layer — I found that 9 tests were redundantly reseeding the same data and fixed the test
fixtures instead, cutting runtime by 60% with a one-line change. Profile before you optimize."

---

## Day 3 (cont'd) — CI went red on its own, days later

🏦 **FCC:** Not a crime lesson, but the same instinct applies: don't trust that something
still works just because it worked before — verify against current reality. That's why
banks re-screen customers periodically instead of trusting KYC done once at onboarding.

🔧 **Engineering:** Pushed slice 0.3, CI failed — but nothing in the diff was wrong.
`pyproject.toml` pinned `ruff>=0.5` (open-ended), and between my last local check and this
push, ruff shipped 0.16.0 with a wider default lint scope, catching 8 "naive datetime"
uses in existing test code that had been fine on 0.15.22. Fixed by pinning
`[tool.ruff.lint] select = [...]` explicitly instead of trusting ruff's defaults to stay
stable — verified by installing 0.16.0 locally and re-running. Lesson: any unpinned
"defaults" (linter rules, dependency majors) are a future CI break waiting to happen; pin
the *behavior* you rely on, not just the package.

🎯 **Interview line:** "My CI failed on a diff I hadn't touched — a linter upgrade had
silently widened its default rule set. Instead of chasing the new violations one by one,
I pinned the lint rule selection explicitly in config, so the build's behavior no longer
depends on whatever a dependency decides is 'default' next."

---

## Day 4 — 2026-07-26 · slice 0.4 (FCC primer doc) — Phase 0 complete

🏦 **FCC:** The three stages aren't equally risky for a criminal — placement is where
amateurs get caught (cash is the most traceable form money ever takes), which is why
professional laundering operations spend the least time in placement and the most in
layering. Layering is also where LaunderLab's "no single bank sees the whole picture"
research thesis lives: a rule or graph confined to one bank is structurally blind to a
chain that hops across banks, no matter how good the model is.

🔧 **Engineering:** Deliberately wrote the primer against our *own* seeded characters
(Suresh Gupta's business account, the DMart/kirana merchants) instead of generic textbook
examples — grounding a concept doc in real rows from `data/launderlab.duckdb` means it'll
stay accurate as the world changes, and it doubles as a sanity check that our cast actually
covers every laundering stage's "camouflage."

🎯 **Interview line:** "I mapped the three classic laundering stages — placement, layering,
integration — directly onto which of my six detection subsystems catches each one, using
real accounts from my own synthetic bank as the worked examples, not textbook abstractions."

**Phase 0 is complete.** Ledger schema, seeded 25-customer world, statement generator, and
the FCC vocabulary are all live and tested. Phase 1 (World Engine at 10k-customer scale)
starts next.

---

## Day 5 — 2026-07-26 · slice 1.1 (population generator, Phase 1 begins)

🏦 **FCC:** Real banks calibrate "normal" from income distributions that are right-skewed —
most customers cluster near the median, a long thin tail runs to very high earners. That
shape matters for AML: a threshold rule tuned on a *symmetric* assumption over-flags the
honest high earners in the tail and under-flags structuring hidden in the crowded middle.
Our generator uses a lognormal distribution specifically to get this shape right — median
salaried income landed at ₹54,000 with a long tail to ₹2 lakh, out of the box.

🔧 **Engineering:** Chose not to add the `Faker` library for realistic names — two plain
lists (40 first names, 24 surnames) combined at random give thousands of plausible unique
combinations for free, no new dependency, and the names stay recognizably Indian instead of
whatever Faker's patchy India locale produces. Ladder rung 3 in practice: stdlib random
already solves this; a dependency would have been unearned complexity. Also deliberately
scoped today to *profiles only*, not transactions — verifying the crowd looks realistic
before building behavior on top of it beats debugging both at once.

🎯 **Interview line:** "I generated a 10,000-customer synthetic population from calibrated
distributions instead of a fixed dataset — lognormal income, weighted city and segment
mix — and verified the output against my target distribution before building any
transaction logic on top of it, so a realism bug couldn't hide inside a detection bug."
