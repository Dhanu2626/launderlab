# LaunderLab — 3-minute demo video script

**Status: script and shot list only. The recording is yours to make — I cannot capture screen
or audio.** Everything below is timed to ~3:00 at a normal speaking pace (~150 wpm), and every
number in it is one this repo can reproduce on demand.

## Before you record

```
.venv\Scripts\python -m launderlab demo-world --overwrite
set LAUNDERLAB_DB=data\demo.duckdb
.venv\Scripts\python -m launderlab charts
.venv\Scripts\python -m launderlab story
.venv\Scripts\python -m launderlab publish
```

Then open **two** windows and leave both ready:
1. A browser on `docs/index.html` (the landing page).
2. A terminal, cleared, in the repo root.

Also start the workbench in a third window so it is warm when you reach it:
`.venv\Scripts\python -m uvicorn launderlab.workbench.api:app --port 8787`

⚠️ Check nothing stale is on 8787 first: `netstat -ano | findstr :8787`. A leftover server from
an old session serves old code against an old world and looks perfectly fine on camera.

---

## 0:00–0:20 — The problem (talking head or terminal, no slides)

> "Every bank runs anti-money-laundering detection, and none of them can tell you how good it
> is. They know what they caught. They cannot know what they missed — there's no answer key.
> So I built one."

**Shot:** the landing page, `docs/index.html`. Don't click yet.

---

## 0:20–0:50 — What it is (terminal)

> "LaunderLab is a synthetic bank with real laundering hidden inside it. It generates ten
> thousand customers and six hundred thousand transactions in about thirty seconds, then
> injects six laundering typologies from public FATF and FinCEN advisories — and records
> ground truth for every single transaction it plants."

**Shot:** run `python -m launderlab demo-world --overwrite`. Let it scroll. Land on the summary:
1,200 accounts, 78,556 transactions, 36 schemes, 50 cases.

> "Which means every detector I write can be scored on real precision and recall. That's the
> whole point — it's the measurement a production bank structurally cannot make."

---

## 0:50–1:25 — Watch the crime (Story Mode) ← **the centrepiece**

**Shot:** browser → Story Mode. Pick the shell-company scheme it opens on. **Drag the slider
slowly from left to right.**

> "This is one real scheme replaying day by day. A shell company feeding invoice payments into
> a business account."

**Beat — pause the drag around day 5, before the box turns red:**

> "Watch the account. It stays grey. It's in the answer key the entire time — I know it's dirty
> — but nothing has *detected* it yet."

**Continue the drag past day 6, box outlines red:**

> "There. Day six. That's not me colouring it in — that's the real rule firing, re-run against
> the ledger truncated to that day. Everything before it, the crime was invisible."

---

## 1:25–2:05 — The finding (scroll to the two charts)

> "Building that let me measure something I'd never measured: how long a scheme runs before
> anything fires. And it broke my assumptions twice."

**Shot:** the latency chart.

> "Structuring is the slowest to detect — nine days."

**Shot:** scroll to the second chart, *How much had already moved*.

> "But look what happens when you ask a different question: how much of the money was already
> gone when the alert fired. Round-tripping is caught in four days — fast — with **a hundred
> percent** of the money already moved. Every time."

**Beat:**

> "That's not a tuning problem. The rule fires on money leaving and coming back — it needs the
> return leg to exist before it has anything to see, and the return leg is the last act of the
> scheme. It is structurally incapable of alerting while a rupee is still stoppable. No
> threshold fixes that. Meanwhile structuring, the slowest one, is caught with half the scheme
> still to come."

> "Detection rate is one axis. Whether the alert arrives in time is a completely different one,
> and nothing I'd built before this could tell them apart."

---

## 2:05–2:35 — It's a real workbench, not a dashboard

**Shot:** switch to `localhost:8787`. Click a Tier-1 case. Scroll the entity 360. Click a chain
hop and let it scroll to the two ledger rows.

> "The alerts land in a working investigator queue. Click a case, you get the customer, their
> whole history, and the chain the money took — every hop traceable to the two ledger rows it
> was rebuilt from. A chain an investigator can't trace to transactions is an assertion, not
> evidence."

**Shot:** click through to the SAR narrative.

> "And it drafts the suspicious activity report. Deliberately a template, not a language model
> — every figure in a SAR is asserted to a regulator, and a generated sentence that rounds a
> number is a false statement in a legal filing."

---

## 2:35–3:00 — The honest close

> "The results I'm proudest of are the negative ones. Combining all four detection layers into
> one score doesn't rank better than the best single layer — I measured it, it didn't, and I
> published that. Adverse media adds no true positive at any weight, so it's surfaced and never
> scored."

**Shot:** back to the landing page, or the red team / multi-bank chart.

> "Seventeen times in this project a flattering number turned out to be an artefact. Every one is
> written down. That's the part I'd want a hiring manager to look at."

> "It's open source. Link's below."

---

## Recording notes

- **Screen at 1080p minimum**, browser zoom ~110% — the chart labels are small at 100%.
- **The slider drag is the money shot.** Do it slowly, and re-record until the grey→red
  transition is clearly visible. That single moment carries the whole video.
- Keep the terminal font large. Nobody reads 11pt on a phone.
- Cut the `demo-world` wait — jump-cut from command to summary.
- No music under the 1:25–2:05 section; the finding needs the words to land.
- **Do not read numbers off the script.** Read them off the screen while recording, and if they
  differ from this file, the screen is right and this file is stale — regenerate and re-check.
