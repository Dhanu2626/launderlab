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

---

## Day 11 — 2026-07-26 · slice 2.5 (dormant-account reactivation)

🏦 **FCC:** The red flag here isn't the transaction amount in isolation — ₹15 lakh moving
through a business account is unremarkable. It's the amount **relative to that specific
account's own established baseline**. A student who's moved ₹4,000-8,000 a week for a
month, then suddenly receives ₹2 lakh and cashes out 95% of it within hours, is the same
signal a bank's fraud team calls "behavioral deviation" — and it's exactly the kind of
pattern a rules engine checking fixed thresholds misses (₹2 lakh isn't huge for a business)
but a model trained on each account's own history catches immediately. That per-account
baseline framing is precisely what Phase 6's ML tournament exists to formalize.

🔧 **Engineering:** Two small, honest wins today rather than a big new lesson. First:
this typology's credit-then-debit ordering makes it safe by construction the same way
mule_network is — no need for round_tripping's harder historical-minimum proof, because the
debits only ever spend money that was *just* credited, never pre-existing balance. Picking
the right *shape* of typology (credit precedes debit vs. debit against existing funds)
matters more than being clever about safety margins after the fact. Second: `shell_company`'s
private split helper got used by a second typology today, so I promoted it to a shared,
public function instead of leaving two typologies quietly depending on "internal" code —
a small refactor, but the kind that keeps a codebase honest as it grows past what any one
person can hold in their head.

🎯 **Interview line:** "The right question wasn't 'how do I prove this debit is safe' — it
was 'can I design the transaction order so the question never comes up.' Structuring credit
before debit turned an entire class of overdraft bugs from something I had to prove into
something that couldn't happen."

---

## Day 12 — 2026-07-26 · slice 2.6 (high-risk geography — Phase 2 complete)

🏦 **FCC:** This is the odd one out among all seven typologies: the "tell" isn't a pattern
across many transactions, it's purely **which country** the counterparty sits in. A single,
completely ordinary-looking wire transfer becomes notable only because of a geography tag —
which is exactly why real screening systems (Phase 4) keep a sanctions/high-risk-country list
as a separate check layered on top of behavioral rules, not folded into them. Same amount,
same channel, same everything else — the only difference between "unremarkable" and
"file a SAR" is a lookup against a list that has nothing to do with the transaction itself.

🔧 **Engineering — a bug my own stress test almost let through:** I built a stress test on
Day 10 and reused the same pattern here: many accounts, many seeds, check the minimum
balance never goes negative. It passed — but only because I'd narrowed the test to business
accounts, matching the OTHER typologies' pattern. The real proof run (which targets business
*and* NRI accounts, since NRI accounts genuinely receive international remittances) found a
negative balance immediately. The actual bug: this typology can inject up to 3 transactions
per call, some fraction randomly outbound. I capped each outbound leg independently at the
same safety ceiling — but if two or three land as outbound in one call, each draws
*independently* from the same margin instead of *sharing* it, so their combined effect can
sail straight past the limit that was supposed to hold for all of them together. Fixed by
spending down one shared budget across the whole call instead of resetting it per row —
then rewrote the stress test to force the worst case (3 transactions, every call, NRI
accounts included) instead of hoping default randomness would find it. The uncomfortable
lesson: a stress test that passes only proves what it happened to try. Today's real proof
run — which exists purely to generate a demo number — caught a bug 67 passing tests missed,
because it was the first thing that actually matched production usage (mixed segments,
default parameters) instead of the narrower shape my unit tests assumed.

🎯 **Interview line:** "My unit test suite had 67 passing tests, including a dedicated
overdraft stress test, and none of them caught a real bug — because the stress test only
covered business accounts, matching every other typology's pattern, and the actual bug
needed NRI accounts plus multiple debit legs in one call to surface. It was my own
'real-world proof run,' not the test suite, that caught it. Now I treat the proof run as a
test in its own right, not just a demo number — and I made the unit test match what broke
it, not just what I originally guessed would."

**Phase 2 is complete.** All 7 typologies — structuring, mule networks/layering, shell
companies, round-tripping, dormant-account reactivation, and high-risk geography — are
built, tested, and proven at 10k-customer scale, each writing real ground truth to
`scheme_labels`. Three real bugs were found and fixed along the way (Days 9, 10, 12), all
via the same discipline: prove it, then try to break the proof with real conditions.

---

## Day 13 — 2026-07-26 · Phase 2 capstone (proving composability, not just correctness)

🏦 **FCC:** Real financial crime rarely uses one typology in isolation — a business
laundering money might structure cash deposits, receive shell-company invoices, AND
round-trip funds, all in the same month, on the same account. Today's capstone deliberately
recreated that: the same 5 business accounts got structuring, shell-company payments, and
round-tripping injected simultaneously. One account (real example: MEHTA TRADERS, already
familiar from Day 7) ended up with 34 genuine transactions plus 20 injected across 3
different crime types — 54 rows total, every balance still exactly correct. That's a far
more realistic "suspicious account" than any single typology alone could produce, and it's
exactly the shape of case Phase 7's investigator workbench will eventually have to untangle.

🔧 **Engineering:** Every typology this batch was tested *alone* — thoroughly, with stress
tests that twice caught real bugs (Days 10 and 12). But "each typology works in isolation"
and "all typologies work together" are different claims, and nothing before today actually
tested the second one. Today's capstone does: inject all six onto deliberately overlapping
accounts, then re-verify the *entire* ledger — not just the accounts touched by any one
typology — reconciles. It passed cleanly, which is itself informative: the safety
guarantees built typology-by-typology (credit-before-debit ordering, the shared
`account_true_minimum` proof) turned out to compose correctly without needing any
typology to know about the others. Good isolation in the design paid for itself here. I
also committed this capstone as a permanent test, not just a one-off proof script — it's
exactly the kind of check that would have caught this batch's Day-12 bug immediately if it
had existed first, so it stays as a standing regression guard against that whole class of
interaction bug for every typology built from here on.

🎯 **Interview line:** "Every typology I built passed its own tests in isolation. Before
calling the phase done, I ran a capstone that deliberately overlapped all six on the same
accounts and re-verified the entire ledger, not just the parts each typology touched. It
passed — which told me the safety properties I'd designed typology-by-typology actually
composed, instead of just assuming they would. Then I kept that capstone as a permanent
test, since 'works alone' and 'works together' are genuinely different claims that need
separate proof."

**Five-day batch summary (Days 9–13): six new typologies, three real bugs found and fixed,
one shared safety-utility library extracted (`account_true_minimum`, `safe_debit_ceiling`,
`recompute_account_balances`, `split_uneven`), 72 tests (up from 36), and a capstone proving
the whole system composes. Phase 2 — the entire crime-injection engine — is done.**

---

## Phase 3 — 2026-07-26 (rules engine — the first real detector)

🏦 **FCC:** Every phase before this one generated data. This is the first code that has to
*catch* something, and it immediately surfaced the industry's actual central problem in
miniature: I built `round_trip` to catch money leaving and returning to an account, and on
a first pass it flagged 24 completely legitimate businesses on a clean world — because a
purchase debit followed by an unrelated receipt credit within days is *routine* business
cash flow, not crime. The fix wasn't a bigger amount threshold (that would have cost
recall); it was noticing that the injected typology always moves over RTGS specifically,
while ordinary business AP/AR never does in this world. That's the real skill AML tuning
demands: finding the feature that's actually diagnostic, not just cranking a threshold
until the noise goes quiet — because a big-enough threshold silences noise by also going
blind to real cases (dormant_reactivation's honest 60% recall, further down, is the same
lesson from the other direction).

