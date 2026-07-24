"""Engine core: sizing caps, net_returns no-lookahead + cost, stats()/calmar() formulas."""
import numpy as np
import pandas as pd
import pytest

from tradefabe import engine


def test_realized_vol_matches_the_documented_formula():
    idx = pd.bdate_range("2024-01-02", periods=70)
    px = pd.DataFrame({"A": 100.0 * np.cumprod(1 + 0.01 * np.sin(np.arange(70)))}, index=idx)
    got = engine.realized_vol(px)
    expected = px.pct_change().rolling(engine.VOL_WINDOW).std() * np.sqrt(engine.ANN)
    pd.testing.assert_frame_equal(got, expected)


def test_sized_weights_clips_to_max_leg_when_vol_is_zero():
    # a perfectly flat price has zero realized vol -> TARGET_VOL/0 = inf -> clipped to MAX_LEG
    idx = pd.bdate_range("2024-01-02", periods=70)
    px = pd.DataFrame({"A": np.full(70, 100.0)}, index=idx)
    signal = pd.DataFrame(1.0, index=idx, columns=["A"])
    w = engine.sized_weights(px, signal)
    # single asset: gross = MAX_LEG (< MAX_GROSS), so the gross-cap never engages here
    assert w["A"].iloc[-1] == pytest.approx(engine.MAX_LEG)


def test_gross_cap_does_not_bind_under_frozen_doctrine_parameters():
    """Documents a real, checkable consequence of the current frozen parameters
    (MAX_LEG=2.0, MAX_GROSS=3.0) combined with the /n_assets step in sized_weights:
    gross = mean(|raw_i|) <= MAX_LEG for any number of assets, and MAX_LEG < MAX_GROSS,
    so the gross-cap scale factor is mathematically always 1.0. If either frozen
    parameter or the sizing formula ever changes, this is the regression guard."""
    idx = pd.bdate_range("2024-01-02", periods=70)
    # two assets: one flat (vol=0, leg-capped at MAX_LEG), one genuinely moving
    flat = np.full(70, 100.0)
    moving = 100.0 * np.cumprod(1 + 0.002 * np.where(np.arange(70) % 2 == 0, 1, -1))
    px = pd.DataFrame({"FLAT": flat, "MOVING": moving}, index=idx)
    signal = pd.DataFrame(1.0, index=idx, columns=["FLAT", "MOVING"])
    w = engine.sized_weights(px, signal)
    gross = w.abs().sum(axis=1).iloc[-1]
    assert gross <= engine.MAX_LEG + 1e-9
    assert gross < engine.MAX_GROSS


def test_size_and_rebalance_only_changes_on_scheduled_days():
    idx = pd.bdate_range("2024-01-29", periods=6)     # 2024-01-29..02-05, crosses into February
    px = pd.DataFrame({"A": np.linspace(100, 106, 6)}, index=idx)
    signal = pd.DataFrame(1.0, index=idx, columns=["A"])
    w = engine.size_and_rebalance(px, signal, freq="M")
    periods = pd.Series(idx.to_period("M"), index=idx)
    reb_days = periods.ne(periods.shift(1))
    # weight is identical across every run of days sharing a month (forward-filled)
    for i in range(1, len(idx)):
        if not reb_days.iloc[i]:
            assert w["A"].iloc[i] == w["A"].iloc[i - 1]


def test_net_returns_no_lookahead_and_cost():
    idx = pd.bdate_range("2024-01-02", periods=3)
    px = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)   # +10% each day
    w = pd.DataFrame({"A": [0.0, 1.0, 1.0]}, index=idx)
    r = engine.net_returns(px, w)

    # NOTE: with a single-column frame, DataFrame.sum(axis=1)'s default skipna=True
    # turns an all-NaN row into 0.0 rather than NaN, so .dropna() has nothing to drop
    # here -- the pre-warmup row shows up as a real 0.0, not a dropped row.
    assert len(r) == 3
    assert r.iloc[0] == pytest.approx(0.0)     # no prior weight yet -> no return, no cost
    assert r.iloc[1] == pytest.approx(0.0)     # yesterday's weight was 0.0 -> no exposure
    # row 2: gross = w_exec(=1.0, i.e. yesterday's weight) * today's 10% return = 0.10
    # cost = |w_exec.diff()| * bps = |1.0 - 0.0| * 5/1e4 = 0.0005
    assert r.iloc[2] == pytest.approx(0.10 - 0.0005)


def test_stats_matches_independent_computation():
    r = pd.Series(0.001 * np.sin(np.arange(40)))
    got = engine.stats(r)

    eq = (1 + r).cumprod()
    exp_cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    exp_vol = r.std() * np.sqrt(252)
    exp_sharpe = r.mean() / r.std() * np.sqrt(252)
    exp_sortino = r.mean() / r[r < 0].std() * np.sqrt(252)
    exp_maxdd = (eq / eq.cummax() - 1).min()

    assert got["CAGR"] == pytest.approx(exp_cagr)
    assert got["Vol"] == pytest.approx(exp_vol)
    assert got["Sharpe"] == pytest.approx(exp_sharpe)
    assert got["Sortino"] == pytest.approx(exp_sortino)
    assert got["MaxDD"] == pytest.approx(exp_maxdd)


def test_stats_returns_nan_below_min_length():
    r = pd.Series(0.001 * np.ones(29))   # < 30 rows
    got = engine.stats(r)
    assert all(np.isnan(v) for v in got.values())


def test_calmar_basic_and_zero_drawdown():
    assert engine.calmar({"CAGR": 0.20, "MaxDD": -0.10}) == pytest.approx(2.0)
    assert np.isnan(engine.calmar({"CAGR": 0.20, "MaxDD": 0.0}))
    assert np.isnan(engine.calmar({"CAGR": 0.20, "MaxDD": np.nan}))
