"""Seed the ledger with a hand-crafted cast and one believable week of financial life.

Deliberately small and readable: 25 customers whose week we can eyeball line by line.
Phase 1 replaces this with the agent-based World Engine at scale — but the behaviors
rehearsed here (salaries, rent, EMIs, UPI P2P, merchant footfall, business receipts)
become the World Engine's vocabulary.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import duckdb

WEEK_START = date(2026, 7, 1)
IFSC = "LLAB0000001"


@dataclass(frozen=True)
class Person:
    customer_id: str
    name: str
    dob: str
    segment: str
    city: str
    account_type: str
    opening: int
    vpa: str = ""
    salary: int = 0
    employer: str = ""
    rent: int = 0
    emi: int = 0
    emi_lender: str = ""
    remittance: int = 0
    remit_from: str = ""
    pocket_money: int = 0
    parent: str = ""


CAST: list[Person] = [
    Person("C001", "Asha Rao", "1994-03-12", "salaried", "Hyderabad", "savings", 62000,
           vpa="asha.rao@okhdfc", salary=85000, employer="TECHNOVA SOLUTIONS",
           rent=18000, emi=12400, emi_lender="HDFC CAR LOAN"),
    Person("C002", "Vikram Iyer", "1991-08-04", "salaried", "Bengaluru", "savings", 48000,
           vpa="vikram.iyer@okicici", salary=72000, employer="QUANTEDGE ANALYTICS", rent=22000),
    Person("C003", "Meera Pillai", "1996-01-27", "salaried", "Hyderabad", "savings", 35000,
           vpa="meera.p@oksbi", salary=54000, employer="BRIGHTPATH EDUTECH", rent=15000),
    Person("C004", "Rohit Sharma", "1989-11-19", "salaried", "Pune", "savings", 90000,
           vpa="rohit.sh@okaxis", salary=110000, employer="APEXCORE SYSTEMS",
           emi=24000, emi_lender="SBI HOME LOAN"),
    Person("C005", "Farhan Ali", "1993-05-30", "salaried", "Hyderabad", "savings", 28000,
           vpa="farhan.ali@okhdfc", salary=46000, employer="MEDIQUICK LABS", rent=12000),
    Person("C006", "Divya Nair", "1995-09-14", "salaried", "Mumbai", "savings", 41000,
           vpa="divya.nair@okicici", salary=65000, employer="NILGIRI FOODS LTD", rent=19000),
    Person("C007", "Arjun Reddy", "1992-02-08", "salaried", "Hyderabad", "savings", 55000,
           vpa="arjun.reddy@oksbi", salary=78000, employer="SKYBRIDGE LOGISTICS",
           emi=9800, emi_lender="BAJAJ FIN EMI"),
    Person("C008", "Kavya Krishnan", "1997-07-22", "salaried", "Bengaluru", "savings", 22000,
           vpa="kavya.k@okaxis", salary=38000, employer="PIXELWEAVE DESIGN", rent=11000),
    Person("C009", "Suresh Gupta", "1978-04-16", "business", "Hyderabad", "current", 320000,
           vpa="guptatextiles@okhdfc"),
    Person("C010", "Lakshmi Devi", "1982-12-03", "business", "Hyderabad", "current", 260000,
           vpa="lakshmitraders@oksbi"),
    Person("C011", "Imran Sheikh", "1985-06-21", "business", "Mumbai", "current", 410000,
           vpa="imran.electro@okicici"),
    Person("C012", "Nilesh Patel", "1975-10-09", "business", "Pune", "current", 285000,
           vpa="patelagro@okaxis"),
    Person("C013", "Rahul Verma", "2004-03-25", "student", "Hyderabad", "savings", 6500,
           vpa="rahul.v04@oksbi", pocket_money=5000, parent="S B VERMA"),
    Person("C014", "Sneha Kulkarni", "2005-08-11", "student", "Pune", "savings", 4200,
           vpa="sneha.kulk@okhdfc", pocket_money=4000, parent="M A KULKARNI"),
    Person("C015", "Aditya Rao", "2003-12-30", "student", "Bengaluru", "savings", 8900,
           vpa="adi.rao03@okicici", pocket_money=6000, parent="V RAO"),
    Person("C016", "Priya Singh", "2004-05-17", "student", "Hyderabad", "savings", 5400,
           vpa="priya.s04@okaxis", pocket_money=4500, parent="R K SINGH"),
    Person("C017", "Anand Menon", "1986-01-05", "nri", "Kochi", "savings", 540000,
           vpa="anand.menon@okhdfc", remittance=150000, remit_from="ANAND MENON DUBAI AE"),
    Person("C018", "Ritu Malhotra", "1988-09-28", "nri", "Delhi", "savings", 380000,
           vpa="ritu.m@okicici", remittance=90000, remit_from="RITU MALHOTRA LONDON GB"),
    Person("C019", "DMART HYDERABAD", "2001-01-01", "merchant", "Hyderabad", "current", 850000,
           vpa="dmart.hyd@okicici"),
    Person("C020", "KPHB KIRANA STORE", "2010-01-01", "merchant", "Hyderabad", "current", 95000,
           vpa="kphb.kirana@oksbi"),
    Person("C021", "SRI SAI MEDICALS", "2008-01-01", "merchant", "Hyderabad", "current", 140000,
           vpa="srisai.med@okhdfc"),
    Person("C022", "PARADISE BIRYANI", "1995-01-01", "merchant", "Hyderabad", "current", 310000,
           vpa="paradise.bir@okaxis"),
    Person("C023", "HP PETROL KUKATPALLY", "2004-01-01", "merchant", "Hyderabad", "current",
           520000, vpa="hp.kukat@okicici"),
    Person("C024", "CHOICE ELECTRONICS", "2012-01-01", "merchant", "Hyderabad", "current", 270000,
           vpa="choice.elec@oksbi"),
    Person("C025", "ZEPTO DARK STORE HYD", "2021-01-01", "merchant", "Hyderabad", "current",
           600000, vpa="zepto.hyd@okhdfc"),
]

MERCHANT_PRICE = {
    "C019": (250, 1800), "C020": (80, 600), "C021": (120, 700), "C022": (280, 950),
    "C023": (500, 2200), "C024": (1500, 9000), "C025": (150, 900),
}
STUDENT_MERCHANTS = ["C020", "C021", "C022", "C025"]
P2P_PAIRS = [
    ("C001", "C005"), ("C002", "C008"), ("C003", "C006"), ("C007", "C004"),
    ("C013", "C014"), ("C015", "C016"), ("C005", "C007"), ("C008", "C003"),
]
FIRMS = [
    "SRINIVASA COTTON MILLS", "NAVKAR DISTRIBUTORS", "GOLKONDA EXPORTS",
    "RK ENTERPRISES", "SHREE BALAJI AGENCIES", "VMAX RETAIL PVT LTD",
]


def account_id(customer_id: str) -> str:
    return "A" + customer_id[1:]


def load(conn: duckdb.DuckDBPyConnection, week_start: date = WEEK_START) -> int:
    """Insert the cast and post one week of life. Returns transactions posted."""
    _insert_people(conn)
    events = _week_of_life(random.Random(42), week_start)
    return _post_all(conn, events)


def _insert_people(conn: duckdb.DuckDBPyConnection) -> None:
    base = datetime(2023, 1, 1)
    cust_rows, acct_rows = [], []
    for i, p in enumerate(CAST):
        risk = "medium" if p.segment in ("business", "nri") else "low"
        cust_rows.append((p.customer_id, p.name, p.dob, p.segment, p.city, "full", risk,
                          base + timedelta(days=i * 17)))
        acct_rows.append((account_id(p.customer_id), p.customer_id, p.account_type, IFSC,
                          "active", base + timedelta(days=i * 17 + 1)))
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)", cust_rows)
    conn.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)", acct_rows)


def _week_of_life(rng: random.Random, week_start: date) -> list:
    """Build composite events: (ts, [leg, ...]) where each leg is one statement row.

    Internal payments produce two legs (payer DR + payee CR) so both statements agree.
    """
    people = {p.customer_id: p for p in CAST}
    merchants = [p for p in CAST if p.segment == "merchant"]
    ev: list = []

    def ref() -> str:
        return str(rng.randrange(100000, 1000000))

    def at(d: int, h: int, m: int | None = None) -> datetime:
        minute = rng.randrange(60) if m is None else m
        return datetime.combine(week_start + timedelta(days=d), time(h, minute))

    for i, p in enumerate(CAST):
        acct = account_id(p.customer_id)
        if p.salary:
            r = ref()
            ev.append((at(0, 6, 30 + i), [(acct, "CR", "NEFT", p.salary, p.employer, r,
                                           f"NEFT/CR/{r}/{p.employer} SAL JUL")]))
        if p.remittance:
            r = ref()
            ev.append((at(1, 11), [(acct, "CR", "RTGS", p.remittance, p.remit_from, r,
                                    f"INW-RMT/CR/{r}/{p.remit_from}")]))
        if p.pocket_money:
            r = ref()
            pv = p.parent.split()[0].lower() + "@oksbi"
            ev.append((at(0, 7, 15), [(acct, "CR", "UPI", p.pocket_money, p.parent, pv,
                                       f"UPI/CR/{r}/{pv}")]))
        if p.rent:
            r = ref()
            lv = f"rent.{p.city[:3].lower()}@okaxis"
            ev.append((at(1, 9), [(acct, "DR", "UPI", p.rent, "Landlord", lv,
                                   f"UPI/DR/{r}/{lv} JUL RENT")]))
        if p.emi:
            r = ref()
            ev.append((at(4, 8, 0), [(acct, "DR", "NACH", p.emi, p.emi_lender, r,
                                      f"NACH/DR/{r}/{p.emi_lender}")]))
        if p.segment == "salaried":
            amt = rng.randrange(4, 13) * 500
            ev.append((at(rng.randrange(1, 7), 19), [(acct, "DR", "ATM", amt, None, None,
                       f"ATM-CASH/DR/{p.city[:3].upper()}-{rng.randrange(10, 99)}")]))

    shoppers = [p for p in CAST if p.segment in ("salaried", "student")]
    for p in shoppers:
        acct = account_id(p.customer_id)
        pool = ([m for m in merchants if m.customer_id in STUDENT_MERCHANTS]
                if p.segment == "student" else merchants)
        for d in range(7):
            for _ in range(rng.choice([0, 1, 1, 2])):
                m = rng.choice(pool)
                lo, hi = MERCHANT_PRICE[m.customer_id]
                amt = rng.randrange(lo, hi)
                r, ts = ref(), at(d, rng.randrange(9, 22))
                ev.append((ts, [
                    (acct, "DR", "UPI", amt, m.name, m.vpa, f"UPI/DR/{r}/{m.vpa}"),
                    (account_id(m.customer_id), "CR", "UPI", amt, p.name, p.vpa,
                     f"UPI/CR/{r}/{p.vpa}"),
                ]))

    for payer, payee in P2P_PAIRS:
        if rng.random() < 0.8:
            amt = rng.randrange(4, 50) * 50
            r, ts = ref(), at(rng.randrange(0, 7), rng.randrange(10, 22))
            pp, qq = people[payer], people[payee]
            ev.append((ts, [
                (account_id(payer), "DR", "UPI", amt, qq.name, qq.vpa, f"UPI/DR/{r}/{qq.vpa}"),
                (account_id(payee), "CR", "UPI", amt, pp.name, pp.vpa, f"UPI/CR/{r}/{pp.vpa}"),
            ]))

    for p in [q for q in CAST if q.segment == "business"]:
        acct = account_id(p.customer_id)
        for d in range(7):
            for _ in range(rng.randrange(1, 4)):
                amt = rng.randrange(15, 81) * 1000
                r, ch, f = ref(), rng.choice(["IMPS", "NEFT"]), rng.choice(FIRMS)
                ev.append((at(d, rng.randrange(10, 18)), [(acct, "CR", ch, amt, f, r,
                                                           f"{ch}/CR/{r}/{f}")]))
        for d in (3, 5):
            amt = rng.randrange(40, 121) * 1000
            r, f = ref(), rng.choice(FIRMS)
            ev.append((at(d, rng.randrange(10, 16)), [(acct, "DR", "NEFT", amt, f, r,
                                                       f"NEFT/DR/{r}/{f} PURCHASE")]))
        r = ref()
        ev.append((at(5, 17), [(acct, "DR", "NEFT", rng.randrange(8, 31) * 1000, "GSTN", r,
                                f"GST/DR/{r}/EPAYMENT")]))

    for m in merchants:
        acct = account_id(m.customer_id)
        lo, hi = MERCHANT_PRICE[m.customer_id]
        for d in range(7):
            for _ in range(rng.randrange(3, 7)):
                amt = rng.randrange(lo, hi)
                r = ref()
                cust = f"cust{rng.randrange(1000, 9999)}@ok{rng.choice(['sbi', 'hdfc', 'icici'])}"
                ev.append((at(d, rng.randrange(8, 23)), [(acct, "CR", "UPI", amt, None, cust,
                                                          f"UPI/CR/{r}/{cust}")]))
        r = ref()
        restock = int(m.opening * rng.randrange(30, 61) / 100)
        ev.append((at(5, 9), [(acct, "DR", "NEFT", restock, "DISTRIBUTOR", r,
                               f"NEFT/DR/{r}/STOCK PURCHASE")]))

    return ev


def _post_all(conn: duckdb.DuckDBPyConnection, events: list) -> int:
    """Post composites in time order, keeping running balances. No overdrafts in v0:
    if any debit leg would overdraw, the whole payment silently doesn't happen —
    a broke agent simply doesn't spend."""
    balances = {account_id(p.customer_id): p.opening for p in CAST}
    rows = []
    for ts, legs in sorted(events, key=lambda e: e[0]):
        if any(d == "DR" and amt > balances[acct] for acct, d, _ch, amt, *_ in legs):
            continue
        for acct, direction, channel, amount, cp_name, cp_ref, narration in legs:
            balances[acct] += amount if direction == "CR" else -amount
            rows.append((ts, acct, direction, channel, amount, cp_name, cp_ref, narration,
                         balances[acct]))
    conn.executemany(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " counterparty_name, counterparty_ref, narration, balance_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)
