import pytest

from launderlab.db.ledger import connect
from launderlab.statement import render, write
from launderlab.world.seed import load


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    # module-scoped: statement rendering only reads, so one seeded load suffices
    c = connect(tmp_path_factory.mktemp("stmt") / "s.duckdb")
    load(c)
    return c


def test_render_has_holder_and_rows(conn):
    html = render(conn, "A001")
    assert "Asha Rao" in html
    assert "Opening balance" in html
    assert "NEFT/CR/" in html


def test_debit_credit_columns_split(conn):
    html = render(conn, "A001")
    assert '<td class="amt debit">85,000.00</td>' not in html
    assert '<td class="amt credit">85,000.00</td>' in html


def test_unknown_account_raises(conn):
    with pytest.raises(ValueError):
        render(conn, "GHOST")


def test_write_creates_file(conn, tmp_path):
    path = write(conn, "A001", tmp_path / "statements")
    assert path.exists()
    assert "Asha Rao" in path.read_text(encoding="utf-8")
