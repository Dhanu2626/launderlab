import random
from datetime import date

import pytest

from launderlab.db.ledger import connect
from launderlab.typology import high_risk_geography
from launderlab.typology.high_risk_geography import HIGH_RISK_COUNTRIES
from launderlab.world.generate import load


@pytest.fixture()
def world(tmp_path):
    conn = connect(tmp_path / "w.duckdb")
    load(conn, n=200, days=30, seed=9)
    return conn


def _business_accounts(conn, limit=10) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment = 'business' ORDER BY account_id LIMIT ?", [limit]
    ).fetchall()]


def _business_and_nri_accounts(conn, limit=15) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT account_id FROM accounts a JOIN customers c USING (customer_id)"
        " WHERE c.segment IN ('business', 'nri') ORDER BY account_id LIMIT ?", [limit]
    ).fetchall()]


def test_injects_international_transactions(world):
    acct = _business_accounts(world, 1)[0]
    n = high_risk_geography.inject(world, "SCH-G1", acct, date(2026, 7, 3),
                                    random.Random(1), n_transactions=3)
    assert n == 3
    rows = world.execute(
        "SELECT t.channel, t.direction FROM transactions t"
        " JOIN scheme_labels l USING (txn_id) WHERE l.scheme_id = 'SCH-G1'"
    ).fetchall()
    assert len(rows) == 3
    assert all(channel == "INT" and direction in ("CR", "DR") for channel, direction in rows)

    typologies = {t for (t,) in world.execute(
        "SELECT typology FROM scheme_labels WHERE scheme_id = 'SCH-G1'"
    ).fetchall()}
    assert typologies == {"high_risk_geography"}


def test_category_label_matches_country_in_narration(world):
    # proves the txn_id<->row correlation is correct: each label's category must
    # match the FATF category of the country actually embedded in that same row
    country_category = {name: category for name, _iso, category in HIGH_RISK_COUNTRIES}
    acct = _business_accounts(world, 1)[0]
    high_risk_geography.inject(world, "SCH-G2", acct, date(2026, 7, 3), random.Random(2),
                                n_transactions=3)

    rows = world.execute(
        "SELECT t.counterparty_name, l.role FROM transactions t"
        " JOIN scheme_labels l USING (txn_id) WHERE l.scheme_id = 'SCH-G2'"
    ).fetchall()
    assert len(rows) == 3
    for counterparty_name, role in rows:
        country = counterparty_name.removeprefix("REMITTANCE ").rsplit(" ", 1)[0].title()
        assert country_category[country] == role


def test_never_overdraws_across_many_accounts_and_seeds(world):
    # includes NRI accounts, not just business - the scale proof run that first
    # caught this typology's overdraft bug used business+nri, and business-only
    # accounts happened not to trigger it (see FIELD-NOTES Day 12)
    accounts = _business_and_nri_accounts(world, 15)
    for i, acct in enumerate(accounts):
        for seed in range(8):
            # force n_transactions=3 every call: worst case for the within-call
            # cumulative-debit bug this test exists to catch
            high_risk_geography.inject(world, f"SCH-STRESS-{i}-{seed}", acct,
                                        date(2026, 7, 1), random.Random(seed),
                                        n_transactions=3)
    min_bal = world.execute("SELECT min(balance_after) FROM transactions").fetchone()[0]
    assert float(min_bal) >= 0


def test_balances_still_reconcile_globally(world):
    acct = _business_accounts(world, 1)[0]
    high_risk_geography.inject(world, "SCH-G3", acct, date(2026, 7, 5), random.Random(3))

    running = {}
    rows = world.execute(
        "SELECT account_id, direction, amount, balance_after FROM transactions"
        " ORDER BY account_id, ts, txn_id"
    ).fetchall()
    for account_id, direction, amount, balance_after in rows:
        if account_id not in running:
            running[account_id] = balance_after - amount if direction == "CR" \
                else balance_after + amount
        running[account_id] += amount if direction == "CR" else -amount
        assert running[account_id] == balance_after


def test_deterministic(world):
    acct = _business_accounts(world, 1)[0]
    n1 = high_risk_geography.inject(world, "SCH-A", acct, date(2026, 7, 1), random.Random(9))

    conn2 = connect(":memory:")
    load(conn2, n=200, days=30, seed=9)
    n2 = high_risk_geography.inject(conn2, "SCH-A", acct, date(2026, 7, 1), random.Random(9))
    assert n1 == n2


def test_unknown_account_raises(world):
    with pytest.raises(ValueError):
        high_risk_geography.inject(world, "SCH-X", "GHOST", date(2026, 7, 1), random.Random(1))
