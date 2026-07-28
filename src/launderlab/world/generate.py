"""Generate a month of financial life for a procedurally-generated population.

seed.py hand-crafts events for 25 named people using per-person hardcoded values
(rent, EMI, favorite merchants, P2P friends). This module generalizes the same
behaviors — salary, rent/EMI, P2P, merchant footfall, business receipts — to run
over any list of population.Profile objects, deriving parameters from each
profile's segment and income instead of a human typing them in.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import duckdb

from launderlab.db.ledger import bulk_insert
from launderlab.world.population import Profile, generate
from launderlab.world.seed import FIRMS, IFSC, account_id

LENDERS = ["HDFC HOME LOAN", "SBI CAR LOAN", "BAJAJ FIN EMI", "ICICI PERSONAL LOAN",
           "AXIS CONSUMER DURABLE LOAN"]

_TXN_COLUMNS = ["ts", "account_id", "direction", "channel", "amount",
                "counterparty_name", "counterparty_ref", "narration", "balance_after"]


def _insert_people(conn: duckdb.DuckDBPyConnection, profiles: list[Profile]) -> None:
    base = datetime(2023, 1, 1)
    cust_rows = [
        (p.customer_id, p.full_name, p.dob, p.segment, p.city, p.kyc_level, p.risk_rating,
         base + timedelta(minutes=i))
        for i, p in enumerate(profiles)
    ]
    acct_rows = [
        (account_id(p.customer_id), p.customer_id, p.account_type, IFSC, "active",
         base + timedelta(minutes=i, seconds=1))
        for i, p in enumerate(profiles)
    ]
    bulk_insert(conn, "customers",
                ["customer_id", "full_name", "dob", "segment", "city", "kyc_level",
                 "risk_rating", "created_at"], cust_rows)
    bulk_insert(conn, "accounts",
                ["account_id", "customer_id", "account_type", "ifsc", "status", "opened_at"],
                acct_rows)


def _friend_pairs(rng: random.Random, profiles: list[Profile]) -> list[tuple[Profile, Profile]]:
    """A lightweight social graph: shuffle P2P-eligible customers, pair each with
    their next 1-2 neighbours in the shuffled order. O(n), no quadratic scan."""
    candidates = [p for p in profiles if p.segment in ("salaried", "student")]
    if not candidates:
        return []
    rng.shuffle(candidates)
    n = len(candidates)
    pairs = []
    for i, p in enumerate(candidates):
        for offset in (1, 2):
            q = candidates[(i + offset) % n]
            if p.customer_id != q.customer_id:
                pairs.append((p, q))
    return pairs


def _merchant_price_range(p: Profile) -> tuple[int, int]:
    """Derive a plausible per-ticket price range from a merchant's monthly revenue."""
    avg_ticket = min(max(p.monthly_revenue / 1200, 30), 3000)
    return int(avg_ticket * 0.4), int(avg_ticket * 2.5)


