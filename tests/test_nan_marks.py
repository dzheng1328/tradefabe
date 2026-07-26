"""A partial price bar must never reach the ledger (2026-07-26).

yfinance intermittently appends a bar for the current, still-open or non-trading day:
the row exists but some tickers are NaN. Three things then went wrong at once, and all
three are pinned here:

  1. `equity()`'s `float(px.get(t, 0) or 0)` guard did not screen NaN -- NaN is truthy in
     Python, so `nan or 0` is `nan`, and the NaN reached `book["history"]`.
  2. `mark()` wrote it anyway. 8 of 12 books logged a literal NaN equity in one cycle and
     the job still exited 0.
  3. `rebalance_to()`'s `p <= 0` screen did not catch it either (`nan <= 0` is False), so
     a bad bar would have sized positions off a NaN.

Plus the visible symptom that started the investigation: on a weekend with markets shut,
books flip-flopped between two equity values, because the partial bar came and went."""
import math

import numpy as np
import pandas as pd
import pytest

from tradefabe import books, engine


@pytest.fixture
def book():
    return {"name": "test_book", "cash": 1000.0, "positions": {"SPY": 10.0, "IEF": 5.0},
            "history": [], "last_run": None, "last_rebalance": None}


def _px(spy=100.0, ief=50.0):
    return pd.Series({"SPY": spy, "IEF": ief})


# ------------------------------------------------------------------ equity
def test_equity_is_nan_when_a_held_name_has_no_price(book):
    assert math.isnan(books.equity(book, _px(spy=float("nan"))))


def test_equity_is_not_silently_zeroed(book):
    # coercing the bad price to 0 would report 1500 -- a 40% "loss" that never happened
    eq = books.equity(book, _px(spy=float("nan")))
    assert not math.isfinite(eq), "a 0-priced leg is a silent 100% loss on that leg"


def test_equity_is_normal_when_everything_prices(book):
    assert books.equity(book, _px()) == pytest.approx(1000 + 10 * 100 + 5 * 50)


# ------------------------------------------------------------------ mark
def test_mark_refuses_to_write_nan_and_returns_false(book):
    assert books.mark(book, "2026-07-26T06:38", _px(spy=float("nan"))) is False
    assert book["history"] == [], "a NaN in the ledger is permanent"


def test_mark_writes_normally_when_priced(book):
    assert books.mark(book, "2026-07-26T07:00", _px()) is True
    assert len(book["history"]) == 1
    assert math.isfinite(book["history"][0][1])


def test_a_skipped_mark_leaves_earlier_history_intact(book):
    books.mark(book, "2026-07-26T07:00", _px())
    good = list(book["history"])
    books.mark(book, "2026-07-26T08:00", _px(ief=float("nan")))
    assert book["history"] == good


# ------------------------------------------------------------------ rebalance
def test_rebalance_refuses_a_partial_bar(book):
    before = dict(book["positions"])
    w = pd.Series({"SPY": 0.6, "IEF": 0.4})
    assert books.rebalance_to(book, w, "2026-07-26", _px(spy=float("nan")), 5.0) is False
    assert book["positions"] == before, "must not trade on a bar it cannot price"


def test_rebalance_does_not_size_positions_off_a_nan(book):
    # the real damage: nan <= 0 is False, so the old guard let tgt_sh = (w*eq)/nan through
    w = pd.Series({"SPY": 0.6, "IEF": 0.4})
    books.rebalance_to(book, w, "2026-07-26", _px(ief=float("nan")), 5.0)
    assert all(math.isfinite(sh) for sh in book["positions"].values())


def test_rebalance_still_works_on_a_complete_bar(book):
    w = pd.Series({"SPY": 0.6, "IEF": 0.4})
    assert books.rebalance_to(book, w, "2026-07-26", _px(), 5.0) is True
    assert set(book["positions"]) == {"SPY", "IEF"}
    assert all(math.isfinite(sh) for sh in book["positions"].values())


# ------------------------------------------------------- incomplete tail trimming
def _frame(n=5):
    idx = pd.bdate_range("2026-07-20", periods=n)
    return pd.DataFrame({"SPY": np.arange(100.0, 100.0 + n),
                         "IEF": np.arange(50.0, 50.0 + n)}, index=idx)


def test_trailing_partial_bar_is_dropped():
    px = _frame()
    px.iloc[-1, 0] = np.nan                     # the phantom bar: SPY missing
    out = engine.drop_incomplete_tail(px)
    assert len(out) == len(px) - 1
    assert out.notna().all().all()


def test_a_complete_frame_is_untouched():
    px = _frame()
    pd.testing.assert_frame_equal(engine.drop_incomplete_tail(px), px)


def test_leading_nans_are_preserved():
    # a ticker whose history starts later than the universe's is legitimate, not partial
    px = _frame()
    px.iloc[0, 1] = np.nan
    out = engine.drop_incomplete_tail(px)
    assert len(out) == len(px)


def test_multiple_trailing_partial_bars_are_all_dropped():
    px = _frame(6)
    px.iloc[-2:, 0] = np.nan
    assert len(engine.drop_incomplete_tail(px)) == 4


def test_empty_frame_does_not_explode():
    assert engine.drop_incomplete_tail(pd.DataFrame()).empty
