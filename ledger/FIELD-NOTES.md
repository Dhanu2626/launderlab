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
