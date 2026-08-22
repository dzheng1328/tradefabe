"""Family M's live monitor-only books (#105/#126).

Every test here runs WITHOUT torch or the 400MB checkpoint. That is deliberate and is the
whole reason `kronos.py` splits pure signals from inference: the live book's decision path is
`forecast_frame -> sig_* -> weights -> books.rebalance_to`, all of it arithmetic on a stored
forecast frame. Only `forecast_today()` needs the model, and it is the one thing not tested
here (it is exercised by the study, whose output is committed).

The load-bearing tests:
  - the live book and the STUDY consume the same function (no drifting second copy);
  - a missing [kronos] extra advances no ledger and raises nothing;
  - the wick book is NOT vol-targeted, because its frozen spec says so;
  - every family M book that can go live has a persisted backtest curve, or dashboard.py dies
    with a bare KeyError (the failure family L already caused once).
"""
import os

import numpy as np
import pandas as pd
import pytest

from tradefabe import books, kronos, kronos_live, pricing, runner


def _ohlcv(tickers, n=200, start=100.0, trend=1.0):
    idx = pd.bdate_range("2025-01-02", periods=n)
    out = {}
    for i, t in enumerate(tickers):
        close = np.linspace(start + i, (start + i) * trend, n)
        out[t] = pd.DataFrame({"open": close * 0.99, "high": close * 1.02,
                               "low": close * 0.97, "close": close,
                               "volume": np.full(n, 1e6)}, index=idx)
    return out


def _snapshot(tickers, dates, fc_ret=0.01, fc_vol=0.30, fc_hammer=0.0):
    rows = []
    for d in dates:
        for t in tickers:
            rows.append({"date": pd.Timestamp(d), "ticker": t, "fc_ret": fc_ret,
                         "fc_vol": fc_vol, "fc_hammer": fc_hammer})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ wiring / universes
def test_only_the_profitable_two_books_go_live():
    """Dave's criterion was "only the ones that are profitable" over the clean window.
    kronos_dir_daily's OOS Sharpe was -1.17, so it is deliberately excluded; the other two
    (+0.69, +3.10) are in. Asserted so the exclusion is a decision on the record rather than
    something that looks like an oversight."""
    assert set(kronos_live.LIVE_BOOKS) == {"kronos_wick_agg", "carry_kronos_vol"}
    assert kronos_live.DIR_BOOK not in kronos_live.LIVE_BOOKS


def test_shared_tickers_are_requested_once():
    """SPY/QQQ are in both equity universes. A forecast is per (date, ticker) and shared, so
    asking for it twice would double the most expensive part of the cycle."""
    names = (kronos_live.DIR_BOOK, kronos_live.WICK_BOOK)
    needed = kronos_live.tickers_needed(names)
    assert len(needed) == len(set(needed))
    assert set(needed) == set(kronos.WICK_UNIVERSE) | set(kronos_live.universe_for(kronos_live.DIR_BOOK))


def test_the_wick_book_has_its_own_hourly_price_source():
    """kronos_wick_agg holds 14 single names, NONE of them in UNIVERSE. Without its own
    source every mark would price its holdings at NaN -- the same class of bug that rendered
    crypto_reversal_1h's capital-deployed panel as $-0 (#109)."""
    assert pricing.source_for("kronos_wick_agg") == "wick_hourly"
    assert set(pricing.SOURCES["wick_hourly"]) == set(kronos.WICK_UNIVERSE)
    for t in kronos.WICK_UNIVERSE:
        assert t in pricing.SOURCES["wick_hourly"]


def test_the_kronos_carry_book_is_not_price_marked():
    """It is a funding-accrual book -- it owns its own marking, like carry_btc_eth. Leaving
    it in the price loop would mark a book with no positions to $100k cash forever."""
    assert "carry_kronos_vol" in pricing.NON_PRICED


# ------------------------------------------------------------------ the signal path
def test_wick_weights_are_equal_weight_gross_one_and_NOT_vol_targeted():
    """The frozen spec is long-only, equal-weight, gross 1.0 whenever a name fires. Running
    it through sized_weights would be a DIFFERENT strategy than the one judged -- and would
    quietly shrink gross, since these are single names with high vol."""
    tickers = ["AAPL", "MSFT", "NVDA"]
    ohlcv = _ohlcv(tickers, trend=0.5)          # falling -> satisfies the pullback test
    px = pd.DataFrame({t: d["close"] for t, d in ohlcv.items()})
    dates = px.index[-10:]
    snap = _snapshot(tickers, dates, fc_hammer=1.0)    # every path sees a hammer

    w = kronos_live.wick_weights(kronos_live.forecast_frame(snap, tickers), px)
    assert w.sum() == pytest.approx(1.0)               # gross 1.0, not vol-scaled
    assert (w >= 0).all()                              # long-only
    assert w.nunique() == 1                            # equal weight


