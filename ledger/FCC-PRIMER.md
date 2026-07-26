# FCC primer — the three stages, mapped to what we're building

Read this once before Phase 1 starts. Every future subsystem exists to fight one of these
three stages. Examples use our own seeded cast (`ledger/FIELD-NOTES.md` Day 2) so the
concepts point at real rows in our own database, not textbook abstractions.

## The three stages of money laundering

Criminal money has one problem: it can't be spent openly, because its origin gives it away.
Laundering is the three-step fix.

### 1. Placement — getting dirty cash into the banking system

The moment illegal cash (drugs, fraud, extortion) first touches a bank account. This is the
riskiest stage for a criminal — banks are legally required to report large cash deposits, so
placement is where the more clumsy criminals get caught immediately.

**Classic technique — structuring/smurfing:** break a ₹10 lakh pile of cash into 25 deposits
of ₹40,000 each, spread across days and branches, to stay under India's ₹10 lakh reporting
threshold (US equivalent: $10,000 under the Bank Secrecy Act).

**Where LaunderLab fights this:** Phase 2's structuring typology injects exactly this
pattern into the transaction stream; Phase 3's rules engine (velocity + threshold rules)
is the first line of defense that has ever caught it in the real world.

### 2. Layering — burying the money's trail

Once inside the system, money gets moved through many hops — different accounts, different
banks, different countries — specifically to make the paper trail exhausting to follow. No
single hop looks criminal; the crime is only visible in the *pattern* across hops.

**Classic technique — mule networks:** dirty money lands in one account (`C009 Suresh Gupta`
style business account, say), gets split and forwarded through several "mule" accounts
(recruited or unwitting people who pass money along for a cut), and lands somewhere clean.

**Where LaunderLab fights this:** Phase 2's mule-chain and shell-layering typologies build
the hops; Phase 5's graph analytics is built specifically to unbury them — because rules
checking one account at a time are structurally blind to a pattern spread across ten
accounts. This is also why the cross-bank blind spot (research thesis problem #3) matters:
layering that hops across banks is invisible to any single bank's rules or graph.

### 3. Integration — making dirty money look legitimate

The final step: the now-clean-looking money re-enters the economy as if it were ordinary
income — buying property, going through a business's declared revenue, funding a lifestyle
that has a plausible paper explanation.

**Classic technique — trade-based laundering / shell companies:** a shell company (no real
operations) issues fake invoices to a real business, and payment for the "invoice" is
actually laundered money now sitting in the business's books as legitimate revenue. Our
seeded merchants (`C019`–`C025`, DMart/kirana/Paradise Biryani style) are exactly the kind
of legitimate-cash-business that integration schemes try to hide inside — high genuine cash
turnover is the perfect camouflage.

**Where LaunderLab fights this:** Phase 4's screening (sanctions/PEP/geography/adverse
media) and Phase 6's ML tournament both look for statistical mismatches between a
business's declared profile and its actual transaction behavior — the giveaway integration
schemes can't fully hide.

## The three tracks, restated

- **Track A — Simulate** (phases 0–2): can we build a world real enough that placement,
  layering, and integration can hide inside it convincingly?
- **Track B — Detect** (phases 3–6): rules, screening, graph analytics, and the ML
  tournament — each one aimed at a different stage above.
- **Track C — Investigate** (phase 7): once something is flagged, can a human act on it?

## Quick reference — stage to subsystem

| Stage | Real-world giveaway | LaunderLab subsystem | Phase |
|---|---|---|---|
| Placement | Many small deposits under a threshold | Rules engine (velocity/threshold rules) | 3 |
| Layering | Money hopping through many accounts fast | Graph analytics (mule-ring detection) | 5 |
| Layering (cross-bank) | Hops spread across banks, invisible to any one bank | Multi-bank experiment | 8.5 |
| Integration | Business behavior doesn't match its declared profile | Screening + ML tournament | 4, 6 |
