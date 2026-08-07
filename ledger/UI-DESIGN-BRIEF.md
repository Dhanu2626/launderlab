# LaunderLab — UI design brief (paste this into Claude)

**Purpose:** get a second, independent design for the LaunderLab research site, designed from
the *content* rather than from the existing layout. Everything Claude needs is in this brief —
it should not need the repo, and it should not be shown the current site first.

**How to use it:** open a new Claude conversation, paste everything below the line, and ask for
an artifact. Then compare against <https://dhanu2626.github.io/launderlab/>.

**Before you act on the result — read this.** Whatever comes back will be a mockup with these
numbers *typed into the HTML*. The live site's whole claim is that its figures are rendered from
the scoring modules, so nobody types them and a published number cannot drift from the one the
tests grade. That property is worth more than any layout. So:

- Judge the result on **information architecture, hierarchy, typography, and how well it makes a
  stranger understand the findings**.
- If you prefer it, the move is to port the **design** into `src/launderlab/web.py`, not to
  publish its HTML.
- Sanity-check any number it shows against this brief. If it invented one, that tells you
  something about trusting generated mockups.

---

## PASTE FROM HERE

You are designing the public research website for **LaunderLab**, a completed open-source
project. I want your own independent design — do not ask me for the existing version, and do not
try to match anything. Design from the content in this brief.

Deliver **one self-contained HTML artifact** (inline CSS and JS, no external requests of any
kind — no CDN, no web fonts, no remote images). It must work opened as a single file.

At the end, give me a short rationale: the three or four design decisions you made and why. I am
comparing your reasoning as much as your output.

---

### 1. What the project is

Every bank runs anti-money-laundering (AML) detection. None of them can tell you how good it is:
they know what they *caught*, but there is no way to know what they *missed*. There is no answer
key, so recall is not computable on real data.

LaunderLab builds the missing answer key. It generates a synthetic bank, injects six real
money-laundering typologies taken from public FATF / FinCEN / RBI advisories, and **records
ground truth for every planted transaction**. That makes every detector scorable on real
precision and recall — the measurement a production bank structurally cannot make.

The framing that works: **a cyber range, but for financial crime.** Security teams have had
adversarial ranges for years — red team attacks, blue team defends, you measure who wins.
Financial-crime teams have nothing equivalent, because you cannot publish real laundering data.

**The loop:** Red team (a mutating adversary) → Synthetic bank (+ ground truth) → Detection
stack (4 layers) → Investigator workbench (queue → SAR draft) → Scorers (precision / recall) →
back to the red team, which reads what got caught and adapts.

**Author:** Dhanush Jangadi, a financial-crime/AML specialist. This is a portfolio piece. It has
to work for two audiences at once — a recruiter with three minutes, and a senior AML engineer
with thirty.

**Tone:** scientific, precise, quietly confident. Not salesy. Not cyberpunk. Not neon. The
reference points are Linear, Vercel, Stripe's dashboard, Datadog, a Bloomberg terminal.

---

### 2. The six laundering typologies (needed to read the charts)

| Typology | Plain English |
|---|---|
| `structuring` | Splitting cash into many deposits under the ₹1,00,000 reporting threshold ("smurfing") |
| `layering` (mule network) | Money hops through a chain of accounts, each keeping a cut, to break the trail |
| `shell_company` | A few large fake "invoice" payments from a front company into a real business |
| `round_tripping` | Money leaves an account and returns slightly inflated, to look like profit |
| `dormant_reactivation` | A long-inactive account gets a big credit and is drained within hours |
| `high_risk_geography` | International transfers tied to FATF-listed jurisdictions |

**The four detection layers:** rules engine (6 tunable scenarios) · sanctions/PEP name screening
· graph analytics (rebuilds chains) · ML tournament (6 model families).

---

### 3. THE DATA — use these exact numbers, invent nothing

Scale: **10,000 customers, 630,755 transactions generated in 31 seconds.** The benchmark world
used for all results below: **1,200 accounts, 78,556 transactions, 36 injected schemes, 50 cases
opened.** Test suite: **320 tests, zero skips.**

**Headline operating metrics**
| Metric | Value | Detail |
|---|---|---|
| Detection rate | 86.1% | 31 of 36 injected schemes caught |
| Alert precision | 65.3% | false-positive rate 34.7% |
| Queue precision | 80.0% | 40 of 50 opened cases sit on a genuinely dirty account |
| Alert-to-SAR conversion | **not measurable** | no case worked to a disposition; ceiling 80.0% |
| Reviews per true find | 1.25 | at an alert budget of 100: 40 real in 50 worked |

