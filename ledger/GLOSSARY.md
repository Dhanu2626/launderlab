# Glossary — FCC jargon, decoded as we meet it

- **Ledger** — the bank's master record of every transaction. Ours lives in DuckDB.
- **DR / CR** — debit (money going out) / credit (money coming in), as printed on statements.
- **Narration** — the cryptic text line on a statement (`UPI/DR/519377/nexatr@okhdfc`) that encodes channel, direction, reference and counterparty.
- **Typology** — a named laundering method (structuring, mule chain, shell layering…). Regulators publish them; our injector implements them.
- **Ground truth** — knowing which transactions are actually criminal. Real banks don't have it; simulators do. Ours lives in `scheme_labels`.
- **Placement → layering → integration** — the three classic stages of money laundering: get dirty cash into the system, hide its trail, make it look legitimate.
- **KYC** — Know Your Customer: identity checks when an account is opened; depth recorded as `kyc_level`.
