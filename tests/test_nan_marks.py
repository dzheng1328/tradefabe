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


# ------------------------------------------------------------------ save backstop
def test_save_refuses_to_write_a_nan_token(book, tmp_path, monkeypatch):
    # Python emits a bare `NaN`, which is NOT valid JSON -- JSON.parse and jq both reject
    # the whole file. This is the backstop if some future path bypasses mark().
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    book["history"] = [["2026-07-26T06:38", float("nan")]]
    with pytest.raises(ValueError):
        books.save(book)


def test_save_writes_strict_json_normally(book, tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    book["history"] = [["2026-07-26T07:00", 1500.0]]
    books.save(book)
    text = (tmp_path / "test_book.json").read_text()
    # parse_constant fires on NaN/Infinity, i.e. exactly the non-standard tokens
    json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


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


# ------------------------------------------------------- no backward time travel
def _bar(day, spy=100.0, ief=50.0):
    """A price row labelled with the bar it came from, the way px.iloc[-1] is."""
    s = pd.Series({"SPY": spy, "IEF": ief})
    s.name = pd.Timestamp(day)
    return s


def test_a_mark_never_regresses_to_an_older_bar(book):
    # the dashboard square wave: yfinance's newest row comes and goes, so equity jumped
    # between Friday's close and Thursday's close and back again
    assert books.mark(book, "t1", _bar("2026-07-24", spy=110.0)) is True
    friday = list(book["history"])
    assert books.mark(book, "t2", _bar("2026-07-23", spy=100.0)) is False
    assert book["history"] == friday, "equity may stand still but must not travel back"


def test_the_same_bar_may_be_re_marked(book):
    assert books.mark(book, "t1", _bar("2026-07-24")) is True
    assert books.mark(book, "t2", _bar("2026-07-24")) is True
    assert len(book["history"]) == 2


def test_a_newer_bar_is_accepted(book):
    assert books.mark(book, "t1", _bar("2026-07-23", spy=100.0)) is True
    assert books.mark(book, "t2", _bar("2026-07-24", spy=110.0)) is True
    assert book["history"][-1][1] > book["history"][0][1]


def test_the_bar_actually_used_is_recorded(book):
    books.mark(book, "t1", _bar("2026-07-24"))
    assert book["last_price_bar"] == "2026-07-24"


def test_an_unlabelled_series_still_marks(book):
    # plain Series with no .name -- must not crash or silently refuse
    assert books.mark(book, "t1", _px()) is True


def test_rebalance_refuses_an_older_bar(book):
    w = pd.Series({"SPY": 0.6, "IEF": 0.4})
    assert books.rebalance_to(book, w, "2026-07-24", _bar("2026-07-24"), 5.0) is True
    before = dict(book["positions"])
    assert books.rebalance_to(book, w, "2026-07-23", _bar("2026-07-23"), 5.0) is False
    assert book["positions"] == before


# ------------------------------------------------------- duplicate keys
def test_a_repeated_key_is_not_appended_twice_even_when_not_last(book):
    """run_daily() keys on a bare date, run_mark() on a full timestamp, so the two
    interleave. mark() used to compare only against history[-1], so a bare date that
    reappeared after some timestamps was appended a SECOND time -- 25 duplicate keys
    accumulated in the live ledger before this was caught."""
    books.mark(book, "2026-07-23", _px())
    books.mark(book, "2026-07-24T21:44", _px())
    books.mark(book, "2026-07-24T21:50", _px())
    books.mark(book, "2026-07-23", _px(spy=999.0))     # the interleaved repeat

    keys = [k for k, _ in book["history"]]
    assert len(keys) == len(set(keys)), f"duplicate keys: {keys}"
    assert keys.count("2026-07-23") == 1


def test_a_repeated_key_does_not_rewrite_the_first_valuation(book):
    # the first valuation of a bar is the record -- see test_books.py
    books.mark(book, "2026-07-23", _px())
    first = book["history"][0][1]
    books.mark(book, "2026-07-24T00:00", _px())
    books.mark(book, "2026-07-23", _px(spy=999.0))
    assert book["history"][0][1] == first
