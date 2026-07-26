"""Dense, evenly-spaced marks independent of the scheduler (#87).

GitHub's cron is best-effort: an `0 * * * *` mark schedule actually delivered 03:00, 06:38,
09:13, 11:20, 13:25, 15:06, 17:03, 19:13, 20:59 -- one every ~2.2h, only one on the hour.
One mark per firing left multi-hour holes in every chart and a freshly-opened book showed a
single dot.

Backfilling one mark per hourly bar since the last one decouples chart resolution from when
the scheduler happened to fire. The three things that make it honest rather than invented
are pinned here: it never writes before the book existed, it never rewrites an existing
key, and every key is on ONE clock."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from tradefabe import books, pricing


def _bars(n=6, start="2026-07-24 10:00", cols=("SPY", "IEF"), tz=None):
    idx = pd.date_range(start, periods=n, freq="h", tz=tz)
    return pd.DataFrame({c: np.linspace(100.0, 110.0, n) for c in cols}, index=idx)


def _book(history=None):
    return {"name": "b", "cash": 1000.0, "positions": {"SPY": 10.0},
            "history": history if history is not None else [], "last_run": None,
            "last_rebalance": None}


# ---------------------------------------------------------------- density
def test_backfill_adds_one_mark_per_bar():
    b = _book([["2026-07-24T09:00", 2000.0]])
    added = books.backfill_marks(b, _bars(6))
    assert added == 6
    assert len(b["history"]) == 7


def test_backfill_is_idempotent():
    b = _book([["2026-07-24T09:00", 2000.0]])
    px = _bars(6)
    books.backfill_marks(b, px)
    n = len(b["history"])
    assert books.backfill_marks(b, px) == 0
    assert len(b["history"]) == n


def test_backfill_only_adds_bars_after_the_last_one():
    b = _book([["2026-07-24T09:00", 2000.0]])
    px = _bars(6)
    books.backfill_marks(b, px.iloc[:3])
    assert books.backfill_marks(b, px) == 3


# ---------------------------------------------------------------- honesty
def test_backfill_never_writes_before_the_book_existed():
    """The price source carries 30 days of bars; a book opened yesterday did not hold
    these positions three weeks ago. Writing that window would invent a history the book
    never had -- the one thing this ledger must not do."""
    b = _book([["2026-07-24T13:00", 2000.0]])          # opened mid-session
    added = books.backfill_marks(b, _bars(6, start="2026-07-24 10:00"))
    # bars are 10:00..15:00; 10/11/12 predate the book, and 13:00 is already recorded,
    # so only 14:00 and 15:00 are genuinely new
    assert added == 2
    assert all(k >= "2026-07-24T13:00" for k, _ in b["history"])
    assert len(b["history"]) == 3


def test_backfill_on_an_empty_book_is_unbounded_but_harmless():
    # no inception to respect yet; the first real mark establishes it
    b = _book([])
    assert books.backfill_marks(b, _bars(4)) == 4


def test_backfill_skips_unpriceable_bars():
    px = _bars(4)
    px.iloc[2, 0] = np.nan                              # SPY missing on one bar
    b = _book([["2026-07-24T09:00", 2000.0]])
    assert books.backfill_marks(b, px) == 3
    assert all(np.isfinite(v) for _, v in b["history"])


def test_backfill_leaves_history_sorted():
    b = _book([["2026-07-24T09:00", 2000.0], ["2026-07-24T20:59", 2100.0]])
    books.backfill_marks(b, _bars(6))
    ks = [k for k, _ in b["history"]]
    assert ks == sorted(ks)


def test_backfill_does_not_touch_the_daily_regression_guard():
    """last_price_bar guards the DAILY-frame mark path. Setting it from hourly bars made
    every daily mark look like a step backwards, and mark() correctly refused all of
    them -- no equity book marked at all."""
    b = _book([["2026-07-24T09:00", 2000.0]])
    b["last_price_bar"] = "2026-07-24"
    books.backfill_marks(b, _bars(6))
    assert b["last_price_bar"] == "2026-07-24"


# ---------------------------------------------------------------- one clock
def test_keys_are_naive_utc_even_from_tz_aware_bars():
    """Bars arrive tz-aware, the Action stamps UTC, a local run stamped PDT. Three
    representations in one series made it non-monotonic in a way sorting cannot fix,
    because the values genuinely disagreed about what time it was."""
    b = _book([["2026-07-24T09:00", 2000.0]])
    books.backfill_marks(b, _bars(4, tz="UTC"))
    assert all("+" not in k and "Z" not in k for k, _ in b["history"])


def test_utc_stamp_normalizes_an_aware_timestamp():
    aware = pd.Timestamp("2026-07-26 22:00", tz="UTC")
    assert books.utc_stamp(aware) == "2026-07-26T22:00"


def test_utc_stamp_now_is_utc_not_local():
    now = books.utc_stamp()
    delta = abs(dt.datetime.fromisoformat(now)
                - dt.datetime.now(dt.UTC).replace(tzinfo=None))
    assert delta < dt.timedelta(minutes=2), "utc_stamp() must not return local time"


# ---------------------------------------------------------------- modular sourcing
def test_a_future_book_needs_no_registry_entry():
    assert pricing.source_for("some_book_invented_next_year") == pricing.DEFAULT_SOURCE


def test_the_crypto_book_is_routed_to_crypto_bars():
    assert pricing.source_for("crypto_reversal_1h") == "crypto_hourly"
    assert "BTC-USD" in pricing.SOURCES["crypto_hourly"]


def test_funding_books_are_excluded_from_price_marking():
    # they accrue funding rather than being priced; marking them here would double-count
    assert "carry_btc_eth" in pricing.NON_PRICED
    assert "funding_timing_1h" in pricing.NON_PRICED


def test_fetch_for_books_asks_each_source_once(monkeypatch):
    calls = []
    monkeypatch.setattr(pricing, "fetch", lambda s: calls.append(s) or pd.DataFrame())
    pricing.fetch_for_books(["tsmom_12m", "green_line_200d", "crypto_reversal_1h",
                             "carry_btc_eth"])
    assert sorted(calls) == ["crypto_hourly", "equity_hourly"], f"got {calls}"


def test_a_dead_source_does_not_kill_the_cycle(monkeypatch):
    def boom(s):
        raise RuntimeError("yfinance down")
    monkeypatch.setattr(pricing, "fetch", boom)
    assert pricing.fetch_for_books(["tsmom_12m"]) == {}