def life_events(rng: random.Random, profiles: list[Profile], start: date, days: int = 30):
    """Build composite events: (ts, [leg, ...]) over `days` days, generalizing seed.py's
    per-person patterns to run against any generated population."""
    merchants = [p for p in profiles if p.segment == "merchant"]
    salaried_and_students = [p for p in profiles if p.segment in ("salaried", "student")]
    businesses = [p for p in profiles if p.segment == "business"]
    ev: list = []

    def ref() -> str:
        return str(rng.randrange(100000, 1000000))

    def at(d: int, h: int, m: int | None = None) -> datetime:
        d = min(max(d, 0), days - 1)
        minute = rng.randrange(60) if m is None else m
        return datetime.combine(start + timedelta(days=d), time(h, minute))

    for p in profiles:
        acct = account_id(p.customer_id)
        if p.salary:
            r = ref()
            salary_day = rng.randrange(0, 3)
            ev.append((at(salary_day, 6), [(acct, "CR", "NEFT", p.salary, p.employer, r,
                                            f"NEFT/CR/{r}/{p.employer} SALARY")]))
            if rng.random() < 0.55:
                rent = round(p.salary * rng.uniform(0.15, 0.35), -2)
                lv = f"rent.{p.city[:3].lower()}@okaxis"
                r = ref()
                ev.append((at(rng.randrange(1, 5), 9), [(acct, "DR", "UPI", rent, "Landlord",
                           lv, f"UPI/DR/{r}/{lv} RENT")]))
            if rng.random() < 0.40:
                emi = round(p.salary * rng.uniform(0.08, 0.25), -2)
                lender = rng.choice(LENDERS)
                r = ref()
                ev.append((at(rng.randrange(3, 8), 8), [(acct, "DR", "NACH", emi, lender, r,
                           f"NACH/DR/{r}/{lender}")]))
            for w in range(days // 7):
                amt = rng.randrange(4, 13) * 500
                r = ref()
                ev.append((at(w * 7 + rng.randrange(1, 7), 19), [
                    (acct, "DR", "ATM", amt, None, None,
                     f"ATM-CASH/DR/{p.city[:3].upper()}-{rng.randrange(10, 99)}")]))

        if p.remittance:
            # INT, not RTGS: an inward remittance IS an international transaction.
            # Tagging it RTGS left the INT channel completely unused by legitimate
            # traffic, which made "channel = INT" a perfect crime label for any ML
            # model (see FIELD-NOTES Phase 6).
            r = ref()
            ev.append((at(rng.randrange(0, 4), 11), [(acct, "CR", "INT", p.remittance,
                       p.remit_from, r, f"INW-RMT/CR/{r}/{p.remit_from}")]))

        if p.pocket_money:
            parent = f"{rng.choice('SMRKVA')} {p.full_name.split()[-1].upper()}"
            pv = parent.split()[-1].lower() + "@oksbi"
            for w in range(days // 7):
                r = ref()
                ev.append((at(w * 7, 7, 15), [(acct, "CR", "UPI", p.pocket_money, parent, pv,
                                               f"UPI/CR/{r}/{pv}")]))

    for p in salaried_and_students:
        acct = account_id(p.customer_id)
        pool = merchants
        for d in range(days):
            for _ in range(rng.choice([0, 0, 1, 1, 2])):
                if not pool:
                    break
                m = rng.choice(pool)
                lo, hi = _merchant_price_range(m)
                amt = rng.randrange(lo, hi)
                r = ref()
                ev.append((at(d, rng.randrange(9, 22)), [
                    (acct, "DR", "UPI", amt, m.full_name, m.vpa, f"UPI/DR/{r}/{m.vpa}"),
                    (account_id(m.customer_id), "CR", "UPI", amt, p.full_name, p.vpa,
                     f"UPI/CR/{r}/{p.vpa}"),
                ]))

    for payer, payee in _friend_pairs(rng, profiles):
        if rng.random() < 0.35:
            amt = rng.randrange(4, 50) * 50
            r = ref()
            ev.append((at(rng.randrange(0, days), rng.randrange(10, 22)), [
                (account_id(payer.customer_id), "DR", "UPI", amt, payee.full_name, payee.vpa,
                 f"UPI/DR/{r}/{payee.vpa}"),
                (account_id(payee.customer_id), "CR", "UPI", amt, payer.full_name, payer.vpa,
                 f"UPI/CR/{r}/{payer.vpa}"),
            ]))

    for p in businesses:
        acct = account_id(p.customer_id)
        for d in range(days):
            for _ in range(rng.randrange(0, 3)):
                amt = rng.randrange(15, 81) * 1000
                r, ch, f = ref(), rng.choice(["IMPS", "NEFT"]), rng.choice(FIRMS)
                ev.append((at(d, rng.randrange(10, 18)), [(acct, "CR", ch, amt, f, r,
                                                           f"{ch}/CR/{r}/{f}")]))
        for w in range(days // 7):
            amt = rng.randrange(40, 121) * 1000
            r, f = ref(), rng.choice(FIRMS)
            ev.append((at(w * 7 + 3, rng.randrange(10, 16)), [(acct, "DR", "NEFT", amt, f, r,
                                                               f"NEFT/DR/{r}/{f} PURCHASE")]))
        for w in range(days // 7):
            r = ref()
            ev.append((at(w * 7 + 5, 17), [(acct, "DR", "NEFT", rng.randrange(8, 31) * 1000,
                                            "GSTN", r, f"GST/DR/{r}/EPAYMENT")]))
        # Trading businesses bank cash too, in the SAME size band structuring
        # uses (~30k-95k). Giving cash only to merchants left business accounts —
        # exactly the segment structuring targets — with zero legitimate cash, so
        # "a business that deposited cash" stayed a perfect crime label even after
        # merchants got theirs. Structuring is only hard when it has somewhere to
        # hide (see FIELD-NOTES Phase 6).
        for d in range(days):
            if rng.random() < 0.35:
                r = ref()
                ev.append((at(d, rng.randrange(10, 18)), [
                    (acct, "CR", "CASH", rng.randrange(30, 96) * 1000, None, None,
                     f"CASH DEP/CR/{r}/BR-{rng.randrange(10, 99)}")]))

    for m in merchants:
        acct = account_id(m.customer_id)
        lo, hi = _merchant_price_range(m)
        for d in range(days):
            for _ in range(rng.randrange(3, 7)):
                amt = rng.randrange(lo, hi)
                r = ref()
                cust = f"cust{rng.randrange(1000, 9999)}@ok{rng.choice(['sbi', 'hdfc', 'icici'])}"
                ev.append((at(d, rng.randrange(8, 23)), [(acct, "CR", "UPI", amt, None, cust,
                                                          f"UPI/CR/{r}/{cust}")]))
        for w in range(days // 7):
            r = ref()
            restock = int(m.opening_balance * rng.randrange(30, 61) / 100)
            ev.append((at(w * 7 + 5, 9), [(acct, "DR", "NEFT", restock, "DISTRIBUTOR", r,
                                           f"NEFT/DR/{r}/STOCK PURCHASE")]))
        # Shops bank their cash takings. Without this the CASH channel was used
        # ONLY by injected structuring, so "this account ever deposited cash" was
        # a perfect crime label — a detector could score 100% while learning
        # nothing about laundering (see FIELD-NOTES Phase 6). Real structuring has
        # to hide among real cash banking, which is what makes it hard.
        for d in range(days):
            if rng.random() < 0.45:
                takings = rng.randrange(int(lo * 6), int(hi * 12))
                r = ref()
                ev.append((at(d, rng.randrange(9, 19)), [
                    (acct, "CR", "CASH", takings, None, None,
                     f"CASH DEP/CR/{r}/BR-{rng.randrange(10, 99)}")]))

    return ev


def _post_all(conn: duckdb.DuckDBPyConnection, profiles: list[Profile], events: list) -> int:
    """Same no-overdraft rule as seed.py: a broke agent simply doesn't spend."""
    balances = {account_id(p.customer_id): p.opening_balance for p in profiles}
    rows = []
    for ts, legs in sorted(events, key=lambda e: e[0]):
        if any(d == "DR" and amt > balances[acct] for acct, d, _ch, amt, *_ in legs):
            continue
        for acct, direction, channel, amount, cp_name, cp_ref, narration in legs:
            balances[acct] += amount if direction == "CR" else -amount
            rows.append((ts, acct, direction, channel, amount, cp_name, cp_ref, narration,
                         balances[acct]))
    bulk_insert(conn, "transactions", _TXN_COLUMNS, rows)
    return len(rows)


def load(conn: duckdb.DuckDBPyConnection, n: int = 10000, days: int = 30,
         start: date = date(2026, 7, 1), seed: int = 42) -> int:
    """Generate n customers and post `days` days of life. Returns transactions posted."""
    profiles = generate(n, seed=seed)
    _insert_people(conn, profiles)
    events = life_events(random.Random(seed), profiles, start, days)
    return _post_all(conn, profiles, events)