**Alert-budget sweep (false-positive economics)**
| Budget | Worked | Real | Reviews per true find |
|---|---|---|---|
| 10 | 10 | 10 | 1.00 |
| 25 | 25 | 25 | 1.00 |
| 50 | 50 | 40 | 1.25 |
| 100 | 50 | 40 | 1.25 |

**Rules-engine recall by typology**
| Typology | Caught | Recall |
|---|---|---|
| high_risk_geography | 5/5 | 100% |
| layering | 8/8 | 100% |
| round_tripping | 5/5 | 100% |
| structuring | 8/8 | 100% |
| dormant_reactivation | 3/5 | 60% |
| shell_company | 2/5 | 40% |

**Graph visibility** — only **1 of 6** typologies leaves any internal edge for a graph to
analyse (`layering`). The other five have counterparties outside the bank, so they leave one leg
and no edge. Graph detection on the chains that do exist: 100% precision.

**Investigator queue composition** (50 open cases)
| Layer | Cases filed under this tier | Cases it contributes evidence to |
|---|---|---|
| graph | 27 | 27 |
| rules | 23 | 49 |
| screening | 0 | 1 |
| ml | 0 | 24 |

**Detection latency** — how long a scheme ran before ANY detector could fire, measured by
re-running the real detectors against the ledger truncated to each day. 34 of 36 schemes were
ever caught.
| Typology | Median days to first alert | Share of value already moved by then |
|---|---|---|
| dormant_reactivation | 0 | **100%** |
| high_risk_geography | 0 | 60% |
| layering | 1 | 46% |
| round_tripping | 4 | **100%** |
| shell_company | 6 | 58% |
| structuring | **9** | 47% |

**Red team decay benchmark** — 8 generations, 5 adversary genomes, one per typology. The
adversary mutates its own scheme parameters every generation it gets caught.
| Typology | Gen 0 recall | Final recall | Outcome |
|---|---|---|---|
| structuring | 90% | 90% | never fully evaded |
| round_tripping | 100% | 10% | never fully evaded |
| mule_network | 100% | 0% | collapsed at generation 7 |
| shell_company | 70% | 0% | collapsed at generation 2 |
| dormant_reactivation | 40% | 20% | collapsed at generation 2 |

**Cross-bank blind spot** — one world split across 4 banks with genuinely separate database
files. Two arms: `naive` (chains placed ignoring banks) and `deliberate` (consecutive hops
always at different banks).
| View | naive | deliberate |
|---|---|---|
| Pooled central view (hypothetical regulator) | 100% | 100% |
| A single bank alone | **6%** (2 of 36 hops) | **0%** |
| Privacy-preserving co-operation | **81%** | **69%** |
| Individual mule accounts flagged locally | **75%** | 77% |

**Screening** — 100% recall, 75.0% entity precision on a realistic name pool. On a narrow name
pool it scored 29.4%; a controlled two-arm experiment showed **86% of the false-positive rate
was collision density in the generated data**, not real ambiguity.

---

### 4. The findings — this is what the site exists to communicate

Lead with these. They are counterintuitive and they are the point.

**A. "Caught" was never one property.** `round_tripping` is caught in a median of 4 days —
fast — with **100% of the money already moved, every time**. That is not a tuning problem: the
rule fires on money leaving and coming back, so it needs the return leg before it has anything
to see, and the return leg is the *last act of the scheme*. It is structurally incapable of
alerting while a rupee is still stoppable. Meanwhile `structuring` — the slowest at 9 days, the
worst bar on the latency chart — is caught with roughly half the scheme still to come. Detection
rate asks *whether* a control fires; latency asks *when*, and whether that was soon enough.

**B. Detection decay is not uniform.** Against an adapting adversary, one rule collapses to zero
recall in 2 generations and stays there; two others never fully evade across 8. A single
aggregate recall figure could not have shown the difference.

**C. The cross-bank blind spot is the network, not the account.** Banks flag 75–77% of the
individual mule accounts on their own books and reconstruct 0–6% of the chains those accounts
form. And it does not take a sophisticated launderer: deliberately spreading a chain across
banks buys almost nothing over placing it carelessly (0% vs 6%), because seeing a chain needs
two *consecutive* hops inside one bank, and those odds fall as 1/n². Six banks each file a
report and nobody can see it is one operation.