def test_wick_weights_are_flat_when_nothing_fires():
    tickers = ["AAPL", "MSFT"]
    ohlcv = _ohlcv(tickers, trend=0.5)
    px = pd.DataFrame({t: d["close"] for t, d in ohlcv.items()})
    snap = _snapshot(tickers, px.index[-10:], fc_hammer=0.0)
    w = kronos_live.wick_weights(kronos_live.forecast_frame(snap, tickers), px)
    assert w.abs().sum() == pytest.approx(0.0)


def test_the_live_book_calls_THE_SAME_signal_function_as_the_study(monkeypatch):
    """Not a style point. If the live book had its own copy of the hammer logic, the
    backtest/live splice chart on the dashboard would be comparing two different strategies
    and every divergence check would be meaningless."""
    called = {}
    real = kronos.sig_kronos_wick

    def spy(fc, prices):
        called["yes"] = True
        return real(fc, prices)

    monkeypatch.setattr(kronos, "sig_kronos_wick", spy)
    tickers = ["AAPL", "MSFT"]
    px = pd.DataFrame({t: d["close"] for t, d in _ohlcv(tickers).items()})
    snap = _snapshot(tickers, px.index[-5:])
    kronos_live.wick_weights(kronos_live.forecast_frame(snap, tickers), px)
    assert called.get("yes"), "the live book does not go through kronos.sig_kronos_wick"


def test_dir_weights_ARE_vol_targeted_unlike_the_wick_book():
    """The other side of the same coin: kronos_dir_daily's frozen spec DOES size through
    engine.sized_weights, like tsmom_12m. The two books differ on purpose."""
    tickers = list(kronos_live.universe_for(kronos_live.DIR_BOOK))[:4]
    px = pd.DataFrame({t: d["close"] for t, d in _ohlcv(tickers, n=200).items()})
    snap = _snapshot(tickers, px.index[-5:], fc_ret=0.02)
    w = kronos_live.dir_weights(kronos_live.forecast_frame(snap, tickers), px)
    assert w.abs().sum() != pytest.approx(1.0), "vol targeting should not leave gross at 1.0"


# ------------------------------------------------------------------ graceful degradation
def test_run_kronos_touches_no_ledger_when_the_extra_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr(kronos, "is_available", lambda: False)
    assert kronos_live.run_kronos(verbose=False) == []
    assert list(tmp_path.iterdir()) == []


