"""Manual-only book retirement (#113, DOCTRINE v1.6).

The load-bearing test in this file is
`test_no_cycle_path_ever_retires_a_book_on_its_own`. Everything else checks the mechanism;
that one checks the POLICY -- that no code path in the engine can retire a book without a
human. DOCTRINE v1.6's reasoning is that auto-retiring losing books would filter the forward
paper record on results, manufacturing survivorship bias in the one dataset here that has
none. A rule stated only in a markdown file is a rule that quietly stops being true, so it
is asserted here against the real cycle functions."""
import numpy as np
import pandas as pd
import pytest

from tradefabe import books, carry_live, cli, hourly, runner, signals


def _prices(n=300):
    idx = pd.bdate_range("2024-01-02", periods=n)
    return pd.DataFrame({"A": np.linspace(100.0, 300.0, n),
                         "B": np.full(n, 50.0)}, index=idx)


def _open_book(name, px):
    """A real live book, opened the way the engine opens one."""
    runner._run_book(name, "D", lambda p, n: pd.Series({"A": 1.0}), px,
                     "2024-06-01", px.iloc[-1], verbose=False, stamp="2024-06-01T22:00")
    return books.load(name)


# ------------------------------------------------------------------ the mechanism
def test_retire_freezes_the_book_and_records_who_asked_and_why(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    px = _prices()
    _open_book("bk", px)

    book = books.retire("bk", "bleeding 70%/yr, no longer worth the cycle time")
    assert books.is_retired(book)
    assert book["retired"]["reason"].startswith("bleeding 70%/yr")
    assert book["retired"]["at"]                      # a stamp, not just a bool
    assert books.is_retired(books.load("bk"))         # persisted, not in-memory only


def test_retire_refuses_a_name_with_no_ledger_on_disk(monkeypatch, tmp_path):
    """books.load() synthesizes a fresh $100k book for ANY name, so without this guard a
    typo would create a retired phantom book that then shows up in the dashboard forever."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    with pytest.raises(KeyError):
        books.retire("tsmom_12mm", "typo")
    assert not (tmp_path / "tsmom_12mm.json").exists()


def test_retire_refuses_an_empty_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    _open_book("bk", _prices())
    with pytest.raises(ValueError):
        books.retire("bk", "   ")
    assert not books.is_retired(books.load("bk"))


def test_retiring_twice_keeps_the_FIRST_decision(monkeypatch, tmp_path):
    """The original stamp and reason are the record. A second call must not overwrite when
    it happened or why."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    _open_book("bk", _prices())
    first = books.retire("bk", "reason one", when="2026-01-01T00:00")["retired"]
    again = books.retire("bk", "reason two")["retired"]
    assert again == first


def test_unretire_restores_the_book_without_touching_its_history(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    px = _prices()
    _open_book("bk", px)
    hist_before = list(books.load("bk")["history"])
    books.retire("bk", "pausing")
    book = books.unretire("bk")
    assert not books.is_retired(book)
    assert "retired" not in book
    assert book["history"] == hist_before


# ------------------------------------------------------------------ the cycle honours it
def test_run_book_skips_a_retired_book_and_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    px = _prices()
    _open_book("bk", px)
    books.retire("bk", "frozen for the test")
    before = (tmp_path / "bk.json").read_text()

    runner._run_book("bk", "D", lambda p, n: pd.Series({"B": 1.0}), px,
                     "2024-06-02", px.iloc[-1], verbose=False, stamp="2024-06-02T22:00")

    assert (tmp_path / "bk.json").read_text() == before, \
        "a retired book's ledger must be byte-identical after a cycle"


def test_run_carry_accrues_nothing_for_a_retired_carry_book(monkeypatch, tmp_path):
    """run_carry() must bail BEFORE it hits the network -- a retired book should not even
    provoke a funding fetch. Any call to _funding_since here is a failure."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    books.save({"name": "carry_btc_eth", "cash": 0.0, "positions": {}, "equity": 111.0,
                "history": [["2026-01-01T00:00", 111.0]], "last_run": None,
                "last_rebalance": None})
    books.retire("carry_btc_eth", "frozen for the test")

    def _boom(*a, **k):                                        # noqa: ANN002, ANN003
        raise AssertionError("retired carry book must not fetch funding")
    monkeypatch.setattr(carry_live, "_funding_since", _boom)

    book = carry_live.run_carry()
    assert books.is_retired(book)
    assert book["equity"] == 111.0


def test_hourly_price_books_skip_a_retired_book_before_fetching(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    name = hourly.PRICE_BOOK_NAMES[0]
    books.save({"name": name, "cash": books.START_CASH, "positions": {}, "history": [],
                "last_run": None, "last_rebalance": None})
    books.retire(name, "frozen for the test")

    def _boom(*a, **k):                                        # noqa: ANN002, ANN003
        raise AssertionError("retired hourly book must not fetch bars")
    monkeypatch.setattr(hourly, "fetch_hourly", _boom)

    done = hourly.run_price_books(verbose=False)
    assert name not in done


def test_funding_timing_skips_a_retired_book(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    books.save({"name": "funding_timing_1h", "cash": 0.0, "positions": {}, "equity": 222.0,
                "history": [], "last_run": None, "last_rebalance": None})
    books.retire("funding_timing_1h", "frozen for the test")
    assert hourly.run_funding_timing(verbose=False) is None
    assert books.load("funding_timing_1h")["equity"] == 222.0


def test_write_summary_still_reports_a_retired_book(monkeypatch, tmp_path):
    """Retirement stops trading, not existence. Dropping the book from summary.csv would
    delete its forward record from every downstream view -- the opposite of the point."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runner, "STATE_DIR", tmp_path)
    name = runner.EQUITY_BOOKS[0]
    px = _prices()
    _open_book(name, px)
    books.retire(name, "frozen for the test")

    summary = runner.write_summary(px.iloc[-1])
    row = summary[summary["book"] == name]
    assert len(row) == 1
    assert row.iloc[0]["retired_at"]


# ------------------------------------------------------------------ THE POLICY GUARD
def test_no_cycle_path_ever_retires_a_book_on_its_own(monkeypatch, tmp_path):
    """DOCTRINE v1.6: retirement is manual-only, for every book, at any age, with no
    performance trigger. So no engine code path may WRITE the `retired` key.

    Driven from the real cycle entry point rather than by grepping: a book deep in
    drawdown, marked and rebalanced repeatedly, must come out un-retired."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    idx = pd.bdate_range("2024-01-02", periods=300)
    crashing = pd.DataFrame({"A": np.linspace(300.0, 3.0, 300),      # -99%
                             "B": np.full(300, 50.0)}, index=idx)
    name = "bk"
    for i in range(-40, 0):                      # 40 cycles of relentless losses
        sub = crashing.iloc[:len(crashing) + i]
        runner._run_book(name, "D", lambda p, n: pd.Series({"A": 1.0}), sub,
                         str(sub.index[-1].date()), sub.iloc[-1], verbose=False,
                         stamp=f"{sub.index[-1].date()}T22:00")

    book = books.load(name)
    assert not books.is_retired(book), "the engine retired a book by itself"
    assert "retired" not in book
    equity = books.equity(book, crashing.iloc[-1])
    assert equity < books.START_CASH * 0.5, "sanity: this book really did crater"


def test_the_only_writer_of_the_retired_key_is_books_retire():
    """Structural guard on the same policy, from the other direction: exactly one function
    in the shipped package assigns `["retired"]`. If a future change adds an automatic
    trigger somewhere, this fails even if that path isn't exercised by a test."""
    import pathlib
    src = pathlib.Path(books.__file__).parent
    writers = []
    for path in sorted(src.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if '["retired"]' in code and "=" in code.split('["retired"]')[1][:3]:
                writers.append(f"{path.name}:{lineno}")
    assert writers == ["books.py:" + str(_retire_assign_line())], writers


def _retire_assign_line():
    import inspect
    src, start = inspect.getsourcelines(books)
    for i, line in enumerate(src, start or 1):
        code = line.split("#", 1)[0]
        if '["retired"]' in code and "=" in code.split('["retired"]')[1][:3]:
            return i
    raise AssertionError("books.py no longer assigns book['retired']")


# ------------------------------------------------------------------ CLI
def test_cli_retire_requires_a_reason(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    _open_book("bk", _prices())
    monkeypatch.setattr("sys.argv", ["tradefabe", "retire", "bk"])
    assert cli.main() == 2
    assert "--reason" in capsys.readouterr().out
    assert not books.is_retired(books.load("bk"))


def test_cli_retire_then_unretire_round_trips(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    _open_book("bk", _prices())

    monkeypatch.setattr("sys.argv", ["tradefabe", "retire", "bk", "--reason", "done with it"])
    assert cli.main() == 0
    assert books.is_retired(books.load("bk"))
    assert "retired" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["tradefabe", "unretire", "bk"])
    assert cli.main() == 0
    assert not books.is_retired(books.load("bk"))


def test_cli_retire_reports_an_unknown_book_instead_of_creating_one(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["tradefabe", "retire", "nope", "--reason", "x"])
    assert cli.main() == 1
    assert "nothing to retire" in capsys.readouterr().out
    assert not (tmp_path / "nope.json").exists()


def test_cli_retire_without_a_book_name_is_a_usage_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["tradefabe", "retire"])
    assert cli.main() == 2
    assert "usage:" in capsys.readouterr().out


# ------------------------------------------------------------------ dashboard surface
def test_dashboard_renders_the_retirement_reason_from_the_ledger():
    import app
    note = app.retirement_note({"retired": {"at": "2026-07-29T12:00", "reason": "bleeding"}})
    assert note == {"at": "2026-07-29T12:00", "reason": "bleeding"}
    assert app.retirement_note({}) is None
    assert app.retirement_note(None) is None


def test_dashboard_tolerates_a_retirement_block_with_no_reason():
    """An older or hand-edited ledger must not crash the panel."""
    import app
    note = app.retirement_note({"retired": {"at": "2026-07-29T12:00"}})
    assert note["reason"] == "(no reason recorded)"


def test_signals_registry_is_untouched_by_retirement():
    """Retirement is a LEDGER state, not a roster edit. The strategy stays on the roster and
    in graveyard.csv -- so a retired book can be un-retired, and its verdict is unaffected."""
    assert "tsmom_12m" in signals.REGISTRY
