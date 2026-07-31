# LinkedIn launch post — draft

**Status: draft for your review. I have not posted it and won't — publishing to your account is
yours to do.** Read it in your own voice before it goes out; if a sentence isn't how you'd say
it, change it. Every number below is reproducible from the repo.

---

## Option A — lead with the finding (recommended)

> The typology my detection stack catches *fastest* is the one it catches *too late*, every
> single time.
>
> I spent the last few months building LaunderLab — an open adversarial range for
> anti-money-laundering detection. A synthetic bank, six real laundering typologies injected
> from public FATF and FinCEN advisories, and a four-layer detection stack that has to catch
> them. Because the injector records ground truth, every detector gets scored on real precision
> and recall — the measurement a production bank structurally cannot make, because no bank
> knows what it missed.
>
> Last week I measured something I'd somehow never measured: how long a scheme runs before
> anything fires.
>
> Round-tripping is caught in a median of 4 days. Sounds good. But 100% of the money had
> already moved by then — every time. That isn't a tuning problem. The rule fires on money
> leaving and coming back, so it needs the return leg to exist before it has anything to see,
> and the return leg is the last act of the scheme. It is structurally incapable of alerting
> while a rupee is still stoppable. No threshold fixes it.
>
> Meanwhile structuring — the slowest to detect at 9 days, the worst bar on the chart — is
> caught with half the scheme still to come.
>
> Detection rate is one axis. Whether the alert arrives while the money is still in the
> building is a completely different one, and for some controls it's fixed by the shape of the
> evidence the rule requires, not by any threshold you can tune.
>
> Two other findings the range produced:
>
> → Detection decay isn't uniform. Against an adversary that mutates its own parameters each
> generation, one rule collapses to zero recall in 2 generations and stays there. Two others
> never fully evade across 8.
>
> → The cross-bank blind spot is the network, not the account. Split across four banks with
> genuinely separate ledgers, each flags 75–77% of the mule accounts on its own books — and
> reconstructs 0–6% of the chains those accounts form. Six banks each file a report and nobody
> can see it's one operation.
>
> The results I'm proudest of are the negative ones. Combining all four detection layers into
> one risk score does *not* rank better than the best single layer — I measured it, it didn't,
> and I published that instead of burying it. Adverse media adds no true positive at any
> weight, so it's surfaced to the analyst and never scored.
>
> Sixteen times in this project a flattering number turned out to be an artefact. All sixteen
> are written down in the README.
>
> Open source, all synthetic data, all typologies from public advisories:
> github.com/Dhanu2626/launderlab
>
> You can replay a scheme day by day in the browser without installing anything:
> dhanu2626.github.io/launderlab
>
> #AML #FinancialCrime #AntiMoneyLaundering #Compliance #RegTech #FinCrime

---

## Option B — shorter, lead with the build

> I built a cyber range for financial crime.
>
> Security teams have had them for years — a safe environment where a red team attacks and a
> blue team defends, and you measure who wins. Financial crime teams have nothing equivalent.
> So I built LaunderLab: a synthetic bank, six laundering typologies injected from public FATF
> and FinCEN advisories, a four-layer detection stack, a working investigator workbench that
> ends in a SAR draft, and a red team that mutates its own schemes each generation to evade
> detection.
>
> The point is the answer key. Because the injector records ground truth for every planted
> transaction, every detector is scored on real precision and recall — which is exactly the
> measurement no production bank can make, because no bank knows what it missed.
>
> Three things it found that I did not expect:
>
> → Detection decay isn't uniform. One rule collapses to zero recall in 2 generations of
> adaptation and never recovers; two others never fully evade across 8.
>
> → The cross-bank blind spot is the network, not the account. Four banks with separate ledgers
> each flag 75–77% of the mule accounts they hold — and reconstruct 0–6% of the chains.
>
> → "Caught" was never one property. The typology caught fastest is caught with 100% of the
> money already moved, because the rule needs the crime to complete before it has any evidence
> to fire on.
>
> Open source, all synthetic: github.com/Dhanu2626/launderlab
>
> #AML #FinancialCrime #Compliance #RegTech #FinCrime

---

## Before you post — a checklist

1. **The GitHub Pages link only works once you enable it.** Repo → Settings → Pages → Deploy
   from a branch → `main` / `docs`. Verify the URL loads in a private window before posting; a
   dead link in the first hour is the one people click.
2. **Post the video as native LinkedIn video, not a YouTube link.** LinkedIn suppresses
   off-platform links in the feed. Put the GitHub URL in the first comment if reach matters
   more to you than convenience.
3. **Tuesday–Thursday, 9–11am IST** is the usual sweet spot for this audience.
4. **Option A is the stronger post** — it opens on a specific, counterintuitive finding rather
   than on "I built a thing", and FinCrime people will argue with it in the comments, which is
   what you want. Option B is safer and more generic.
5. Re-read for your own voice. This is drafted to sound like you at your most precise, but you
   are the one who has to stand behind every sentence in an interview.
