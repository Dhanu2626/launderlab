"""Procedurally generate a realistic customer population at any scale.

seed.py hand-crafts 25 people so we can eyeball every row. That doesn't scale to
10k — this module generates profiles from distributions instead, reusing the same
five segments and behavioral vocabulary (salary, rent/EMI, P2P, merchant footfall,
business receipts) that seed.py proved out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

REFERENCE_DATE = date(2026, 7, 1)
BANKS = ["okhdfc", "okicici", "oksbi", "okaxis"]

SEGMENT_WEIGHTS = {
    "salaried": 0.50,
    "student": 0.20,
    "merchant": 0.15,
    "business": 0.10,
    "nri": 0.05,
}
AGE_RANGE = {
    "salaried": (23, 45),
    "student": (18, 24),
    "merchant": (25, 60),
    "business": (28, 60),
    "nri": (25, 50),
}

CITIES = ["Hyderabad", "Bengaluru", "Mumbai", "Pune", "Delhi", "Chennai", "Kolkata",
          "Kochi", "Ahmedabad"]
CITY_WEIGHTS = [0.25, 0.15, 0.15, 0.10, 0.10, 0.08, 0.07, 0.05, 0.05]

FIRST_NAMES = [
    "Asha", "Vikram", "Meera", "Rohit", "Farhan", "Divya", "Arjun", "Kavya", "Suresh",
    "Lakshmi", "Imran", "Nilesh", "Rahul", "Sneha", "Aditya", "Priya", "Anand", "Ritu",
    "Karthik", "Pooja", "Sanjay", "Anjali", "Manoj", "Neha", "Ravi", "Deepa", "Sameer",
    "Swathi", "Vishal", "Anita", "Naveen", "Shreya", "Gopal", "Rekha", "Ajay", "Nandini",
    "Praveen", "Madhuri", "Kiran", "Bhavana",
]
SURNAMES = [
    "Rao", "Iyer", "Pillai", "Sharma", "Ali", "Nair", "Reddy", "Krishnan", "Gupta",
    "Devi", "Sheikh", "Patel", "Verma", "Kulkarni", "Singh", "Menon", "Malhotra",
    "Naidu", "Chowdhury", "Bose", "Mehta", "Joshi", "Desai", "Kumar", "Pandey",
]
EMPLOYERS = [
    "TECHNOVA SOLUTIONS", "QUANTEDGE ANALYTICS", "BRIGHTPATH EDUTECH", "APEXCORE SYSTEMS",
    "MEDIQUICK LABS", "NILGIRI FOODS LTD", "SKYBRIDGE LOGISTICS", "PIXELWEAVE DESIGN",
    "VERTEX CONSULTING", "STARLINE RETAIL", "OMEGA HEALTHCARE", "BLUEPEAK FINANCE",
]
NRI_COUNTRIES = [("Dubai", "AE"), ("Singapore", "SG"), ("London", "GB"),
                  ("Toronto", "CA"), ("New York", "US")]
NRI_WEIGHTS = [0.40, 0.20, 0.15, 0.15, 0.10]


@dataclass(frozen=True)
class Profile:
    customer_id: str
    full_name: str
    dob: date
    segment: str
    city: str
    account_type: str
    kyc_level: str
    risk_rating: str
    opening_balance: int
    vpa: str
    # segment-specific; zero/empty when not applicable
    salary: int = 0
    employer: str = ""
    pocket_money: int = 0
    remittance: int = 0
    remit_from: str = ""
    monthly_revenue: int = 0


def _clip(v: float, lo: float, hi: float) -> int:
    return int(min(max(v, lo), hi))


def _dob(rng: random.Random, segment: str) -> date:
    lo, hi = AGE_RANGE[segment]
    age_days = rng.randrange(lo * 365, hi * 365)
    return REFERENCE_DATE - timedelta(days=age_days)


def _person(rng: random.Random, idx: int, segment: str) -> Profile:
    customer_id = f"P{idx:06d}"
    first, last = rng.choice(FIRST_NAMES), rng.choice(SURNAMES)
    name = f"{first} {last}"
    city = rng.choices(CITIES, weights=CITY_WEIGHTS, k=1)[0]
    vpa = f"{first.lower()}.{last.lower()}{idx % 100}@{rng.choice(BANKS)}"
    account_type = "current" if segment in ("business", "merchant") else "savings"
    risk_rating = "medium" if segment in ("business", "nri") else "low"

    salary = employer = pocket_money = remittance = remit_from = monthly_revenue = 0
    if segment == "salaried":
        salary = round(_clip(rng.lognormvariate(10.9, 0.4), 20000, 200000), -3)
        employer = rng.choice(EMPLOYERS)
        opening = round(salary * rng.uniform(0.5, 1.2))
    elif segment == "student":
        pocket_money = int(round(rng.uniform(3000, 8000), -2))
        opening = round(rng.uniform(2000, 9000))
    elif segment == "nri":
        remittance = round(_clip(rng.lognormvariate(11.7, 0.5), 40000, 400000), -3)
        country, iso = rng.choices(NRI_COUNTRIES, weights=NRI_WEIGHTS, k=1)[0]
        remit_from = f"{name.upper()} {country.upper()} {iso}"
        opening = round(rng.uniform(200000, 800000), -3)
    else:  # business / merchant
        monthly_revenue = round(_clip(rng.lognormvariate(12.6, 0.6), 80000, 2000000), -3)
        opening = round(monthly_revenue * rng.uniform(0.15, 0.4))
        name = f"{rng.choice(SURNAMES).upper()} {'TRADERS' if segment == 'business' else 'STORE'}"

    return Profile(customer_id, name, _dob(rng, segment), segment, city, account_type,
                    "full", risk_rating, opening, vpa, salary, employer, pocket_money,
                    remittance, remit_from, monthly_revenue)


def generate(n: int, seed: int = 42) -> list[Profile]:
    """Generate n customer profiles from segment/income/city distributions.

    Deterministic for a given (n, seed) — same call always returns the same population.
    """
    rng = random.Random(seed)
    segments = rng.choices(list(SEGMENT_WEIGHTS), weights=list(SEGMENT_WEIGHTS.values()), k=n)
    return [_person(rng, i, seg) for i, seg in enumerate(segments)]