def test_run_kronos_never_raises_when_inference_blows_up(monkeypatch, tmp_path):
    """A torch OOM or a HuggingFace outage must not take down the cycle that owns the real
    ledger -- same contract run_hourly() has."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr(kronos, "is_available", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("MPS backend out of memory")
    monkeypatch.setattr(kronos_live, "fetch_ohlcv", _boom)
    assert kronos_live.run_kronos(verbose=False) == []


def test_runner_run_kronos_swallows_even_an_import_error(monkeypatch):
    def _boom(*a, **k):
        raise ImportError("no torch")
    monkeypatch.setattr(kronos_live, "run_kronos", _boom)
    runner.run_kronos(verbose=False)          # must not raise


# ------------------------------------------------------------------ snapshot discipline
def test_forecast_today_skips_dates_already_in_the_snapshot(monkeypatch):
    """Inference is the expensive part of the cycle. Re-forecasting a (date, ticker) already
    stored would also break reproducibility: the stored row is the one the position was
    taken on."""
    tickers = ["AAPL", "MSFT"]
    ohlcv = _ohlcv(tickers)
    last = ohlcv["AAPL"].index[-1]
    snap = _snapshot(tickers, [last])

    def _never(*a, **k):
        raise AssertionError("forecast_paths called for an already-stored (date, ticker)")
    monkeypatch.setattr(kronos, "forecast_paths", _never)
    assert kronos_live.forecast_today(ohlcv, snap) == []


def test_drop_current_day_removes_an_in_progress_24_7_bar():
    """The production defect from the first cloud cycle (#126). BTC-USD trades 24/7, so
    yfinance returns a row for the in-progress UTC day with all five columns populated --
    nothing is NaN, so engine.drop_incomplete_tail() structurally cannot catch it."""
    from tradefabe.engine import drop_incomplete_tail
    idx = pd.to_datetime(["2026-07-27", "2026-07-28", "2026-07-30"])
    hist = pd.DataFrame({"open": [1.0, 2, 3], "high": [1.0, 2, 3], "low": [1.0, 2, 3],
                         "close": [1.0, 2, 3], "volume": [1.0, 2, 3]}, index=idx)

    assert drop_incomplete_tail(hist).index[-1] == pd.Timestamp("2026-07-30"), \
        "precondition: the existing guard keeps this bar, which is why the new one exists"
    trimmed = kronos_live.drop_current_day(hist, today="2026-07-30")
    assert trimmed.index[-1] == pd.Timestamp("2026-07-28")


def test_drop_current_day_is_a_noop_when_the_last_bar_is_older():
    idx = pd.to_datetime(["2026-07-27", "2026-07-28"])
    hist = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
    assert len(kronos_live.drop_current_day(hist, today="2026-07-30")) == 2


def test_drop_current_day_tolerates_an_empty_frame():
    assert kronos_live.drop_current_day(pd.DataFrame()).empty


def test_run_kronos_applies_BOTH_tail_guards(monkeypatch, tmp_path):
    """End-to-end: a fetched frame whose last bar is today must never reach forecast_today().
    Asserted through run_kronos rather than by reading the source, so a future refactor that
    drops one guard fails here."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr(kronos, "is_available", lambda: True)
    monkeypatch.setattr(kronos_live, "FORECAST_SNAPSHOT", str(tmp_path / "fc.csv"))

    today = pd.Timestamp(pd.Timestamp.now('UTC').date())
    n = kronos.DAILY_CONTEXT + 20
    idx = pd.DatetimeIndex(pd.date_range(end=today, periods=n, freq="D"))
    frame = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                          "volume": 1.0}, index=idx)
    monkeypatch.setattr(kronos_live, "fetch_ohlcv", lambda *a, **k: {"BTC-USD": frame})

    seen = {}

    def spy(ohlcv, snapshot):
        seen["last"] = {t: d.index[-1] for t, d in ohlcv.items()}
        return []
    monkeypatch.setattr(kronos_live, "forecast_today", spy)

    kronos_live.run_kronos(verbose=False, names=(kronos_live.CARRY_BOOK,))
    assert seen["last"]["BTC-USD"] < today, "an in-progress bar reached the forecaster"


def test_the_live_seed_matches_the_study_seed():
    """A live forecast for a date must reproduce identically when the study replays it."""
    assert kronos_live._seed_for("2026-07-29") == int(pd.Timestamp("2026-07-29").strftime("%Y%m%d"))
    assert kronos_live._seed_for(pd.Timestamp("2026-07-29 13:45")) == 20260729


def test_append_snapshot_writes_the_header_only_once(tmp_path, monkeypatch):
    monkeypatch.setattr(kronos_live, "FORECAST_SNAPSHOT", str(tmp_path / "fc.csv"))
    row = {"date": pd.Timestamp("2026-07-29"), "ticker": "SPY", "fc_ret": 0.01,
           "fc_vol": 0.2, "fc_hammer": 0.0}
    kronos_live.append_snapshot([row])
    kronos_live.append_snapshot([{**row, "ticker": "QQQ"}])
    df = pd.read_csv(tmp_path / "fc.csv")
    assert list(df.columns) == kronos_live.SNAPSHOT_COLS
    assert len(df) == 2


def test_append_snapshot_is_a_noop_on_an_empty_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(kronos_live, "FORECAST_SNAPSHOT", str(tmp_path / "fc.csv"))
    kronos_live.append_snapshot([])
    assert not (tmp_path / "fc.csv").exists()


def test_the_live_snapshot_is_the_SAME_file_the_study_uses():
    """One record, growing forward. Two files would mean the live positions and the research
    record could disagree about what the model said."""
    from research import kronos_backtest          # noqa: PLC0415
    assert os.path.abspath(kronos_live.FORECAST_SNAPSHOT) == \
           os.path.abspath(kronos_backtest.FORECASTS)


# ------------------------------------------------------------------ dashboard contract
def test_every_live_family_M_book_has_a_persisted_backtest_curve():
    """THE regression guard for this PR. dashboard.py's book_panel_data() falls through to a bare
    `full[name]` and raises KeyError, taking the whole dashboard down -- exactly what adding
    family L to the Research Lab lookup but not this one did on 2026-07-26. A new source that
    can become a live book needs its own persisted-curve story."""
    path = os.path.join(kronos.ARTIFACT_DIR, "kronos_returns.csv")
    assert os.path.exists(path), "run: kronos_backtest.py --judge --curves-only"
    curves = pd.read_csv(path, index_col=0, parse_dates=True)
    for name in kronos_live.LIVE_BOOKS:
        assert name in curves.columns, f"{name} would KeyError the dashboard"
        assert curves[name].notna().any()