🔧 **Engineering:** Enforced a real architectural boundary, not just a documented one:
`detect/rules.py` must never read `scheme_labels`, and `detect/scoring.py` is the only
module allowed to grade against it — a rule earns its alert from transaction data alone,
the same way a real analyst would, never from peeking at the answer key. Tested this with a
static check (no `FROM`/`JOIN scheme_labels` anywhere in rules.py's source), not just a
comment. Also skipped writing an actual textual "scenario DSL" parser — the plan's own
language — since six Python functions with named, tunable keyword parameters already give
a declarative, inspectable configuration surface without inventing a mini-language nobody
but me would ever write in. Ladder rung reasoning made explicit: build the parser only if a
second, non-me author of scenarios ever actually shows up.

🎯 **Interview line:** "My first version of a money-laundering detection rule flagged 24
legitimate businesses out of 300 on a clean dataset. Instead of raising the amount
threshold — which would have cost real recall — I found the channel the injected crime
specifically used that ordinary business cash flow never does, and filtered on that. Real
10,000-customer proof: 93.3% recall, 100% precision, 0% false positives across 90 injected
schemes, exceeding the ≥80%/<5% target — with one typology honestly reported at 60%
recall and a concrete, defensible reason why, rather than hidden or averaged away."

---

## Phase 4 — 2026-07-28 (screening — where the false-positive crisis becomes a number)

🏦 **FCC:** Phase 3's rules engine scored 100% precision, which quietly flattered the whole
project. Phase 4 is where the industry's actual, famous problem shows up and refuses to be
tuned away: **29.4% precision on sanctions/PEP screening, and 3.7% on adverse media.** Both
legs found 100% of what was planted — recall was never the issue. The issue is that names
are not identifiers. Six customers in the world are genuinely called "Suresh Gupta", which
is also a listed PEP; thirty more are called "Farhan Ali", a transliteration-equivalent of
sanctioned "Farhaan Ali". No matching algorithm can separate those people, because *there
is nothing in a name to separate them by*. That is precisely why real banks screen against
date of birth and nationality, not names alone, and why the alert-triage floor of a real
FIU is full of humans reading passports. The 95%-false-positive statistic in this project's
own research thesis stopped being a citation this phase and became a measurement.

🔧 **Engineering:** Three findings, each from measuring rather than assuming. First, I very
nearly shipped a matcher that used whole-string Jaro-Winkler — it scored "Suresh Kumar" vs
"Suresh Gupta" at 0.900, above any workable threshold, because Jaro-Winkler weights a shared
prefix heavily and both share a first name. Dropping whole-string comparison for pure
token alignment fixed it (0.73) without touching real transliterations (0.95+) — the rare
change that is simultaneously less code and more accurate. Second, the requested
Double Metaphone **does not exist in jellyfish** (it ships `metaphone`, `soundex`, `nysiis`,
`match_rating_codex`), and when I benchmarked all of them, the `nguyen/nuyen` case the
original `ponytail:` comment specifically named was missed by *every* phonetic algorithm and
caught cleanly by Jaro-Winkler at 0.950 — so the honest architecture is JW primary, Metaphone
corroborating, rather than adding a second phonetics library to satisfy the letter of the
note. Third, and most important: before reporting 29.4% precision as an industry insight, I
checked whether it was my own bug — and found every false positive scored ≥0.986, meaning
zero were sloppy matches. But I also found the world generates only 1,049 distinct names for
10,000 customers, so collision density is exaggerated. Both facts are now in PROJECT.md,
because a number this quotable is exactly the kind that deserves its caveat attached.

🎯 **Interview line:** "My name-screening engine hit 100% recall and 29% precision — and
before I reported that as evidence of the industry's false-positive problem, I checked
whether it was just my bug. Every false positive scored above 0.98, so none were sloppy
matches; they were six customers genuinely sharing a listed PEP's name and thirty sharing a
sanctioned person's transliteration. No algorithm separates those — that's what date of
birth and nationality are for. I also found my own world generator over-concentrated names,
which inflates the effect, and wrote that caveat next to the number rather than letting the
better-sounding version stand."

---

## Phase 4, slice 4.2 — 2026-07-28 (turning a caveat into a measurement)

🏦 **FCC:** Phase 4 reported 29.4% screening precision and called it the false-positive
crisis made real. It was half true, and the half that wasn't is the more useful lesson.
Widening the world's name pool from 1,000 to 23,160 combinations — nothing else changed,
same seeds, same planted entities — moved precision to **75.0%** and dropped exact-same-name
false positives from six to **zero**. So **86% of that dramatic number was an artefact of my
own data**, and only **14% was the real phenomenon. The real phenomenon is still there** —
five transliteration-equivalent names survive, and no algorithm separates those from the
genuine entity. But the honest headline is much narrower than the first one, and the
narrower version is the one that would survive an interviewer pushing back.

🔧 **Engineering:** The design decision that made this possible was small and worth
repeating: when widening the lists, I appended the new names *after* the originals rather
than replacing or reshuffling them. That meant the narrow arm could be reproduced exactly by
slicing `FIRST_NAMES[:40]` and `SURNAMES[:25]`, so the two arms were a genuine controlled
comparison rather than two unrelated worlds that happened to differ in several ways at once.
It cost nothing at the time and turned an unanswerable "how much of this is my fault?" into
a two-line experiment. Also worth recording: I predicted 60–80% entity precision (actual
75.0% — fine) and 30–40% media precision (actual 15.8% — I was too optimistic, because each
trap article still name-matches about four customers even in the wide pool). Writing the
prediction down before running it is what made the miss visible instead of invisible.

🎯 **Interview line:** "I published a 29% precision figure as evidence of AML's
false-positive problem, then went back and tested whether my own synthetic data had
manufactured it. Widening the name pool — one variable, same seeds — moved precision to 75%
and took exact-name collisions to zero. So I could say precisely that 86% of my headline
number was an artefact and 14% was the real effect. I'd rather own a smaller number I can
defend than a dramatic one I can't."

---

## Phase 5 — 2026-07-28 (graph analytics — and the blind spot it measures)

🏦 **FCC:** The graph did what it was built to do: 15 of 15 mule networks reconstructed as
complete paths, no false positives. Phase 3's per-account rule had already flagged 47 of the
62 accounts involved — but flagging accounts is not the same as knowing they form a chain.
"Account A looks odd" is 62 separate alerts an analyst triages one by one; "money moved
A→B→C→D over 27 hours, losing 6% a hop" is one case with a narrative. That difference is the
entire argument for graph analytics, and it is now measured rather than asserted.

The more important number is the one the graph *couldn't* see. Of the six injected
typologies, **only layering produced any internal edges at all** — structuring, shell
companies, round-tripping, dormant reactivation and high-risk geography all scored 0 of 15
visible. Not because the algorithm failed, but because their counterparties bank somewhere
else: a cash deposit, an offshore invoice or an inbound remittance leaves one leg in this
ledger and nothing to connect it to. A bank's graph can only ever see the part of a network
that happens to sit inside it. That is the cross-bank blind spot from this project's research
thesis, no longer a paragraph in a plan but a measured 1-in-6, and it is precisely what
Phase 8.5's multi-bank experiment exists to quantify further.

🔧 **Engineering:** Two corrections found by looking at output rather than trusting design.
First, edge reconstruction: pairing DR and CR legs on (timestamp, amount) seemed obviously
right and produced obviously wrong edges, because unrelated payments that coincide get
cross-joined. Both legs of a real payment share a reference number in the narration — that
is the only field that identifies *one* payment, and switching to it fixed the graph. Second,
5 planted chains were reported as 13: growing paths from every edge rediscovers a long chain
starting from its 2nd account, its 3rd, and so on. Collapsing chains that are contiguous
fragments of longer ones took it back to exactly 5. Neither bug would have failed a naive
test — both were only visible by reading the actual output and asking whether the number made
sense. Also removed the fan-in/fan-out detectors I had just written: measured, they fired
zero times at usable thresholds and, loosened until they fired, returned 72 merchants out of
76 hits. A detector that has never detected anything is decoration; it can come back when
a fan-shaped typology exists to justify it.

🎯 **Interview line:** "My graph layer reconstructed all 15 mule networks with no false
positives — but the number I'd actually lead with is that five of my six laundering
typologies were invisible to it, because their counterparties banked elsewhere and left no
edge to analyse. Graph analytics only sees the fraction of a network that sits inside your
own institution. I also deleted the fan-in detector I'd just written, because when I measured
it, every hit was a legitimate shop."

---

## Phase 6, slice 6.1 — 2026-07-29 (the ML tournament, and what it actually measured)

🏦 **FCC:** The leaderboard's headline is not which model won — it is that **they fail
differently**. Isolation forest caught every shell-company account (8/8) and every
structuring account (5/5), but only 7 of 18 layering accounts. One-class SVM caught 18/18
layering. An institution running one model is blind wherever that model happens to be weak,
and nothing in its own metrics would reveal the gap — you only see it when ground truth
lets you break recall down by crime type, which no real bank can do. That is the entire
argument for a tournament rather than a champion, and it is the argument this project can
make and a real FIU cannot.

The second lesson is harsher. Making the world *more realistic* made detection *worse* —
correctly. Giving businesses legitimate cash banking took Phase 3's structuring rule from
zero false positives to twenty-four, which means its perfect precision had never been a
property of the rule at all; it was a property of a world where nobody legitimately banked
cash. Structuring is hard in reality precisely because honest shops deposit sub-threshold
cash all day. After re-tuning, small structuring schemes are now genuinely undetectable by
that rule — recorded as a test, not hidden.

🔧 **Engineering:** Gradient boosting scored a perfect AP of 1.000, which is a red flag,
not a triumph. Perfect ranking almost always means a feature encodes the label. It did: the
legitimate world emitted **no CASH and no INT transactions whatsoever**, so both channels
existed only inside injected crime, and the model had learned "channel = CASH" rather than
anything about laundering. Two world fixes later (remittances retagged INT; merchants and
businesses banking real cash), a feature-importance audit still shows three features
carrying 98.6% of the signal — `std_amount` alone at 67.8% — meaning the model is largely
detecting "this account moved unusually large money for this world". So the supervised
number is still not a credible AML result, and I have written that next to it rather than
publishing 1.000 unqualified. The judgement call that follows: **do not add LSTM and
GraphSAGE yet.** Adding two more models to a benchmark that is measuring an artefact just
produces two more inflated numbers. Fix the world's amount realism first.

🎯 **Interview line:** "My supervised model hit a perfect average precision, so I went
looking for the bug instead of celebrating. The synthetic world had never generated a
legitimate cash or international transaction, so the model had learned 'cash equals crime'.
I fixed the data — and that immediately broke my earlier rules engine, taking it from zero
false positives to twenty-four, which told me its perfect precision had been an artefact
too. I'd rather have a benchmark I can defend than a leaderboard that flatters me."

---

## Phase 6, slices 6.2 + 6.3 — 2026-07-29 (fixing the benchmark, then finishing the tournament)

🏦 **FCC:** Making the world honest made every detector worse, and that is the finding.
Giving the bank legitimate large payments — property purchases, loan disbursals, one-client
suppliers, NRI property remittances — collapsed the unsupervised models: one-class SVM fell
from 0.910 to 0.219, isolation forest from 0.395 to 0.155. They had been riding a single
assumption, that *anomalous* means *large*, and it held only while the honest population had
no upper tail. Real banking has an enormous one. This is why unsupervised anomaly detection
disappoints in production AML: when normal is genuinely heterogeneous, "unusual" stops
meaning "criminal". Supervised learning held up far better (0.925) because it learns what
distinguishes crime, not merely what is rare.

The harder lesson was `counterparty_concentration`. Measured against the realistic world,
shell-company schemes sit at 6 payments and 50% concentration — *inside* the legitimate
range, where real businesses with one dominant client run 5-9 payments at 51-63%. There is
no threshold that separates them, and there should not be: "most of my revenue comes from
one customer" describes an honest supplier and a shell-fed front identically. That rule is
now documented as producing genuine false positives, with the clean-world test asserting a
bounded, triageable alert load instead of silence. Some things are not tunable.

🔧 **Engineering:** Two design choices worth keeping. First, personal big-ticket spending is
modelled as a funding credit followed days later by the purchase — not a bare debit. A bare
debit of 3-22x salary would simply have been refused by the no-overdraft rule and never
appeared in the data at all, so the "fix" would have silently done nothing; and the funding
credit is itself the thing that stops large incoming payments from being an automatic crime
signal. The 3-10 day gap is deliberate too, sitting outside the 48h rapid-pass-through
window so buying a flat does not look like moving money onward. Second, GraphSAGE is ~15
lines of plain PyTorch rather than a torch-geometric dependency: aggregate neighbours,
concatenate with self, transform. Writing the layer is more transparent than importing it,
avoids a large fragile dependency for one idea, and CPU-only torch is ~200MB against ~2.5GB
for the CUDA build — these models are far too small to want a GPU.

🎯 **Interview line:** "I fixed my synthetic data and watched three of my four models get
dramatically worse — one-class SVM fell from 0.91 to 0.22. That was the point: they had
learned that anomalous means large, which only worked while my honest population had no big
legitimate transactions. Real banks have an enormous upper tail, which is exactly why
unsupervised anomaly detection underdelivers in production AML. I'd rather have models that
score lower against realistic data than models that score well against data I made easy."

---

## Phase 7, slice 7.1 — 2026-07-29 (risk aggregation, and a negative result)

🏦 **FCC:** The combined risk score does not rank better than the single best detector. At an
alert budget of 25 it is actually *worse* than the ML model alone — 0.800 precision against
0.840 — because screening drags it down. That is worth saying plainly rather than burying:
the reason to aggregate is not accuracy, it is that an analyst opening an alert needs to see
*why*, and a score assembled from named signals can tell them. Ranking was never the problem
the workbench was solving.

Two findings fell out of measuring it. First, **graph analytics alone has perfect precision**
— 10 alerts, 10 real launderers — which makes it the natural top tier of a queue: work those
first, they are all real. Rules give more volume at 72%, ML gives the broadest reach at 60%.
That is a tiered alert queue derived from evidence rather than from an org chart, and it is
exactly how a real FIU allocates scarce analyst hours. Second, **screening barely contributes
to laundering risk at all** (0.250 precision) — and it should not, because it answers a
different question. Sanctions screening finds *who someone is*; transaction monitoring finds
*what they did*. Blending them into one number mixes identity risk with behaviour risk and
dilutes both. A real bank runs them as separate queues, and now I can say why with a number.

🔧 **Engineering:** I found a bug in my own measurement code before it could flatter me.
`compare_against_individual` divided recall by every dirty account in the bank, while ranking
only a held-out slice — understating recall roughly threefold (0.276 where the truth was
0.923). It surfaced because I knew the split contained exactly 26 positives and the reported
number was impossible against that. The lesson is the same one as Phase 4 and Phase 6: check
your measurement apparatus against a quantity you already know, because a plausible-looking
wrong number is far more dangerous than an obviously broken one. There is now a regression
test that recomputes recall independently and asserts they agree.

🎯 **Interview line:** "I built a risk score combining four detection layers, measured it, and
found it did not out-rank the best single layer — at one alert budget it was actively worse,
because sanctions screening was diluting it. So I documented the combination's real value as
explainability and tiering rather than accuracy, and split screening out as a separate queue.
The measurement also caught a bug in my own evaluation code that had been understating recall
threefold."

---

## Phase 7, slice 7.2 — 2026-07-29 (the case store — where detection becomes decision)

🏦 **FCC:** Everything built before today *finds* things. This is the first part of the system
that records a human having looked, and in AML that record is the actual deliverable. A bank
is not judged on whether its models were clever; it is judged on whether it can show an
examiner who reviewed an alert, what they saw, what they decided and why. So the dispositions
are the real vocabulary an FIU uses — false positive, suspicious with a SAR filed, suspicious
below the reporting threshold, escalated — and none of them can be recorded without a written
rationale, because a decision without a reason is indefensible under examination.

The subtle one is snapshotting the evidence at the moment a case opens. Detectors change:
Phase 6 retuned two rules and knowingly left a third producing false positives. If a case
re-derived its justification from today's code, an analyst's decision from last month would
silently acquire reasoning they never actually saw. That is not a database design choice, it
is the difference between an audit trail and a work of fiction.

🔧 **Engineering:** The append-only rule only holds if it is impossible to violate by
accident, so there is no code path that touches `case_events` other than inserting — and a
test asserts that at source level rather than trusting the convention. Same instinct as the
MCP server's audited decorator: a guarantee you have to remember is not a guarantee. Also
built duplicate suppression into `open_from_queue()` from the start rather than later:
detection gets re-run constantly, and a workbench that opens a fresh case for the same
account every run would bury an analyst in precisely the noise the whole alert-budget idea
exists to control.

🎯 **Interview line:** "The case store snapshots the evidence at the moment a case opens
rather than re-deriving it later, because my detectors get retuned — I'd already changed two
rules and knowingly left a third producing false positives. Without the snapshot, an
analyst's decision from last month would silently acquire reasoning they never actually saw.
That's the difference between an audit trail and a reconstruction."

---

## Phase 7, slice 7.3 — 2026-07-29 (the API — a transport, not a second brain)

🏦 **FCC:** The `/dispositions` endpoint looks trivial and is not: it serves the four closing
options straight from the case store rather than letting the UI hardcode its own list. If a
frontend invented its own vocabulary — "cleared", "no action", "suspicious-ish" — the
disposition field would slowly stop meaning anything, and disposition statistics are exactly
what a regulator samples. One list, one source, defined where the rule is enforced.

The entity-360 endpoint is the shape of the actual job. An analyst opening an alert needs
four things at once: who this customer is (KYC profile), what they did (transactions, newest
first), who they moved money with (the Phase 5 chains they sit in), and whether anyone has
looked before (open cases). Assembling those four from four different subsystems into one
response is most of what an investigation platform *is* — the detection was the easy part.

🔧 **Engineering:** Mapped case lifecycle violations to **409 Conflict rather than 500**.
Closing an already-closed case is not a server fault; it is a disagreement with the state of
the record, usually because two analysts had the same queue open. A 500 tells the UI "we
broke"; a 409 lets it say "someone already dispositioned this — refresh". Same reasoning for
requiring `actor` on every mutation: the case store already refuses anonymous changes, so
inventing an API-level default like "system" would have quietly created an audit trail that
lies. Where a lower layer enforces something, the layer above should surface it, not paper
over it. The API is deliberately thin for the same reason the MCP server was rewired in
Phase 4 — two implementations of the same logic drift, and then the numbers you publish stop
describing the thing users actually touch.

🎯 **Interview line:** "I mapped case-lifecycle violations to 409 Conflict rather than 500,
because closing an already-closed case isn't a server fault — it's usually two analysts with
the same queue open, and the UI needs to say 'someone already dispositioned this' rather than
'something broke'. I also refused to default the actor field on mutations: the case store
rejects anonymous changes, and inventing a default would have created an audit trail that
lies."

---

## Phase 7, slice 7.4 — 2026-07-29 (the queue — and the bug only the UI could show)

🏦 **FCC:** The queue is tiered by *kind of evidence*, not sorted by one blended number, and
that is a direct consequence of measuring rather than assuming: slice 7.1 showed the combined
score never out-ranked the best single layer, while graph evidence alone hit 100% precision.
So Tier 1 is "this account sits in a reconstructed money chain — work these first", Tier 2 is
"a named scenario fired, explainable in a sentence", Tier 3 is "no rule, but the model finds
it unusual". That is how a real FIU allocates scarce analyst hours, and here it is derived
from evidence instead of an org chart.

🔧 **Engineering:** Then the UI immediately earned its place by exposing a bug 178 passing
tests had missed. Rule strength was `min(n, 3) / 3`, so one rule firing counted as a third of
a signal. But **most genuine cases trip exactly one scenario** — a structuring scheme of 27
cash deposits totalling ₹2.6M trips `structuring_burst` and nothing else. It scored 11.7 out
of 100, fell below the queue's cut-off, and never reached an analyst, while mule accounts
scored 34.2 and did. The system was silently hiding confirmed placement cases. Nothing in the
test suite could see it, because every test asserted relative behaviour — more sources score
higher, repeats do not stack — and all of that stayed true. The absolute number was wrong,
and absolute numbers only look wrong when a human looks at them next to a threshold.
Replaced with a diminishing-returns curve (one rule 0.60, two 0.84, three 0.94), which is
also the more honest model: a second scenario is real corroboration, a third adds little.
The demo world went from 16 cases in a single tier to 30 across two.

🎯 **Interview line:** "I built the alert queue, looked at it, and found my risk score had
been hiding genuine cases. One rule firing counted as a third of a signal, so a confirmed
structuring scheme — 27 sub-threshold cash deposits — scored 11.7 out of 100 and fell below
the queue cut-off, while mule accounts appeared. A hundred and seventy-eight passing tests
never caught it, because they all asserted relative behaviour and that stayed true. Some bugs
only surface when a human looks at an absolute number next to a threshold."

---

## Phase 7, slice 7.5 — 2026-07-29 (the customer behind the alert — and a second truncation)

🏦 **FCC:** An alert names an *account*. A disposition is about a *customer*. Everything
between those two sentences is the investigation, and the entity-360 screen is where it
happens: KYC profile, what the account has done in total, who it moved money with, and the
statement itself, all on one screen with the evidence that raised the alert. The ordering is
deliberate and it is the analyst's own order — why am I looking at this, who is this, what
have they done, has anyone looked before. Notably, the profile is where a case usually turns:
A000630 alerted on 89 cash deposits, and it is a *business* account in Ahmedabad with a
medium risk rating — the deposits are either takings or placement, and nothing in the
transaction data alone decides which. That is why entity 360 exists and why detection alone
never closes a case.

🔧 **Engineering:** The screen found a bug for the second slice running, and it is the same
family as 7.4's. The entity endpoint returns the latest 100 transactions by default. Account
A000630 has 136, so its statement began 2026-07-08 while the account's history begins
2026-07-01 — an alert reading "89 cash deposits under Rs 100,000" was rendered above a
statement that could not contain 89 of anything. Nothing failed. No test could fail, because
the API was doing exactly what it was asked. **The evidence screen was truncating the
evidence, and truncation is invisible by construction — it looks like a shorter list.** Same
instinct produced the other decision in this slice: the activity totals are computed in SQL
over the whole account rather than summed from the transaction list the page already holds.
Summing what is on screen is one line shorter and would have understated credits on every
busy account without ever looking wrong. The rule I keep re-learning here: a number derived
from a *window* must never be presented as a number about the *whole*, and if the code cannot
tell the difference, a human will not either.

🎯 **Interview line:** "Building the entity-360 screen caught the same class of bug two slices
running. The transaction endpoint defaults to the latest hundred rows, so an account alerted
for eighty-nine cash deposits displayed a statement that started a week after the account did
— the evidence screen was truncating the evidence, and nothing failed, because the API did
exactly what it was asked. I also refused to sum the visible transactions for the account
totals and computed them in SQL over the whole history instead: summing the window is shorter
code and would have under-reported every busy customer without ever looking wrong. A number
derived from a window must never be presented as a number about the whole."


---

## Phase 7, slice 7.6 — 2026-07-30 (drawing the chain, and getting back to the rows)

🏦 **FCC:** Phase 5's real finding was that a chain does not exist in any single account's
history — it only exists in the edges *between* accounts. So showing it as a line of account
ids was showing the wrong shape: an investigator reading `A000640 → A000541 → A000544 →
A000045` cannot see that they are looking at one movement of money passing through four
people. Drawn as a path, with each hop labelled by what it carried, the 7.6% skim per hop is
visible at a glance — and that skim *is* the typology. The other half of the job is the
reverse direction: from the picture back to the rows. An investigator does not file a report
saying "the graph said so"; they file one citing two ledger entries. A chain nobody can trace
to transactions is an assertion, not evidence.

🔧 **Engineering:** The fix for that was already sitting in the codebase, thrown away. The
edge-pairing SQL in `graph/build.py` has always selected `dr_txn` and `cr_txn` — the two rows
whose shared narration reference proves they are one payment — and `load_transfers()`
discarded both. Carrying them through `Transfer` → graph edge → `Chain.hop_txns` → the API
took about fifteen lines, and it turns the chain from a claim into something clickable: hop 0
of A000541's chain resolves to a credit of Rs 6,41,251 at 04 Jul 02:21, hop 1 to a debit of
Rs 5,92,308 at 05 Jul 07:47. The general lesson is one I keep meeting: **when a derived
result feels unverifiable, check whether the derivation already computed the proof and
dropped it.** Drawing the thing was the easy part — hand-written SVG, because a path laid out
left to right does not need a force-directed layout engine, and the page's whole point is
that it has no build step.

🎯 **Interview line:** "My graph layer detected mule chains but an analyst couldn't act on
one, because a chain is an assertion until you can name the transactions behind it. The fix
was already in my own code — the SQL that pairs the two legs of a transfer had always selected
both row ids and then thrown them away. Carrying them through to the UI means clicking a hop
in the diagram highlights the exact statement lines it was built from. When a result feels
unverifiable, check whether the derivation already computed the proof and dropped it."

---

## Phase 7, slice 7.7 — 2026-07-30 (the part where a human decides)

🏦 **FCC:** Until this slice the workbench could show you everything and let you change
nothing, which is not a workbench — it is a report. The disposition is the moment the bank
takes a position: this was a false positive, or this is going to the Financial Intelligence
Unit. Three things had to be true for that to be worth anything, and all three already
existed one layer down, so the UI's job was to surface them rather than reinvent them. The
closing options are fetched from the API, because a frontend that invents "cleared" or
"looks fine" quietly destroys the disposition statistics a regulator samples. Every action
carries a named analyst, because "the system closed it" is not an audit trail. And a
disposition without a rationale is refused, because a decision nobody wrote a reason for
cannot be defended a year later when someone asks why this account was cleared.

🔧 **Engineering:** The most satisfying part was that a design decision from 7.3 finally paid
out. Back then I mapped case-lifecycle violations to **409 Conflict rather than 500**, and
the argument was hypothetical: two analysts with the same queue open. This slice is where
that becomes a sentence a human reads. Closing an already-closed case now says *"case 50 is
already closed — someone else may have worked this case"* instead of "something broke". I
tested it by racing a close against the API directly while the form was open, and the message
was exactly right. Worth noticing: **the error taxonomy had to be decided at the layer that
knew the truth, three slices before anything could display it.** If 7.3 had returned 500 for
everything, no amount of frontend work could have recovered the distinction — the information
would simply not have been there.

🎯 **Interview line:** "In my workbench, closing an already-closed case tells the analyst
'someone else may have worked this case' rather than showing an error. That's only possible
because three slices earlier I'd mapped lifecycle violations to 409 rather than 500 — the
distinction between 'you broke it' and 'the record moved under you' has to be decided at the
layer that knows the truth. By the time you're writing the error message in the UI, if the
API returned a 500 for everything, the information is already gone."

---

## Phase 7, slice 7.8 — 2026-07-30 (the filing — and the number it caught)

🏦 **FCC:** The narrative is the only artefact of this entire system that anyone outside the
bank ever reads. Everything upstream — the world, six typologies, four detection layers, a
tournament of six models — exists to produce a few paragraphs a Financial Intelligence Unit
can act on. Writing the template forced three positions I had not had to take before. It
never says laundering occurred: the bank reports *suspicion* and is not the finder of fact,
so the language stays at "consistent with" and "no conclusion is drawn as to whether an
offence has occurred". It reproduces the case's **snapshotted** signals rather than re-running
today's detectors, because a filing that silently acquires reasoning the analyst never saw is
worse than no filing. And the transaction annex is ranked by value and says so out loud —
because only the graph layer can name the rows behind its own alert. A rule emits a reason
string, screening answers an identity question, a model emits a score; none of them record
which transactions made them fire. **Explainability in an AML stack is not one property, it
is four different ones, and only one of my four layers has it.**

🔧 **Engineering:** The roadmap allowed a language model here and I did not use one, which is
a decision rather than laziness. A SAR is a regulatory filing: every figure in it is asserted
to a regulator by the bank. A generated sentence that rounds Rs 26,00,000 to "approximately
2.5 million", or invents a plausible counterparty name, is not a style problem — it is a false
statement in a legal document. A template can only emit numbers it read from the ledger, and
the same case always drafts identically, so it can be diffed and reviewed. Then **the very
first narrative I printed caught a bug the whole project had been carrying**: a confirmed
structuring scheme, 50 cash deposits totalling Rs 33,43,000, described itself as *"21.0 out of
100 (low band)"*. Measuring the whole bank: every one of 50 cases was low or medium and the
highest score that existed anywhere was 43.5 — `high` and `critical` were words describing
nothing. The thresholds treated the score as a percentage of something attainable, but 100
requires all four layers firing at full strength on one account, and 7.4 had already
established that most real cases trip exactly one. Re-derived the bands from the signal
algebra instead of guessing again. **Twice now, the thing that exposed a bad number was
rendering it for a human**: the queue in 7.4, and a document in 7.8.

🎯 **Interview line:** "I deliberately did not use an LLM for the SAR narrative, even though
my own plan allowed it. A suspicious activity report is a regulatory filing where every figure
is asserted to a regulator by the bank — a generated sentence that rounds a number is a false
statement in a legal document, not a style problem. And the first narrative I printed caught a
real bug: a confirmed structuring scheme with fifty cash deposits described itself as 'low
risk', because my risk bands assumed a score of 100 was attainable when nothing in the bank
could exceed 43. 'High' and 'critical' were words that described nothing."

---

## Phase 7 complete — 2026-07-30 (what the workbench turned out to be)

🏦 **FCC:** Phase 7 was supposed to be the presentation layer over phases 3-6 and it was not.
It was where the detection work got audited by contact with the job. The queue exposed that
genuine single-rule cases were scoring below the cut-off. The entity screen exposed that the
statement was truncating the evidence it existed to show. The narrative exposed that the risk
bands described a scale nothing could reach. **Three defects, none of which any test could
have found, all of them discovered by rendering a number where a person had to read it next
to a decision.** That is the honest case for building the investigator's tool rather than
stopping at the leaderboard: detection metrics grade a detector against ground truth, but
nothing grades whether the output is *usable*, and the gap between those two is where AML
programmes actually fail.

🔧 **Engineering:** Phase 7 also closed a gap that had been open since Phase 4 — there was no
way to *see* any of it. Every world with crime in it lived inside a test fixture or a
throwaway script, so the workbench demoed on an empty queue and the MCP server returned empty
lists. `python -m launderlab demo-world` now builds the thing in 52 seconds: 1,200 accounts,
78,556 transactions, 36 schemes, 50 cases across two evidence tiers. The lesson is unglamorous
and general: **a demo path is not documentation, it is a feature, and if it does not exist the
work is invisible regardless of how good it is.** I had shipped six phases whose only
demonstration was `pytest -q`.

🎯 **Interview line:** "Building the investigator's workbench found three bugs in detection
work that a hundred and ninety passing tests had not: a scoring curve that hid single-rule
cases below the queue cut-off, a statement that truncated the evidence it existed to display,
and risk bands calibrated to a score nothing could ever reach. All three surfaced the same
way — by putting a number in front of a person next to a decision they had to make. Detection
metrics tell you whether a detector is right; only the investigator's screen tells you whether
the output is usable, and that gap is where AML programmes actually fail."


---

## Phase 7, slice 7.10 — 2026-07-30 (the same bug, four times)

🏦 **FCC:** The workbench exists to combine four detection layers and it had been demonstrating
two. Nothing planted watchlist entities in the demo world, so screening never fired; nothing
passed model scores, so the models never contributed. Ten lines fixed the demo. Then the
interesting part: **fuzzy sanctions screening was being discarded wholesale.** A screening-only
case scores weight × match, and at weight 0.20 its ceiling is exactly 20.0 — which was the
threshold at which a case opens. So only a *perfect* 1.000 name match ever reached an analyst.
Every transliteration, every reordered name, every initials variant — 0.887 to 0.984, which is
the entire reason a fuzzy matcher exists rather than a string comparison — landed between 17.7
and 19.7 and was thrown away at the gate. Fourteen of fifteen planted entities. Phase 4 had
measured 100% recall and been quietly proud of it; the layer above it deleted the result.

This is the most consequential thing I have found in the project, because in the real world it
is not a missed alert, it is a missed *blocking obligation*. A sanctions hit is not a "review
when you get to it" item. And the related finding is the same shape: under one shared alert
budget, sanctions-only hits score lowest of anything and are cut first — 42 of 92 eligible
accounts did not fit. That is precisely why banks run screening as its own queue with its own
clock, and I now understand that as arithmetic rather than as organisational trivia.

🔧 **Engineering:** The threshold is no longer a number someone picked. It is derived from both
directions: it must sit **above** what the model alone can produce (0.15 × 1.0 = 15.0, because
a model-only alert has no reason to give an analyst and "the model said so" is not a SAR) and
**at or below** the faintest thing any control is willing to assert (screening's own accept
threshold, 0.88 × 0.20 = 17.6). That leaves 17.5, and a test pins the window — so changing any
weight now fails a test and forces the decision to be made rather than silently breaking a
layer.

That test then earned its keep in its first run by catching **7.4's bug living in the graph
layer**, where it had survived three slices for the dumbest possible reason: every chain in the
demo world happens to be exactly 3 hops long. Chain strength was `min(hops, 4) / 4`, so the
shortest chain Phase 5 will report — 2 hops, real named evidence with both ledger rows behind
it — scored half, landing at 15.0, *exactly* the model's ceiling and making the threshold
window mathematically unsatisfiable. Identical to treating one rule as a third of a signal, and
fixed with the identical curve, now shared.

Four instances of one root cause: **a global cut applied to a score whose scale depends on
which layers happened to fire.** Bands (7.8), the model tier, screening's gate, the graph
curve. I keep finding this because the weighted sum makes it invisible — every individual
number looks reasonable, and the defect only exists in the interaction. The general lesson: if
a threshold and a weight are chosen in different places at different times, something is
already broken and nothing will tell you.

🎯 **Interview line:** "I found that my system was discarding fourteen of fifteen sanctions
matches. A screening-only alert scored the layer's weight times the match confidence — 0.20 ×
0.98 — which landed just under the threshold at which a case opens. Only a perfect 1.000 name
match ever reached an analyst, so every transliteration, the entire reason you run a fuzzy
matcher, was thrown away one layer above the matcher that correctly found it. Nothing failed:
the threshold and the weight were chosen in different places at different times, and the defect
only existed in their interaction. I fixed it by deriving the threshold from both sides — above
what a model alone can score, at or below the faintest thing any control will assert — and
pinned that window with a test, which then immediately caught the same bug hiding in my graph
layer."


---

## Pre-Phase-8 audit — 2026-07-30 (green did not mean what I thought it meant)

🏦 **FCC:** The finding that matters most here is a control-testing one, and it is the same
mistake regulators keep fining firms for. My continuous integration reported green on every
push for eight days. It was installing only the base dependencies, so the three test files that
guard themselves against missing optional packages skipped silently — and because a skipped
*module* counts as one skip, pytest printed "178 passed, 3 skipped" while 226 tests existed.
Forty-eight tests were absent behind the number 3. Among them were **two of the seven
source-level tests that enforce this project's single most important rule: no detection code may
read ground truth.** The control existed, was well designed, was documented in the handoff as
enforced — and was not executing. That is exactly a control that passes on paper and does
nothing in practice, which is what SOX testing and model validation exist to catch. I now
understand *why* a tester samples evidence of operation rather than reading the control
description.

🔧 **Engineering:** Green ticks are a claim, and I had not audited mine. The fix is two lines of
dependencies, but the durable part is that CI now **fails if any test skips at all**: with every
extra installed there is no legitimate reason to skip, so a skip can only mean a dependency
stopped resolving. A guarantee you have to remember to check is not a guarantee — the same
instinct that made the MCP audit trail a decorator and `case_events` append-only.

The other four findings were all my own claims. A "detection-rate-per-typology bar chart" the
project said it had shipped, generated in some session and lost, with no code able to redraw it;
Phase 3's line still advertising a precision figure that Phase 6 had already demolished, warned
about in HANDOFF but not in the file anyone reads first; an audit decorator that accepted
keyword arguments only while advertising a positional signature, uncaught because every test
happened to call it the one way that worked; and a phase left unchecked in one document and
complete in another. None of these were coding errors. **All of them were the gap between what I
wrote down and what was true**, and the only way any of them surfaced was going back and
running the thing rather than re-reading the claim.

🎯 **Interview line:** "Before starting the last phase I audited my own project for claims I
couldn't reproduce, and found my CI had been reporting green while running 178 of 226 tests. It
installed only the base dependencies, so three test files skipped silently — and because a
skipped module counts as one skip, forty-eight missing tests hid behind the number 3. Two of
them were the source-level tests enforcing my most important invariant, that detection code
never reads ground truth. The control was well designed, documented as enforced, and not
executing. That is a control that passes on paper and does nothing in practice, which is
precisely what control testing exists to find — so CI now fails if any test skips at all."


---

## Phase 7, slice 7.12 — 2026-07-30 (a negative result, and the coin toss under it)

🏦 **FCC:** Adverse media does not belong in a transaction-monitoring risk score, and now I can
say why with numbers rather than instinct. It is not that the matcher is weak — on this world it
was right about the person 47.6% of the time with 100% recall, which for name-only matching
against news text is respectable. It is that **it answers a different question.** Adverse media
asks "is there negative news about this person?"; the risk score asks "is this account moving
criminal money?". Of 21 accounts media flagged, one was laundering — and the set of laundering
accounts that *only* media reached was empty. Every one was already found by a rule or a chain.

That empty set is the whole answer, and it is the cleanest piece of reasoning I have done on this
project: a signal can only add recall through accounts it alone reaches. If that set is empty,
no weight, no normalisation and no clever aggregation shape can add a single true positive — the
signal can only reorder the queue, and reordering a budget-capped queue can only push something
real out of it. Which is exactly what happened: two confirmed structuring cases dropped out of a
50-case budget so that sanctions-plus-news name matches could take their seats.

The right home for it is the entity screen. When an analyst is adjudicating a case, "there is a
corruption story naming this customer" is genuinely the first thing they want. It is context for
a decision, not evidence for a ranking, and those are different jobs. That is the same
conclusion 7.1 reached about sanctions screening, one layer further out — and in the real world
it is why adverse media lives in EDD and periodic review rather than in transaction monitoring.

🔧 **Engineering:** The experiment found something worse than the thing it was measuring. My
ranking had **no tie-break**, and every single-rule case scores exactly 0.35 × 0.60 = 21.00 — so
on the demo world 45 accounts sit on that one value with the alert budget's cut falling inside
the cluster. Which 24 of 45 an analyst actually worked was decided by dictionary insertion
order. I only noticed because the baseline moved from 44 true positives to 46 between two runs
of the same command, which is impossible if the pipeline is deterministic. Ties now break on
account id.

The deeper lesson is about what I then did with the numbers. Once ties were deterministic the
baseline settled at 39 — not 44, not 46 — because the tie-break picks a different 24. **All
three numbers were equally arbitrary.** So the report now prints how many accounts are contesting
how many seats, and the recommendation rests on unique reach, which depends on neither the tie
order nor the budget nor the weighting. A measurement whose headline moves when you change
something irrelevant is not a measurement yet, and the fix is not a better tie-break — it is
finding the statement that does not depend on the arbitrary part.

Also worth its own line: I nearly shipped the "folded into screening" alternative, because at
budget 50 it looked free — identical to baseline on every figure. The budget sweep killed it. At
a looser budget it inherits screening's full weight and opens cases on media alone: 11 extra
reviews, zero extra finds. One budget is not a measurement.

🎯 **Interview line:** "I was asked to add adverse media to my risk score and I measured it
first, which is how I ended up recommending against it. The matcher was fine — 47.6% precision
at identifying the right person. But of the twenty-one accounts it flagged, one was actually
laundering, and the set of laundering accounts that only adverse media reached was empty. That
single fact decides it regardless of weighting: a signal adds recall only through accounts it
alone reaches, so with that set empty it can only reorder the queue — and reordering a
budget-capped queue pushes something real out. It cost two confirmed structuring cases to make
room for sanctions-plus-news name matches, none of which were laundering. So it ships on the
entity screen as context for the analyst and carries zero weight in the ranking, which is where
adverse media actually belongs — enhanced due diligence, not transaction monitoring."


---

## Phase 8 — 2026-07-30 (the number nobody else has published, and it isn't one number)

🏦 **FCC:** The research question was "how fast does a detection stack rot against an adapting
adversary", and I built it expecting one headline number — a generation count, maybe a curve
that slopes the same way for everything. It doesn't. `shell_company` collapses from 70% recall
to 0% in two generations and never recovers — n_invoices only had to move from 5 to 3, barely a
mutation at all, and that confirms something I already suspected from 6.2: `counterparty_concentration`
isn't fragile, it is structurally unfixable, and now I have adversarial pressure proving it rather
than a static clean-world test implying it. `mule_network` — the one typology BOTH the rules
engine and Phase 5's graph watch — starts at a perfect 100% and still fully collapses by
generation 7, once the cut and the hop window both drift past what either detector accepts.
But `structuring` and `round_tripping` never fully converge across all 8 generations, even at
genuinely extreme parameter values — a deposit ceiling one rupee under the cash-reporting line,
a round-trip left parked for 38 days. Those two rules are comparatively ROBUST to this class of
evasion, and Phase 3's single aggregate number (93.3% recall across all six typologies) could
never have told me that some of my detectors decay and some hold. That is the actual finding:
detection decay is not a property of "the stack", it is a property of each individual rule's
relationship to the typology it watches, and averaging across typologies was hiding that the
whole time.

🔧 **Engineering:** Two real bugs, and both were the project's recurring lesson arriving in a new
place. First: the account pool for each typology was sampled independently from a shared pool, so
structuring and shell_company sometimes landed on the SAME business account within one
generation — the extra scheme's credits diluted `counterparty_concentration`'s "one counterparty
is most of my money" signal, and shell_company's measured generation-0 recall came out as 1/12
before I noticed. That is not the adversary winning, that is cross-contamination between two
unrelated experiments sharing a variable they shouldn't share — the exact bug class 2.7's
capstone test exists to catch in the injectors, now found in the benchmark harness on top of
them. Fixed with `_partition()`, which carves disjoint account chunks and *raises* rather than
silently sampling with replacement if the pool runs out — a silent fallback there would have
recreated the same bug quietly instead of loudly. Real generation-0 recall for shell_company
turned out to be 70%, not 8%; the harness bug was hiding the actual finding underneath it.

Second, smaller but the same instinct: `run_decay_benchmark`'s real docstring was immediately
followed by a second string literal, and Python only keeps the FIRST bare string as a function's
`__doc__` — the second silently evaluates as a no-op expression and vanishes without an error.
The actual explanation of what the function does had disappeared from `help()` and I only found
it by reading the file end to end rather than trusting that a docstring existing meant it was the
right one. A test now pins that `__doc__` contains specific text, so a repeat of that edit
mistake fails loudly instead of quietly.

The methodological addition I'm proudest of: "converged" in my own report used to mean "first
generation this typology scored zero recall", and I initially reported it as if that meant
permanent invisibility from then on. It doesn't — the genome freezes, but it still runs against a
FRESH randomly generated world every generation, so a frozen doctrine can still occasionally trip
a rule by chance. `dormant_reactivation` converged at generation 2 and still showed 20% recall
at generation 4. So the report now computes a post-convergence mean recall as its own number,
and it caught exactly this: shell_company's convergence is genuinely stable (0% mean afterward),
dormant_reactivation's is not (12% mean afterward) — two typologies that both say "converged at
generation 2" are not equally caught, and the label alone would have hidden that.

🎯 **Interview line:** "I built a red team that mutates its own parameters generation over
generation, and the finding wasn't a decay curve, it was that decay isn't uniform. One rule —
counterparty concentration for shell companies — collapsed to zero recall in two generations and
stayed there, which confirmed something I'd suspected since an earlier phase: that rule is
structurally unfixable, not just weakly tuned. But two other rules never fully converged across
eight generations even at extreme, realistic parameter values. Averaging those into one recall
number, which is what my Phase 3 proof originally did, was hiding that some of my detectors decay
fast and some don't decay at all — and you cannot tell which is which from an aggregate."


---

## Phase 8.5 — 2026-07-31 (the blind spot is the network, not the account)

🏦 **FCC:** I expected to measure "banks can't see cross-bank laundering". What the experiment
actually says is sharper and more useful: **banks see the accounts perfectly well and cannot see
the network at all.** Each bank flagged 75-77% of the individual mule accounts sitting on its own
books — `rapid_pass_through` fires happily on "money arrived and left again within the day",
because an account's entire history lives at its own bank. What no bank could do was join those
hops into a chain: reconstructing a chain means pairing the two legs of a transfer, and when the
counterparty banks elsewhere the second leg is not in your ledger at all. Solo chain
reconstruction came out at 0-6%.

That distinction matters practically. It means the problem is not that banks lack signals — they
have them, and they are probably filing individual STRs on these accounts already. It is that
nobody can see that six separate "suspicious pass-through" alerts at six different banks are one
laundering operation. Which is exactly the gap FIUs exist to close, and exactly why cross-bank
intelligence sharing is the live regulatory topic it is.

The second finding surprised me and is the one I would lead with. I built two arms expecting to
show that a *sophisticated* launderer who deliberately spreads a chain across institutions
defeats detection. Deliberate placement gave 0% solo reconstruction — but naive placement, where
the launderer ignores banks entirely, gave 6%. Spreading the chain deliberately buys almost
nothing, because **the blind spot is already near-total by accident**. With n banks, seeing a
chain requires two consecutive hops inside one bank, so the odds fall off as 1/n². You do not
need a clever adversary to get this blind spot; you get it for free from how the banking system
is partitioned. The case for co-operation does not depend on facing a sophisticated criminal.

🔧 **Engineering:** Two decisions I would defend in review. First, each bank's view is a
genuinely separate DuckDB file, not a `WHERE` clause. A filter would have been faster and
simpler, but then every detector in the project — rules, graph build, motifs — would have to
remember to honour it, and one that forgot would silently give a bank sight of another bank's
rows. That would invent detection ability that does not exist and inflate the exact number this
phase is built to produce. With separate files the isolation is structural: the other bank's rows
are absent, every existing detector runs completely unmodified, and a test asserts each ledger
holds only its own accounts, transactions and customers.

Second, and this is the mistake I nearly published: my first version scored the co-operative view
on cross-boundary recoveries ALONE. That penalised the naive arm for intra-bank hops its own bank
already held both legs of — and produced the absurd result that a chain *deliberately spread
across banks* looked better covered (69%) than a careless one (50%). Getting a backwards ordering
out of a metric is the cheapest possible signal that the metric is wrong, and I only caught it
because I bothered to ask why the numbers ran the wrong way instead of writing them down. The
co-operative view now counts every hop whose link is known: recovered across a boundary, plus
intra-bank ones needing no protocol at all. Naive correctly comes out ahead at 81%.

I also made the mechanism behind "0%" a computed number rather than a claim.
`_solo_reconstructable_runs` counts how many stretches of a chain were even long enough for
`motifs` to report — if that is 0, a solo bank never had an opportunity, and the 0% that follows
is explained rather than merely observed. Its own test uses hand-built bank sequences, because a
version of that function that just returned 0 would have faked the entire headline.

🎯 **Interview line:** "I split a synthetic bank into four institutions with genuinely separate
ledgers and measured what each could see of a mule chain running through all of them. The finding
wasn't 'banks are blind' — they flagged three-quarters of the individual mule accounts on their
own books. What they reconstructed of the chain itself was between zero and six percent. The
blind spot is the network, not the account: six banks each file a suspicious-activity report and
nobody can see it's one operation. And it doesn't take a sophisticated launderer — spreading a
chain deliberately across banks bought almost nothing over placing it carelessly, because seeing
a chain needs two consecutive hops inside one bank, which falls off as one over n-squared. Then I
prototyped co-operation where banks publish only HMAC'd payment references for accounts they'd
already flagged themselves — no names, no account numbers — and recovered about 80% of the hops."

---

## Phase 9.1 — 2026-07-31 (Story Mode, and "caught" was never one property)

🏦 **FCC:** I set out to build the visual finale — a page where someone who will never open a
ledger can *watch* a laundering scheme run. Building it forced a question the project had never
asked, and the answer is the most useful thing I have measured.

Every detection number in this repo — 86.1% recall, 15/15 chains, the whole decay benchmark —
was scored against the **finished** world. All 39 days of it, graded once, at the end. Written
down like that it is obviously an assumption, and an indefensible one: it quietly grants the
bank permission to wait until the crime is over before deciding it happened. No transaction
monitoring system on earth works that way. They run nightly, against the ledger so far. So the
real question an FCC team asks is not "was it caught" but **"how long did it run first"**.

Measuring it inverted my intuition twice over. The typology caught *fastest* in days is among
the worst in practice: `round_tripping` alerts in a median 4 days with **100% of the money
already moved**. That is not a tuning failure. The `round_trip` rule fires on a debit followed
by a matching credit — it needs the **return leg to exist** before it has anything to see, and
the return leg is the last act of the scheme. The rule is structurally incapable of firing while
a rupee is still stoppable. `dormancy_burst` has the identical shape: it requires the cash-out.
Two of my six rules can only ever confirm a completed crime.

Meanwhile `structuring` is the *slowest* to detect — 9 days, the worst bar on the latency chart
— and is caught with **53% of the scheme still to come**, the best on the chart that matters. It
accumulates, so the alert lands mid-crime, while intervention still means something.

The lesson generalises past this repo. "Detection rate" is one axis and every AML vendor sells
on it. Whether the alert arrives while the money is still in the building is a completely
different axis, it is not implied by the first, and for some controls it is fixed by the shape of
the evidence the rule requires rather than by any threshold you can tune. A control that only
confirms losses is still worth having — it is how a SAR gets filed and a network gets mapped —
but calling it *prevention* is a category error, and I could not have told those apart from a
recall number.

🔧 **Engineering:** The measurement is only trustworthy because the detectors doing it are the
real ones. The temptation was to write a day-aware version of each rule — "has this account hit
24 deposits by day N" — which is a second implementation of six rules that would drift from the
six being graded, and drift silently. Instead I truncate the *world*: a DuckDB view named
`transactions` shadows the real table through `search_path`, so the SQL every rule already
contains does the filtering itself and `rules.run_all` runs completely unmodified. Zero lines of
detection logic were written for this slice.

That mechanism is load-bearing, so I verified it in a scratch database before building on it
(and learned `asof` is a reserved word). The test that guards it asserts the **row count through
the view**, not the effect — because the failure mode is so quiet. If shadowing ever stopped
working, every detector would run against the full 39-day world on every day of the replay and
report that everything was caught on day one. A flattering number, and nothing would fail.

Two bugs came from *looking at the rendered page*, which is now four for four in this project
(7.4, 7.5, 7.8b, this). Sorted by typology, the page opened on a `dormant_reactivation` that
runs for one day — so it loaded with a slider that had a single position, and the one feature
the page exists for looked broken on arrival. And the fixed-width SVG overflowed its card, which
pushed the value label off the end of the **longest** bar — the single number a reader most
wants was the one number they could not see. Both are the same species: nothing throws, the
artefact just quietly fails at its job. A third I caught by re-reading rather than looking — the
scrubber built its calendar with browser `Date` arithmetic, where `setDate` steps in local time
while `toISOString` reads back UTC, so across a DST boundary it would repeat a day. I deleted
the JavaScript and built the calendar in Python, where real dates already existed.

🎯 **Interview line:** "Every detection number I'd published was scored against the finished
world — thirty-nine days, graded once at the end. That assumes a bank can wait until the crime
is over to decide it happened, and no monitoring system works that way. So I replayed each day
and re-ran the real detectors against a view of the ledger truncated to that day — no second
copy of a rule, the rule's own SQL does the filtering. Two things inverted. The typology caught
fastest, round-tripping at four days, was caught with a hundred percent of the money already
gone — because that rule needs the return leg before it can fire, so it structurally cannot
alert while anything is stoppable. And structuring, the slowest at nine days, was caught with
half the scheme still to come. Detection rate is one axis; whether the alert arrives while the
money is still in the building is a different one, and for some controls it's fixed by the shape
of the evidence rather than by any threshold you can tune."
