"""Draft a Suspicious Activity Report narrative from a case.

This is the last thing an investigator does and the only artefact anyone outside
the bank ever reads. Detection produces an alert; the narrative is what a
Financial Intelligence Unit receives, and it has to answer who, what, when,
where and why in plain prose that a person who has never seen this system can
follow.

WHY A TEMPLATE AND NOT A LANGUAGE MODEL. The roadmap allowed an LLM as a stretch
and this deliberately stops at the template. A SAR is a regulatory filing: every
figure in it is asserted to a regulator by the bank. A generated sentence that
rounds Rs 26,00,000 to "approximately 2.5 million" or invents a plausible-sounding
counterparty is not a style problem, it is a false statement in a legal document.
The template can only emit numbers it read from the ledger, and the same case
always produces the same narrative, so it can be diffed and reviewed. An LLM is
the right tool for *polishing prose an analyst then verifies*, which is a
different feature from *drafting the facts*.

WHAT IT DRAFTS FROM. The reason-for-suspicion section is the case's snapshotted
signals, verbatim, not a re-run of today's detectors -- same rule as the case
store (7.2). A narrative has to describe the suspicion the analyst actually
acted on; detectors get retuned, and a filing that silently acquires reasoning
nobody saw is worse than no filing.

WHAT IT REFUSES TO DO. It never states that laundering occurred. A SAR reports
*suspicion* and the language stays there ("activity is consistent with", not
"the customer laundered"), because the bank is not the finder of fact. And every
draft is stamped as a draft: it is a starting point for an analyst, never
something to file unread.

BOUNDARY: reads the ledger and the case store. Never `scheme_labels`.
"""

from __future__ import annotations

import textwrap
from datetime import datetime

import duckdb

from launderlab.workbench import cases

# The annex is ranked by VALUE, not by suspicion, and says so in its heading.
# ponytail: only the graph layer can currently name the rows behind its own
# alert (7.6 gave chains their hop transactions). Rules emit a reason string with
# figures in it, screening answers an identity question and ML emits a score, so
# there is nothing to join on. Rank by materiality until detectors record the
# transactions they fired on -- inventing an "evidence" ranking would be worse.
DEFAULT_ANNEX_ROWS = 10

DISCLAIMER = (
    "This narrative was drafted automatically from the case record and the bank's "
    "own ledger. It is a starting point for the reporting officer, not a filing. "
    "Every figure must be verified and the assessment confirmed by a named human "
    "before submission."
)


def _money(amount: float) -> str:
    # plain "Rs" rather than the rupee sign: narratives get printed to Windows
    # consoles, which default to cp1252 and cannot encode it.
    return f"Rs {amount:,.2f}"


def _when(ts: datetime) -> str:
    return ts.strftime("%d %b %Y")


def _when_exact(ts: datetime) -> str:
    return ts.strftime("%d %b %Y %H:%M")


