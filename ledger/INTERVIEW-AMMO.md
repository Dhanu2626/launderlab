# Interview ammo — harvested lines

One STAR-ready sentence per day, appended at the bottom. Use these verbatim in interviews.

- 2026-07-22 — "I designed a core-banking ledger in DuckDB with a hidden ground-truth label table, so my detection stack's precision and recall could be measured exactly — something real FIUs can never do with production data."
- 2026-07-22 — "I hand-crafted a synthetic banking week for 25 customer archetypes — salaries, rent, NACH EMIs, UPI P2P, merchant footfall, GST — realistic enough that UPI came out at 80% of transactions by count, matching real Indian payment mix, without my tuning for it."
- 2026-07-23 — "When my test suite hit 5 minutes, I didn't rewrite the database layer — I found that 9 tests were redundantly reseeding the same data and fixed the test fixtures instead, cutting runtime by 60% with a one-line change. Profile before you optimize."
- 2026-07-26 — "My CI failed on a diff I hadn't touched — a linter upgrade had silently widened its default rule set. Instead of chasing the new violations one by one, I pinned the lint rule selection explicitly in config, so the build's behavior no longer depends on whatever a dependency decides is 'default' next."
- 2026-07-26 — "I mapped the three classic laundering stages — placement, layering, integration — directly onto which of my six detection subsystems catches each one, using real accounts from my own synthetic bank as the worked examples, not textbook abstractions."
