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

---

## Day 6 — 2026-07-26 · slice 1.2 (transactions at scale — the world runs)

🏦 **FCC:** A month, not a week, is the right unit for AML monitoring — most real scenarios
(salary cadence, EMI cycles, rolling structuring windows) only reveal their pattern across
30 days. A week of data can hide a monthly rhythm entirely. That's why Phase 1's acceptance
bar was written as "30 days," and why today's run deliberately generated a full month before
calling the engine done, not just scaling up the row count.

🔧 **Engineering:** Measured before optimizing, again — this time the answer was the
opposite of Day 3's. I benchmarked our existing `executemany` insert path at real scale
(200,000 rows) and it took 8,224 seconds (2.3 hours) to finish — confirmed after the fact, it hadn't hung. Swapped to a temp-CSV + DuckDB `COPY`
approach (pure stdlib `csv` + DuckDB's own bulk loader, zero new dependencies) and the same
200,000 rows loaded in 4.5 seconds — **1,900x faster** (24 rows/sec vs ~44,700 rows/sec). Verified correctness first
(decimals, `NULL`s, timestamps, even a comma inside a narration all round-trip correctly)
before trusting it with real data. The full 10,000-customer, 30-day world — 630,755
transactions, ₹274 crore moved — now generates in 31 seconds. Also generalized every
hand-typed pattern from seed.py (salary, rent, EMI, P2P friends, merchant footfall, business
receipts) into formulas driven by each profile's own segment and income, instead of a human
picking values per person — the same vocabulary, now capable of running at any scale.

🎯 **Interview line:** "My row-by-row insert took 2.3 hours for 200,000 rows. I benchmarked a
temp-CSV-plus-COPY approach using tools I already had — same data, 4.5 seconds, 1,900x
faster, zero new dependencies. I verified the values round-tripped correctly before trusting
it with real data, which caught nothing — but I checked anyway, because 'faster' and
'correct' are two separate claims."

---

## Day 7 — 2026-07-26 · slice 2.1 (typology injector — the crime begins)

🏦 **FCC:** Structuring only works as camouflage if it hides among *genuine* cash activity —
that's why the injector targets business/merchant accounts specifically, the same insight
FCC-PRIMER.md flagged on Day 4 ("high genuine cash turnover is the perfect camouflage").
Today's worked example, MEHTA TRADERS: 34 real business receipts already in its history,
19 structuring deposits added among them — 36% of its rows are now dirty, and nothing about
any single row gives it away. That's the actual difficulty of AML monitoring in one account.

🔧 **Engineering:** Injecting a scheme into an *already-generated* ledger is harder than
generating one from scratch — every transaction on the target account that comes after the
injection point needs its running balance recalculated, and I initially rewrote those
balances with the same row-by-row `executemany` pattern Day 6 had just proven was slow.
It showed: 2.64s for just 60 rows (~24 rows/sec — the exact same ceiling, on UPDATE this
time, not INSERT). Built `bulk_update()` — load the new values into a temp table via the
existing `bulk_insert`, then one set-based `UPDATE ... FROM` join — and the same call
dropped to 0.9s. While fixing it, I noticed `seed.py` never got the Day 6 fix since it
wasn't the bottleneck back then — retrofitting it cut the *entire test suite* from ~150s to
29s. Same lesson as Day 3, opposite direction: once you've found a real bottleneck pattern,
check every place it might be hiding, not just the one that paged you.

🎯 **Interview line:** "Rewriting a ledger's running balances after a mid-history insert hit
the exact same row-by-row UPDATE bottleneck I'd just fixed for INSERT the day before — so I
generalized the fix into a reusable bulk_update helper instead of patching it locally, then
went back and found the same slow pattern sitting untouched in code I'd written days earlier.
Cut my test suite runtime by 5x as a side effect of fixing a correctness path, not a
performance path."

---

## Day 8 — 2026-07-26 · slice 2.2 (mule networks — the trail gets buried)

🏦 **FCC:** Structuring is a *one-account* crime; layering is fundamentally a *pattern
across accounts* — no single row, and no single account's history, looks wrong. Today's
real chain: Karthik Kumar received ₹10 lakh from a shell company, forwarded 92.5% to Manoj,
who forwarded 93.5% to Praveen, who forwarded 94% to Lakshmi — all inside 27 hours. A rule
watching any *one* of those four accounts sees one ordinary transfer. The crime only exists
in the edges connecting them, which is exactly why Phase 5 (graph analytics) has to exist —
per-account rules are structurally blind to it, a fact FCC-PRIMER.md called out on Day 4 and
today made concrete with real data instead of a claim.

🔧 **Engineering:** Structuring only ever touched one account, so its balance-recompute
logic was written as a single-account function. Layering fundamentally can't work that
way — money crosses multiple accounts, so *every* account in the chain needs its own
history replayed and rewritten. Extracting `recompute_account_balances()` out of
structuring.py into `ledger.py` before writing the new typology meant the multi-account
version was just "call it once per account in the chain" — no new balance logic to get
wrong. Second reuse win: DuckDB doesn't persist a UPI-ID (VPA) column anywhere — it only
ever existed as an in-memory field during generation — so realistic counterparty narrations
for newly-injected transactions have to be synthesized from the account's stored name at
injection time, the same pattern population.py already used to build them the first time.

🎯 **Interview line:** "My first typology only ever touched one account, so I wrote its
balance-recompute logic as single-account by default. Before writing the second typology —
which by definition crosses multiple accounts — I extracted that logic into a shared
function first, so the harder multi-account version was composition, not new code to debug."

---

## Day 9 — 2026-07-26 · slice 2.3 (shell companies — integration)

🏦 **FCC:** Structuring's tell is *many small* amounts; a shell company's tell is the exact
opposite — *few large* amounts, all from one counterparty a business has never dealt with
before, often with suspiciously sequential invoice numbers. Real investigators watch
**counterparty concentration**: what share of a business's revenue comes from its single
biggest customer this month? A legitimate business is diversified; a shell-fed one isn't.
This typology exists specifically to make that concentration signal show up in real data
Phase 6's ML tournament can later learn to detect.

🔧 **Engineering:** Caught a real bug in code review before it ever ran: my first version
split a total into pieces by drawing n-1 random amounts and computing the last piece as
"whatever's left" — total minus the sum of the others. For a *few large* pieces (as few as
3, up to 8), enough of those random draws landing near their upper bound could push the
subtracted remainder negative, which the database would then reject outright (amounts must
be positive). Rewrote it as a proportional weighted split instead — every piece is a
fraction of a shared weight pool that always sums to less than the total by construction,
so the last piece can never go negative, no matter how unlucky the random draws get. Proved
it with a 1,400-case stress test (200 seeds × 7 group sizes) rather than trusting the math
by eye — this is exactly the kind of edge case that passes 99% of test runs and then fails
in front of someone months later.

🎯 **Interview line:** "I found a rare-but-real bug in my own split algorithm before it ever
shipped — a subtracted-remainder approach that could go negative under unlucky random
draws — and replaced it with a proportional weighted split that's negative-proof by
construction, then proved it with a 1,400-case stress test instead of trusting the math."

---

## Day 10 — 2026-07-26 · slice 2.4 (round-tripping — a genuine bug, caught and fixed)

🏦 **FCC:** Round-tripping is the odd one out among the four typologies built this batch:
its whole signature is money that *leaves and comes back*, usually slightly inflated. Real
investigators use it to catch businesses inflating apparent turnover — the money never did
any real economic work, it just went on a round trip through a shell entity and returned a
few percent heavier, making the books look like the business is growing when it isn't.

🔧 **Engineering — today's real bug:** Every other typology so far only ever *adds* credit
before debiting it (mule hops: CR always precedes DR; structuring: pure credits), so an
overdraft was structurally impossible. Round-tripping is different — its first leg debits
money the account *already has*, so I had to actively prove it could never overdraw. I wrote
a safety cap (departure ≤ 60% of the account's historical minimum balance) with a clean
mathematical proof, then ran a 50-injection stress test to check it — and it failed on the
third injection into one account with a genuine negative balance. The bug: my "historical
minimum" only scanned `min(balance_after)` — every balance *after* a transaction — but never
considered the balance *before* the account's very first transaction (the opening balance
itself). A newly injected departure landing earlier in time than every existing row becomes
the new first transaction, computed straight against that opening balance — which my safety
margin had never checked. Fixed by folding the opening balance into the minimum. The lesson
that matters isn't the bug — proofs have edge cases — it's that I wrote the proof *and*
tested it against real conditions instead of trusting either one alone. The proof told me
the shape of the fix; the stress test told me the proof was incomplete.

🎯 **Interview line:** "I wrote a mathematical safety proof for a debit that could never
overdraw an account, then stress-tested it anyway with 50 injections across 10 accounts —
and it failed. The bug: my 'historical minimum' calculation only checked balances *after*
transactions, missing the balance *before* the very first one. A proof and a test that only
agree with each other prove nothing; they have to agree with reality."