def draft(conn: duckdb.DuckDBPyConnection, case_id: int,
          annex_rows: int = DEFAULT_ANNEX_ROWS) -> str:
    """Return a full SAR narrative draft for `case_id`.

    Raises `cases.CaseError` if the case does not exist.
    """
    case = cases.get(conn, case_id)
    account = conn.execute(
        "SELECT c.full_name, c.customer_id, c.segment, c.city, c.kyc_level, c.risk_rating,"
        " c.dob, a.account_type, a.ifsc, a.status, a.opened_at"
        " FROM accounts a JOIN customers c USING (customer_id) WHERE a.account_id = ?",
        [case.account_id]).fetchone()
    if account is None:  # a case can outlive nothing here, but never assume it
        raise cases.CaseError(f"case {case_id} points at unknown account {case.account_id}")

    (name, customer_id, segment, city, kyc_level, risk_rating,
     dob, account_type, ifsc, status, opened_at) = account

    totals = conn.execute(
        "SELECT count(*),"
        " coalesce(sum(CASE WHEN direction = 'CR' THEN amount END), 0)::DOUBLE,"
        " coalesce(sum(CASE WHEN direction = 'DR' THEN amount END), 0)::DOUBLE,"
        " min(ts), max(ts) FROM transactions WHERE account_id = ?",
        [case.account_id]).fetchone()
    txn_count, credits, debits, first_ts, last_ts = totals

    channels = conn.execute(
        "SELECT channel, count(*), sum(amount)::DOUBLE FROM transactions"
        " WHERE account_id = ? GROUP BY channel ORDER BY sum(amount) DESC",
        [case.account_id]).fetchall()

    annex = conn.execute(
        "SELECT ts, direction, channel, amount::DOUBLE, counterparty_name, narration"
        " FROM transactions WHERE account_id = ? ORDER BY amount DESC, ts LIMIT ?",
        [case.account_id, annex_rows]).fetchall()

    events = cases.timeline(conn, case_id)

    lines: list[str] = []
    add = lines.append

    add(f"SUSPICIOUS ACTIVITY REPORT - NARRATIVE DRAFT (case {case.case_id})")
    add("=" * 78)
    add("")

    # ---------------------------------------------------------------- subject
    add("1. SUBJECT")
    add(f"   Name             {name}")
    add(f"   Customer ID      {customer_id}")
    if dob:
        add(f"   Date of birth    {_when(dob)}")
    add(f"   Customer type    {segment}")
    if city:
        add(f"   Location         {city}")
    add(f"   KYC status       {kyc_level}")
    add(f"   Bank risk rating {risk_rating}")
    add("")

    # --------------------------------------------------------------- accounts
    add("2. ACCOUNT CONCERNED")
    add(f"   Account number   {case.account_id} ({account_type}, {status})")
    add(f"   Branch IFSC      {ifsc}")
    add(f"   Opened           {_when(opened_at)}")
    add("")

    # ------------------------------------------------------- activity summary
    add("3. ACCOUNT ACTIVITY IN THE PERIOD REVIEWED")
    if txn_count:
        add(f"   Period reviewed  {_when(first_ts)} to {_when(last_ts)}")
        add(f"   Transactions     {txn_count:,}")
        add(f"   Total credits    {_money(credits)}")
        add(f"   Total debits     {_money(debits)}")
        add(f"   Net movement     {_money(credits - debits)}")
        add("")
        add("   Activity by channel:")
        for channel, count, value in channels:
            noun = "transaction " if count == 1 else "transactions"
            add(f"     {channel:<6} {count:>6,} {noun}   {_money(value)}")
    else:
        add("   No transactions are recorded on this account for the period reviewed.")
    add("")

    # ---------------------------------------------------- reason for suspicion
    add("4. REASON FOR SUSPICION")
    add(f"   The account was referred for review on {_when_exact(case.opened_at)} with a")
    add(f"   composite risk score of {case.risk_score:.1f} out of 100 ({case.risk_band} band).")
    add("   The following monitoring signals were recorded at the time the case was")
    add("   opened, and are reproduced here as they stood on that date:")
    add("")
    if case.signals:
        for signal in case.signals:
            add(f"     - [{signal.source}] {signal.detail}")
    else:
        add("     - No signals were recorded against this case.")
    add("")
    add("   Taken together, this activity is consistent with the typologies the above")
    add("   scenarios are designed to detect. No conclusion is drawn as to whether an")
    add("   offence has occurred; this report is filed on the basis of suspicion.")
    add("")

    # ----------------------------------------------------------------- annex
    if annex:
        add(f"5. HIGHEST-VALUE TRANSACTIONS ON THE ACCOUNT (top {len(annex)} by amount)")
        add("   Listed by value to show the scale of the activity. This ordering is not")
        add("   an assertion that these particular entries are the suspicious ones.")
        add("")
        for ts, direction, channel, amount, counterparty, narration in annex:
            party = counterparty or "-"
            add(f"     {_when_exact(ts)}  {direction}  {channel:<5} {_money(amount):>18}"
                f"  {party}")
            add(f"        {narration}")
        add("")

    # ------------------------------------------------------------ what we did
    add("6. INVESTIGATION RECORD")
    for event in events:
        add(f"   {_when_exact(event.ts)}  {event.actor:<12} {event.event_type}")
        add(f"      {event.detail}")
    add("")

    # ----------------------------------------------------------- disposition
    add("7. DISPOSITION")
    if case.disposition:
        meaning = cases.DISPOSITIONS.get(case.disposition, "")
        add(f"   {case.disposition} - {meaning}")
    else:
        add(f"   The case is {case.status}. No disposition has been recorded, so this")
        add("   narrative is provisional and must not be filed as it stands.")
    if case.assigned_to:
        add(f"   Assigned analyst: {case.assigned_to}")
    add("")

    add("-" * 78)
    lines.extend(textwrap.wrap(DISCLAIMER, 78))

    return "\n".join(lines)
