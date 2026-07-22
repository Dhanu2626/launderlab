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
