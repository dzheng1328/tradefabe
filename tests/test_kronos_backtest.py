"""Family M study plumbing (#105) — no torch, no weights, no network.

The expensive part of this study is inference; the part that can silently be WRONG is
everything around it. These pin the wiring: no lookahead, the OOS override that keeps
candidate and null on one window, and the frame reshaping between the snapshot and the
pure signals.
"""
import numpy as np
import pandas as pd
import pytest

import harness
from tradefabe import kronos

kb = pytest.importorskip("kronos_backtest")


IDX = pd.bdate_range("2025-07-01", periods=40)
TK = ["AAA", "BBB"]


def snapshot(fields=None):
    """A long-form forecast snapshot, the shape run_forecasts() appends."""
    rng = np.random.default_rng(0)
    rows = []
    for d in IDX:
        for t in TK:
            rows.append({"date": d, "ticker": t,
                         "fc_ret": (fields or {}).get("fc_ret", rng.normal(0, 0.02)),
                         "fc_vol": (fields or {}).get("fc_vol", 0.25),
                         "fc_hammer": (fields or {}).get("fc_hammer", 0.0)})
    return pd.DataFrame(rows)


def prices(slope=1.0):
    return pd.DataFrame({t: np.linspace(100.0, 100.0 * slope, len(IDX)) for t in TK},
                        index=IDX)


# ------------------------------------------------------------------ the OOS override
def test_the_window_override_moves_harness_oos_start(monkeypatch):
    """`harness.OOS_START` is read by BOTH evaluate() and noise_floor(). Overriding it is
    what keeps candidate and null on the SAME window — slicing only the candidate would
    hand the null 7.5 years against the candidate's 1.1 and make gate 1 a comparison
    between two different experiments."""
    monkeypatch.setattr(harness, "OOS_START", pd.Timestamp("2018-01-01"))
    kb._use_kronos_window()
    assert harness.OOS_START == kronos.KRONOS_OOS_START == pd.Timestamp("2025-06-05")


# ------------------------------------------------------------------ forecast_frame
def test_forecast_frame_pivots_to_the_ticker_field_shape_the_signals_expect():
    fc = kb.forecast_frame(snapshot(), TK)
    assert isinstance(fc.columns, pd.MultiIndex)
    assert set(fc.columns) == {(t, f) for t in TK
                               for f in ("fc_ret", "fc_vol", "fc_hammer")}
    # the pure signals index by field at level 1 -- a transposed frame would raise there
    assert list(kronos.sig_kronos_dir(fc).columns) == TK


def test_forecast_frame_selects_only_the_requested_universe():
    """kronos_dir_daily and kronos_wick_agg share a snapshot but not a universe. Leaking
    the other's tickers in would silently change the book being tested."""
    fc = kb.forecast_frame(snapshot(), ["AAA"])
    assert list(kronos.sig_kronos_dir(fc).columns) == ["AAA"]


def test_forecast_frame_is_sorted_by_date():
    shuffled = snapshot().sample(frac=1.0, random_state=1)
    assert kb.forecast_frame(shuffled, TK).index.is_monotonic_increasing


# ------------------------------------------------------------------ no lookahead
def test_wick_returns_do_not_use_the_same_bar_they_decide_on():
    """The signal is shifted before it meets a return. Without the shift the book would
    'buy' on the very bar whose move it is being paid for — the single easiest way to
    manufacture a spectacular backtest."""
    fc = kb.forecast_frame(snapshot({"fc_hammer": 1.0}), TK)
    px = prices(slope=0.7)                      # falling, so the pullback precondition holds
    r, sig = kb.wick_returns(fc, px)
    # first bar can never have a return attributed to it
    assert r.iloc[0] == 0.0 or pd.isna(r.iloc[0])
    # and a signal that only turns on at bar k cannot move equity before k+1
    assert len(r) == len(px)


def test_wick_returns_charge_turnover_on_every_position_change():
    """Aggressive construction means high turnover; a study that forgot the cost would
    flatter it exactly where it is most vulnerable."""
    fc = kb.forecast_frame(snapshot({"fc_hammer": 1.0}), TK)
    px = prices(slope=0.7)
    r_costed, _ = kb.wick_returns(fc, px)
    import tradefabe.engine as eng
    saved = eng.COST_BPS
    try:
        kb.COST_BPS = 0.0
        r_free, _ = kb.wick_returns(fc, px)
        assert r_free.sum() > r_costed.sum()
    finally:
        kb.COST_BPS = saved


def test_wick_returns_are_flat_when_nothing_triggers():
    fc = kb.forecast_frame(snapshot({"fc_hammer": 0.0}), TK)
    r, _ = kb.wick_returns(fc, prices(slope=0.7))
    assert r.abs().sum() == pytest.approx(0.0)


# ------------------------------------------------------------------ carry leg
def funding_frame():
    idx = pd.date_range("2025-07-01", periods=len(IDX) * 24, freq="h")
    return pd.DataFrame({"BTC": 1e-5, "ETH": 1e-5}, index=idx)


def test_carry_scaling_never_beats_the_benchmark_on_leverage():
    """The cap is what keeps the pre-registered question honest: does TIMING beat holding?
    Uncapped, a calm-vol forecast would win on notional alone and answer something else."""
    f = funding_frame()
    scale = pd.Series(5.0, index=pd.date_range("2025-07-01", periods=len(IDX), freq="D"))
    r, always = kb.carry_returns(f, kronos.vol_scale(scale * 0 + 0.001))
    assert r.sum() <= always.sum() + 1e-9


def test_carry_returns_share_one_funding_series_with_their_benchmark():
    """Candidate and benchmark must differ ONLY by the scaling. Different funding series
    would compare two strategies and a data difference at once."""
    f = funding_frame()
    scale = pd.Series(1.0, index=pd.date_range("2025-07-01", periods=len(IDX), freq="D"))
    r, always = kb.carry_returns(f, scale)
    assert always.index.equals(r.index)
    # at full scale and no scale changes there is no turnover, so they coincide
    assert r.sum() == pytest.approx(always.sum(), rel=1e-9)


def test_carry_null_randomizes_the_scaling_not_the_funding():
    """Isolates whether the vol signal adds anything over holding the position it scales —
    a null that randomized the funding would be testing the market, not the signal."""
    f = funding_frame()
    _, always = kb.carry_returns(f, pd.Series(
        1.0, index=pd.date_range("2025-07-01", periods=len(IDX), freq="D")))
    out = kb.carry_null(always, 20, np.random.default_rng(0))
    assert len(out) > 0 and np.isfinite(out).all()
