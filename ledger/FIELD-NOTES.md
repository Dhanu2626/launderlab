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
