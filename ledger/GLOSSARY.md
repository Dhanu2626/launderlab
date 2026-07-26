# Glossary — FCC jargon, decoded as we meet it

- **Ledger** — the bank's master record of every transaction. Ours lives in DuckDB.
- **DR / CR** — debit (money going out) / credit (money coming in), as printed on statements.
- **Narration** — the cryptic text line on a statement (`UPI/DR/519377/nexatr@okhdfc`) that encodes channel, direction, reference and counterparty.
- **Typology** — a named laundering method (structuring, mule chain, shell layering…). Regulators publish them; our injector implements them.
- **Ground truth** — knowing which transactions are actually criminal. Real banks don't have it; simulators do. Ours lives in `scheme_labels`.
- **Placement → layering → integration** — the three classic stages of money laundering: get dirty cash into the system, hide its trail, make it look legitimate.
- **KYC** — Know Your Customer: identity checks when an account is opened; depth recorded as `kyc_level`.
- **VPA** — Virtual Payment Address, the UPI ID (`asha.rao@okhdfc`) that stands in for an account number.
- **NACH** — National Automated Clearing House: the auto-debit rail that pulls EMIs and SIPs on a fixed day each month.
- **Peer group** — the crowd an account is compared against ("students", "kirana stores"). Suspicion = deviation from *your* peer group, not from everyone.
- **Two-leg posting** — one internal payment writes two statement rows: payer's DR and payee's CR. If only one leg exists, a statement is lying.
- **Opening balance** — the balance before a statement's first row; derived by reversing the first transaction, not stored — same trick real core-banking systems use.
- **Bulk load (COPY)** — loading many database rows via a file + the database's native bulk loader, instead of one SQL statement per row. Orders of magnitude faster because it skips per-statement parsing/transaction overhead.