**D. Detection is not monotonic — some alerts expire.** All five shell-company schemes fired a
concentration rule; three went *silent again* before month end, because that rule is a ratio
("one counterparty is at least half my credits") and ongoing legitimate income diluted the
shell's share back under the threshold. The three that went quiet fired earliest (8th, 9th, 11th
— now at 36.0%, 42.5%, 45.1%); the two still alerting fired latest (22nd, 26th — 59.1%, 53.3%).
A scheme detectable on the 9th was invisible on the 31st.

**E. Two negative results, reported rather than buried.** Combining all four detection layers
into one blended risk score does **not** rank better than the best single layer. And adverse
media, measured as a scoring signal, adds **no true positive at any weight** — of 21 accounts it
flags, 1 is laundering, and the set it uniquely reaches is empty. It is surfaced to analysts and
never scored.

**F. The honesty thread.** Seventeen times a flattering number turned out to be an artefact, and
each was measured, corrected and written down. Four worth showing:
- A model scored a perfect 1.000 average precision — the synthetic world emitted zero legitimate
  cash, so it had learned "cash = crime".
- The rules engine showed 100% precision — same root cause; fixing it took one rule from 0 to 24
  false positives on a clean world.
- CI looked green while running **178 of 226 tests** — a skipped *module* counts as one skip, so
  48 missing tests hid behind the number "3".
- Risk bands ran low→critical, but the highest achievable score was 43.5, so "high" and
  "critical" described nothing.

The pattern behind almost all of them: **they surfaced by rendering a number where a person had
to read it next to a decision.** Detection metrics grade a detector against ground truth; nothing
grades whether its output is usable.

**G. The limits, published too.** The world is synthetic and its realism bounds every figure.
The benchmarks use one random seed. The co-operation protocol is a prototype whose residual
disclosure is stated rather than glossed. Alert-to-SAR conversion is reported as *not measurable*
rather than as zero, because no case has been worked to a disposition — "nobody reviewed these"
and "everything reviewed was cleared" are opposite facts that a zero would merge.

---

### 5. What to build

A multi-page feel in one artifact (tabs, or a single scrolling page with sticky navigation —
your call, and I want to see which you choose and why):

1. **Overview / landing** — what this is in ten seconds, the loop diagram, the headline
   findings, a way in for both audiences.
2. **Story Mode** — an interactive replay of one laundering scheme, day by day. Invent
   plausible transaction rows for a shell-company scheme running 23 days across one account
   (large "invoice" credits from a front company). A day slider; the account must light up
   **only on the day a detector actually fires** (day 6), never before — the whole point is that
   it is in the answer key the entire time and stays dark. Show what evidence has accumulated.
3. **Measured results** — the operating metrics, recall by typology, graph visibility, queue
   composition. Every chart must answer: what am I seeing, why should I care, what does this
   prove.
4. **Red team benchmark** — the decay table as a chart across 8 generations, with what collapsed
   and what held.
5. **Cross-bank blind spot** — the flagship. It needs an illustration of a chain crossing four
   institutional boundaries and why each bank sees only one leg of each hop.

---

### 6. Constraints

- **Self-contained.** No external request of any kind. Inline everything. System font stack only.
- **No build step, no framework.** Semantic HTML, modern CSS, vanilla JS.
- **Accessible, and I will check this.** WCAG AA contrast: **4.5:1 for text** against every
  surface it sits on, 3.0:1 for chart fills and non-text UI. Keyboard navigable, visible focus
  states, a skip link, `<html lang>`, real `<button>` elements for controls.
- **Light and dark themes, both measured independently.** Do not derive one by inverting the
  other — a colour is a property of a colour *and the surface it sits on*, so a value moved to a
  new background is a new question. Include a toggle, respect `prefers-color-scheme` when the
  reader has not chosen, persist an explicit choice, and apply it before first paint so nothing
  flashes.
- **Motion is subtle and refusable.** Respect `prefers-reduced-motion`, and never make content
  depend on an animation having run — if scripting fails, the page must still be fully readable.
- **Responsive.** No horizontal scrolling on the page body at any width; wide tables and charts
  scroll inside their own container.
- **Never place a chart without context.** Each one answers: what am I seeing, why should I care,
  what does this prove, what is the conclusion.
- **Do not soften the negative results or the limitations.** They are the most credible thing
  here. "Not measurable" must never render as 0%.

Every number must be exactly as given above. If you are unsure of a figure, leave it out rather
than inventing it.