def test_the_persisted_curve_starts_at_the_pretraining_cutoff_not_2018():
    """A curve reaching back before the cutoff would put CONTAMINATED bars on a chart
    labelled "backtest" -- the one place they could quietly become evidence."""
    curves = pd.read_csv(os.path.join(kronos.ARTIFACT_DIR, "kronos_returns.csv"),
                         index_col=0, parse_dates=True)
    assert curves.index.min() >= kronos.KRONOS_OOS_START


def test_book_panel_data_resolves_a_family_M_book_from_its_own_artifact():
    import tradefabe.dashboard as dashboard
    curves = dashboard.load_kronos_backtest()
    assert curves is not None
    for name in kronos_live.LIVE_BOOKS:
        assert name in curves.columns


@pytest.mark.parametrize("name", list(kronos_live.LIVE_BOOKS))
def test_book_panel_data_renders_end_to_end_for_each_live_family_M_book(name):
    """The actual failure mode, reproduced rather than approximated: book_panel_data() is what
    raises the bare KeyError that takes the whole dashboard down. Checking that the curve file
    has a column is necessary but not sufficient -- the lookup chain has to reach it."""
    import tradefabe.dashboard as dashboard
    curves = dashboard.load_kronos_backtest()
    idx = pd.to_datetime(["2026-07-29T22:00", "2026-07-29T23:00"])
    phist = pd.DataFrame({"date": idx, "book": name, "equity": [100_000.0, 100_010.0]})
    gy = pd.read_csv(os.path.join(kronos.ARTIFACT_DIR, os.pardir, "graveyard.csv"))
    gy_last = gy.drop_duplicates("strategy", keep="last").set_index("strategy")

    data = dashboard.book_panel_data(
        name, phist, full=pd.DataFrame(index=curves.index), meta={"oos_start": "2018-01-01"},
        gy_last=gy_last, price_now=None, price_date=None, piggy=None, factory_bt=None,
        hourly_bt=None, kronos_bt=curves)

    assert len(data["bt_curve"]), "no backtest curve resolved"
    assert data["bt_start"] >= kronos.KRONOS_OOS_START, \
        "family M's chart must start at the pretraining cutoff, not 2018"
    assert data["verdict"] == "DEAD"


def test_dead_strategy_detail_resolves_family_M_too():
    """The Research Lab has its own lookup chain. Family L was added to one and not the
    other; that asymmetry is what broke the dashboard, so both are asserted."""
    import tradefabe.dashboard as dashboard
    curves = dashboard.load_kronos_backtest()
    empty = pd.DataFrame(index=curves.index)
    r = dashboard._dead_strategy_returns("kronos_wick_agg", empty, None, None, None, curves)
    assert r is not None and len(r)


def test_family_M_books_resolve_a_family_and_a_description():
    import tradefabe.dashboard as dashboard
    for name in ("kronos_dir_daily", "kronos_wick_agg", "carry_kronos_vol"):
        assert dashboard.book_family(name) == "M"
        assert not dashboard.strategy_description(name).startswith("(no description yet")


# ------------------------------------------------------------------ cycle placement
def test_run_daily_forecasts_but_run_mark_does_not(monkeypatch):
    """Family M rebalances at freq D. Forecasting on every mark would pay the full torch +
    400MB inference cost ~12x a day for a decision that cannot change until tomorrow."""
    import inspect
    daily = inspect.getsource(runner.run_daily)
    mark = inspect.getsource(runner.run_mark)
    assert "run_kronos" in daily
    assert "run_kronos" not in mark


def test_retired_family_M_books_are_skipped(monkeypatch, tmp_path):
    """DOCTRINE v1.6 applies to these books like every other (#113)."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    tickers = ["AAPL", "MSFT"]
    ohlcv = _ohlcv(tickers)
    px = pd.DataFrame({t: d["close"] for t, d in ohlcv.items()})
    snap = _snapshot(tickers, px.index[-5:], fc_hammer=1.0)

    books.save({"name": "kronos_wick_agg", "cash": books.START_CASH, "positions": {},
                "history": [], "last_run": None, "last_rebalance": None})
    books.retire("kronos_wick_agg", "frozen for the test")
    before = (tmp_path / "kronos_wick_agg.json").read_text()

    assert kronos_live.run_price_book("kronos_wick_agg", ohlcv, snap, verbose=False) is False
    assert (tmp_path / "kronos_wick_agg.json").read_text() == before
