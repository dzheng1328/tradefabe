"""Ledger accounting: rebalance_to conserves equity minus cost, turnover math, short
handling. All core-logic tests operate on in-memory book dicts (the same shape
books.load() returns) -- never touching the real state/paper/ ledger. Only the
save/load round-trip test touches disk, and it's isolated to a tmp_path via
monkeypatch."""
import pandas as pd
import pytest

from tradefabe import books


def fresh_book(cash=100_000.0, positions=None):
    return {"name": "test", "cash": cash, "positions": dict(positions or {}),
            "history": [], "last_run": None, "last_rebalance": None}


def test_rebalance_to_fresh_book_conserves_equity_minus_cost():
    book = fresh_book()
    px = pd.Series({"SPY": 100.0, "TLT": 50.0})
    weights = pd.Series({"SPY": 0.5, "TLT": 0.3})
    books.rebalance_to(book, weights, "2024-01-02", px, cost_bps=5.0)

    # tgt_sh SPY=500, TLT=600 -> turnover = 500*100 + 600*50 = 80,000 -> cost = 40.0
    assert book["positions"] == {"SPY": 500.0, "TLT": 600.0}
    assert book["cash"] == pytest.approx(19_960.0)
    assert books.equity(book, px) == pytest.approx(100_000.0 - 40.0)


def test_rebalance_to_turnover_only_charges_the_change():
    book = fresh_book(cash=60_000.0, positions={"SPY": 400.0})
    px = pd.Series({"SPY": 100.0})
    weights = pd.Series({"SPY": 0.6})
    eq0 = books.equity(book, px)
    assert eq0 == pytest.approx(100_000.0)

    books.rebalance_to(book, weights, "2024-01-02", px, cost_bps=5.0)
    # tgt_sh = 600, cur_sh = 400 -> turnover = |600-400|*100 = 20,000 -> cost = 10.0
    # cash = eq0 - new_position_value - cost = 100,000 - 60,000 - 10
    assert book["positions"] == {"SPY": 600.0}
    assert book["cash"] == pytest.approx(39_990.0)
    assert books.equity(book, px) == pytest.approx(eq0 - 10.0)


def test_rebalance_to_short_position_receives_cash_and_conserves_equity():
    book = fresh_book()
    px = pd.Series({"SPY": 100.0})
    weights = pd.Series({"SPY": -0.3})
    books.rebalance_to(book, weights, "2024-01-02", px, cost_bps=5.0)

    # tgt_sh = -300 -> turnover = |-300|*100 = 30,000 -> cost = 15.0
    # shorting SPY brings in cash: cash = 100,000 - (-30,000) - 15
    assert book["positions"] == {"SPY": -300.0}
    assert book["cash"] == pytest.approx(129_985.0)
    assert books.equity(book, px) == pytest.approx(100_000.0 - 15.0)


def test_rebalance_to_closed_position_counts_in_turnover():
    book = fresh_book(cash=80_000.0, positions={"QQQ": 100.0})
    px = pd.Series({"SPY": 100.0, "QQQ": 200.0})
    eq0 = books.equity(book, px)
    assert eq0 == pytest.approx(100_000.0)

    weights = pd.Series({"SPY": 0.5})   # QQQ dropped entirely
    books.rebalance_to(book, weights, "2024-01-02", px, cost_bps=5.0)

    # opening SPY: |500-0|*100 = 50,000; closing QQQ: |100|*200 = 20,000 -> turnover 70,000
    # cost = 35.0
    assert book["positions"] == {"SPY": 500.0}   # QQQ fully closed, not just zeroed
    assert book["cash"] == pytest.approx(49_965.0)
    assert books.equity(book, px) == pytest.approx(eq0 - 35.0)


def test_mark_appends_new_date_but_does_not_refresh_same_date():
    book = fresh_book(cash=50_000.0, positions={"SPY": 100.0})
    px1 = pd.Series({"SPY": 110.0})
    books.mark(book, "2024-01-02", px1)
    assert book["history"] == [["2024-01-02", 61_000.0]]
    assert book["last_run"] is not None

    # same date, price moved -- mark() intentionally does not rewrite the day's entry
    px2 = pd.Series({"SPY": 200.0})
    books.mark(book, "2024-01-02", px2)
    assert book["history"] == [["2024-01-02", 61_000.0]]   # unchanged

    # new date -- appends
    books.mark(book, "2024-01-03", px2)
    assert book["history"] == [["2024-01-02", 61_000.0], ["2024-01-03", 70_000.0]]


def test_save_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    name = "unit_test_book_do_not_use_in_prod"

    book = books.load(name)
    assert book == {"name": name, "cash": 100_000.0, "positions": {}, "history": [],
                    "last_run": None, "last_rebalance": None}

    book["positions"] = {"SPY": 12.5}
    book["cash"] = 87_500.0
    books.save(book)

    reloaded = books.load(name)
    assert reloaded == book
