from datetime import datetime

from launderlab.db.ledger import connect
from launderlab.detect.rules import Alert
from launderlab.detect.scoring import score


def _account(conn, cid, acct):
    conn.execute(
        "INSERT INTO customers VALUES (?,'x','2000-01-01','salaried','Hyderabad','full','low',?)",
        [cid, datetime(2020, 1, 1)],
    )
    conn.execute(
        "INSERT INTO accounts VALUES (?,?,'savings','X','active',?)",
        [acct, cid, datetime(2020, 1, 1)],
    )


def _txn(conn, acct, amount=1000):
    conn.execute(
        "INSERT INTO transactions (ts, account_id, direction, channel, amount,"
        " narration, balance_after) VALUES (?,?,?,?,?,?,?)",
        [datetime(2026, 7, 1), acct, "CR", "UPI", amount, "x", amount],
    )
    return conn.execute("SELECT txn_id FROM transactions ORDER BY txn_id DESC LIMIT 1").fetchone()[0]


def test_score_precision_recall_and_false_positive_rate():
    conn = connect(":memory:")
    for i, acct in enumerate(["A1", "A2", "A3", "A4"]):
        _account(conn, f"C{i}", acct)
    txn_a1 = _txn(conn, "A1")
    txn_a2 = _txn(conn, "A2")
    _txn(conn, "A3")  # A3 is dirty too (scheme S2) but never alerted - a miss
    _txn(conn, "A4")  # A4 is clean, never alerted, not part of the picture

    # ground truth: scheme S1 lives on A1, scheme S2 lives on A2 and A3
    conn.execute("INSERT INTO scheme_labels VALUES (?, 'S1', 'structuring', 'placement')",
                 [txn_a1])
    conn.execute("INSERT INTO scheme_labels VALUES (?, 'S2', 'layering', 'source')", [txn_a2])

    # alerts: A1 (true positive), A2 (true positive), A5 (false positive - not
    # even a real customer, but that's fine, scoring only cares whether it's
    # inside the "dirty accounts" set)
    alerts = [
        Alert("A1", "structuring_burst", "x", datetime(2026, 7, 1), 1000),
        Alert("A2", "rapid_pass_through", "x", datetime(2026, 7, 1), 1000),
        Alert("A5", "dormancy_burst", "x", datetime(2026, 7, 1), 1000),
    ]

    report = score(conn, alerts)
    assert report.total_alerts == 3
    assert report.true_positive_accounts == 2
    assert report.false_positive_accounts == 1
    assert report.precision == 2 / 3
    assert report.false_positive_rate == 1 / 3
    # S1 detected (A1 alerted), S2 detected too (A2 alerted, even though A3 -
    # the OTHER account in scheme S2 - was missed: one hit is enough to call
    # the scheme caught, same as a real investigator would read it)
    assert report.schemes_detected == 2
    assert report.schemes_total == 2
    assert report.overall_recall == 1.0
    assert report.by_typology["structuring"] == (1, 1)
    assert report.by_typology["layering"] == (1, 1)


def test_score_with_no_alerts_is_all_zero():
    conn = connect(":memory:")
    report = score(conn, [])
    assert report.total_alerts == 0
    assert report.precision == 0.0
    assert report.false_positive_rate == 0.0


def test_score_missed_scheme_shows_zero_recall_for_it():
    conn = connect(":memory:")
    _account(conn, "C1", "A1")
    txn = _txn(conn, "A1")
    conn.execute("INSERT INTO scheme_labels VALUES (?, 'S1', 'structuring', 'placement')", [txn])

    report = score(conn, [])  # nothing alerted at all
    assert report.schemes_detected == 0
    assert report.schemes_total == 1
    assert report.by_typology["structuring"] == (0, 1)
