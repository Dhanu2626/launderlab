"""Render any account's transaction history as an HTML bank statement."""

from __future__ import annotations

from pathlib import Path

import duckdb

_ROW = """<tr><td>{date}</td><td class="narr">{narration}</td>
<td class="amt debit">{debit}</td><td class="amt credit">{credit}</td>
<td class="amt bal">{balance}</td></tr>"""

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Statement - {account_id}</title><style>
body{{font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#222;margin:2rem}}
h1{{font-size:16px;margin:0 0 4px}}
.meta{{color:#555;margin-bottom:1rem;line-height:1.6}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:6px 8px;text-align:left}}
th{{background:#f0f0f0}}
.amt{{text-align:right;font-variant-numeric:tabular-nums}}
.debit{{color:#a32d2d}} .credit{{color:#0f6e56}}
.narr{{font-family:Consolas,monospace;font-size:12px}}
</style></head><body>
<h1>LaunderLab Bank</h1>
<div class="meta">Account holder: {name}<br>Account: {account_id} ({account_type})
&middot; IFSC: {ifsc}<br>Statement period: {period}</div>
<table><tr><th>Date</th><th>Narration</th><th>Debit</th><th>Credit</th><th>Balance</th></tr>
{opening_row}
{rows}
</table></body></html>"""


def _money(v) -> str:
    return f"{v:,.2f}" if v is not None else ""


def render(conn: duckdb.DuckDBPyConnection, account_id: str) -> str:
    """Build the statement HTML for one account. Raises ValueError if unknown."""
    header = conn.execute(
        "SELECT c.full_name, a.account_type, a.ifsc FROM accounts a"
        " JOIN customers c USING (customer_id) WHERE a.account_id = ?",
        [account_id],
    ).fetchone()
    if header is None:
        raise ValueError(f"no such account: {account_id}")
    name, account_type, ifsc = header

    txns = conn.execute(
        "SELECT ts, narration, direction, amount, balance_after FROM transactions"
        " WHERE account_id = ? ORDER BY ts, txn_id",
        [account_id],
    ).fetchall()

    opening_row = ""
    period = "no transactions"
    if txns:
        first_ts, _n, first_dir, first_amt, first_bal = txns[0]
        opening = first_bal - first_amt if first_dir == "CR" else first_bal + first_amt
        opening_row = _ROW.format(date="", narration="Opening balance", debit="", credit="",
                                   balance=_money(opening))
        period = f"{txns[0][0]:%d %b %Y} to {txns[-1][0]:%d %b %Y}"

    rows = "\n".join(
        _ROW.format(
            date=f"{ts:%d-%m-%Y}", narration=narration,
            debit=_money(amount) if direction == "DR" else "",
            credit=_money(amount) if direction == "CR" else "",
            balance=_money(balance),
        )
        for ts, narration, direction, amount, balance in txns
    )
    return _PAGE.format(account_id=account_id, name=name, account_type=account_type,
                         ifsc=ifsc, period=period, opening_row=opening_row, rows=rows)


def write(conn: duckdb.DuckDBPyConnection, account_id: str,
          out_dir: str | Path = "data/statements") -> Path:
    """Render and save the statement, returning the file path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{account_id}.html"
    path.write_text(render(conn, account_id), encoding="utf-8")
    return path
