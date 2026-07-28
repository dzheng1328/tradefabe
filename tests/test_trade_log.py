"""The paper trade log and the ledger's own price record (#109).

`rebalance_to()` used to compute target shares, turnover and cost and then keep only the
resulting position, so a book could be watched but never seen ACTING. These pin the fill
records, the price snapshot the dashboard now prices from, and the bounded growth of both —
these ledgers are committed to git every cycle.
"""
import pandas as pd
import pytest

from tradefabe import books


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    return tmp_path


def px(**kw):
    return pd.Series(kw, dtype=float)


def fresh(name="t", cash=books.START_CASH):
    return {"name": name, "cash": cash, "positions": {}, "history": [],
            "last_run": None, "last_rebalance": None}


# ------------------------------------------------------------------ fills are recorded
def test_an_opening_rebalance_logs_one_buy_per_name(isolated):
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 0.5, "BBB": 0.5}), "2026-07-27",
                       px(AAA=100.0, BBB=50.0), 5.0, stamp="2026-07-27T22:00")
    t = b["trades"]
    assert [r["ticker"] for r in t] == ["AAA", "BBB"]
    assert {r["side"] for r in t} == {"BUY"}
    assert all(r["ts"] == "2026-07-27T22:00" for r in t)
    assert t[0]["shares"] == pytest.approx(500.0)        # 50% of 100k at $100
    assert t[0]["price"] == 100.0
    assert t[0]["notional"] == pytest.approx(50_000.0)
    assert t[0]["position_after"] == pytest.approx(500.0)


def test_a_short_is_logged_as_short_and_its_unwind_as_cover(isolated):
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": -1.0}), "d1", px(AAA=100.0), 0.0, stamp="s1")
    assert b["trades"][-1]["side"] == "SHORT"
    assert b["trades"][-1]["shares"] < 0
    books.rebalance_to(b, pd.Series({"AAA": 0.0}), "d2", px(AAA=100.0), 0.0, stamp="s2")
    assert b["trades"][-1]["side"] == "COVER"
    assert b["trades"][-1]["position_after"] == 0.0


def test_a_sign_flip_is_named_by_where_it_lands(isolated):
    """Long -> short in one rebalance is one fill. Naming it SELL would be true of the
    order and useless to a reader of a long/short book; it ends SHORT, so it reads SHORT."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "d1", px(AAA=100.0), 0.0, stamp="s1")
    books.rebalance_to(b, pd.Series({"AAA": -1.0}), "d2", px(AAA=100.0), 0.0, stamp="s2")
    last = b["trades"][-1]
    assert last["side"] == "SHORT"
    assert last["position_after"] < 0


def test_closing_a_name_entirely_is_logged(isolated):
    """A name dropped from the target weights leaves `positions` and must still appear —
    it is the fill most worth seeing, and it is the one a naive diff over the NEW weights
    would miss entirely."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 0.5, "BBB": 0.5}), "d1",
                       px(AAA=100.0, BBB=50.0), 0.0, stamp="s1")
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "d2", px(AAA=100.0, BBB=50.0), 0.0,
                       stamp="s2")
    closed = [r for r in b["trades"] if r["ts"] == "s2" and r["ticker"] == "BBB"]
    assert closed and closed[0]["side"] == "SELL"
    assert closed[0]["position_after"] == 0.0


def test_a_rounding_sized_change_is_not_logged_as_a_fill(isolated):
    """Vol-targeted weights drift by tiny fractions every cycle; logging those would bury
    the real trades in noise."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "d1", px(AAA=100.0), 0.0, stamp="s1")
    n = len(b["trades"])
    b["positions"]["AAA"] += books.MIN_FILL_SHARES / 10       # sub-threshold drift
    books.log_trades(b, dict(b["positions"]), px(AAA=100.0), "s2")
    assert len(b["trades"]) == n


def test_a_mark_does_not_write_trades(isolated):
    """Marking is valuation, not trading. A mark that logged fills would make the log
    useless — it would fire ~24x a day per book with nothing having happened."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "d1", px(AAA=100.0), 0.0, stamp="s1")
    n = len(b["trades"])
    books.mark(b, "s2", px(AAA=101.0))
    assert len(b["trades"]) == n


def test_the_log_is_capped(isolated):
    """These ledgers are committed to git every cycle, so an unbounded list grows the repo
    forever — the same reason backfill_marks() caps."""
    b = fresh()
    b["trades"] = [{"ts": f"s{i}", "ticker": "AAA", "side": "BUY", "shares": 1.0,
                    "price": 1.0, "notional": 1.0, "position_after": 1.0}
                   for i in range(books.MAX_TRADES)]
    books.log_trades(b, {"AAA": 999.0}, px(AAA=100.0), "newest")
    assert len(b["trades"]) == books.MAX_TRADES
    assert b["trades"][-1]["ts"] == "newest"              # newest kept, oldest dropped


def test_an_unpriceable_name_is_not_logged_as_a_fill(isolated):
    """Turnover already skips it, so logging it would claim a trade the book never made."""
    b = fresh()
    b["positions"] = {"AAA": 10.0}
    books.log_trades(b, {"AAA": 20.0}, px(AAA=float("nan")), "s1")
    assert not b.get("trades")


# ------------------------------------------------------------------ record_prices
def test_a_mark_records_the_prices_it_used(isolated):
    """The dashboard used to price positions from data/prices.csv, which is gitignored
    (local-only, arbitrarily stale) and holds only the daily ETF universe — so a crypto
    book's positions all priced to NaN and the panel rendered $-0 for a fully-deployed
    $100k book. The ledger now carries its own prices."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "d1", px(AAA=100.0), 0.0, stamp="s1")
    books.mark(b, "s2", px(AAA=123.5, ZZZ=9.0))
    assert b["last_prices"] == {"AAA": 123.5}            # only HELD names, not the universe
    assert b["last_prices_at"] == "s2"


def test_recorded_prices_never_include_a_non_finite_value(isolated):
    """A NaN written into the ledger is permanent (CLAUDE.md). Omitting the key lets the
    UI say 'could not price' instead of inheriting a poisoned number."""
    b = fresh()
    b["positions"] = {"AAA": 1.0, "BBB": 1.0}
    books.record_prices(b, px(AAA=100.0, BBB=float("nan")), "s1")
    assert b["last_prices"] == {"AAA": 100.0}


def test_a_ledger_with_recorded_prices_still_serializes(isolated):
    """books.save() uses allow_nan=False — a non-finite price would make the file invalid
    JSON that jq and JSON.parse both reject outright."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "d1", px(AAA=100.0), 0.0, stamp="s1")
    books.save(b)
    assert books.load("t")["last_prices"] == {"AAA": 100.0}
    assert books.load("t")["trades"][0]["side"] == "BUY"


# ------------------------------------------------------------------ stamp vs bar date
def test_the_history_key_and_last_rebalance_are_allowed_to_differ(isolated):
    """`date` answers "which price bar did we trade on"; `stamp` answers "when did the
    cycle run". Conflating them is what put a bare date into a minute-stamped history and
    drew the daily cycle's result at midnight."""
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "2026-07-27",
                       px(AAA=100.0), 0.0, stamp="2026-07-27T22:03")
    assert b["last_rebalance"] == "2026-07-27"           # the BAR
    assert b["history"][-1][0] == "2026-07-27T22:03"     # the CLOCK


def test_stamp_defaults_to_date_for_existing_callers(isolated):
    b = fresh()
    books.rebalance_to(b, pd.Series({"AAA": 1.0}), "2026-07-27", px(AAA=100.0), 0.0)
    assert b["history"][-1][0] == "2026-07-27"
