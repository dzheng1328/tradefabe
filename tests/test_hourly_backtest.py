"""Family L mechanics (#86).

The verdicts rest on three things being right: the 1-bar lag (without it every signal
peeks at the bar it trades), the turnover charge (which is the term that actually kills
all three), and the daily aggregation (which is what makes hourly returns comparable to
every other row in the roster under ANN=252). All three are pinned here on hand-built
bars where the correct answer is known by construction."""
import numpy as np
import pandas as pd
import pytest

import hourly_backtest as hb


def _px(vals, cols=("A",), start="2024-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="h")
    return pd.DataFrame({c: vals for c in cols}, index=idx)


# ---------------------------------------------------------------- aggregation
def test_daily_aggregation_compounds_within_the_day():
    idx = pd.date_range("2024-01-01", periods=48, freq="h")
    r = pd.Series(0.01, index=idx)
    d = hb.to_daily(r)
    assert len(d) == 2
    assert d.iloc[0] == pytest.approx(1.01 ** 24 - 1)


def test_daily_aggregation_splits_on_calendar_day():
    idx = pd.date_range("2024-01-01 22:00", periods=4, freq="h")   # 22,23,00,01
    d = hb.to_daily(pd.Series([0.1, 0.1, 0.2, 0.2], index=idx))
    assert len(d) == 2
    assert d.iloc[0] == pytest.approx(1.1 * 1.1 - 1)
    assert d.iloc[1] == pytest.approx(1.2 * 1.2 - 1)


def test_aggregation_of_zero_returns_is_zero():
    idx = pd.date_range("2024-01-01", periods=24, freq="h")
    assert hb.to_daily(pd.Series(0.0, index=idx)).iloc[0] == pytest.approx(0.0)


# ---------------------------------------------------------------- the lag
def test_weights_are_applied_with_a_one_bar_lag():
    # price jumps on bar 2; a weight set ON bar 2 must NOT capture that jump
    px = _px([100.0, 100.0, 110.0, 110.0])
    w = pd.DataFrame({"A": [0.0, 0.0, 1.0, 1.0]}, index=px.index)
    r = hb.net_hourly(px, w, cost_bps=0.0)
    assert r.iloc[2] == pytest.approx(0.0), "signal peeked at the bar it traded"


def test_a_lagged_weight_captures_the_next_bar():
    px = _px([100.0, 100.0, 100.0, 110.0])
    w = pd.DataFrame({"A": [0.0, 0.0, 1.0, 1.0]}, index=px.index)
    r = hb.net_hourly(px, w, cost_bps=0.0)
    assert r.iloc[3] == pytest.approx(0.10)


# ---------------------------------------------------------------- cost
def test_turnover_is_charged_on_every_flip():
    px = _px([100.0] * 6)                       # flat prices: return IS the cost
    w = pd.DataFrame({"A": [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]}, index=px.index)
    r = hb.net_hourly(px, w, cost_bps=5.0)
    # a flip from +1 to -1 is 2.0 of turnover at 5bps = 10bps
    assert r.iloc[3] == pytest.approx(-2.0 * 5.0 / 1e4)


def test_holding_still_costs_nothing():
    px = _px([100.0] * 5)
    w = pd.DataFrame({"A": [1.0] * 5}, index=px.index)
    r = hb.net_hourly(px, w, cost_bps=5.0)
    assert r.iloc[2:].abs().max() == pytest.approx(0.0)


def test_cost_scales_linearly():
    px = _px([100.0] * 4)
    w = pd.DataFrame({"A": [0.0, 1.0, 0.0, 1.0]}, index=px.index)
    a = hb.net_hourly(px, w, cost_bps=1.0).iloc[3]
    b = hb.net_hourly(px, w, cost_bps=10.0).iloc[3]
    assert b == pytest.approx(10 * a)


# ---------------------------------------------------------------- signals
def test_reversal_fades_the_trailing_move():
    n = hb.REVERSAL_LOOKBACK_H
    rising = _px([100.0 * 1.01 ** i for i in range(n + 3)])
    sig = hb.sig_crypto_reversal(rising)
    assert sig.iloc[-1, 0] == -1.0, "a rising market must be faded"


def test_tsmom_follows_the_trailing_move():
    n = hb.TSMOM_LOOKBACK_BARS
    rising = _px([100.0 * 1.01 ** i for i in range(n + 3)])
    assert hb.sig_equity_tsmom(rising).iloc[-1, 0] == 1.0


def test_reversal_and_tsmom_take_opposite_sides_of_the_same_move():
    n = max(hb.REVERSAL_LOOKBACK_H, hb.TSMOM_LOOKBACK_BARS)
    px = _px([100.0 * 1.01 ** i for i in range(n + 3)])
    assert hb.sig_crypto_reversal(px).iloc[-1, 0] == -hb.sig_equity_tsmom(px).iloc[-1, 0]


def test_equal_weight_sums_to_one_gross():
    sig = pd.DataFrame({"A": [1.0], "B": [-1.0], "C": [0.0]})
    assert hb.equal_weight(sig).abs().sum(axis=1).iloc[0] == pytest.approx(1.0)


def test_equal_weight_of_an_all_flat_signal_is_flat():
    sig = pd.DataFrame({"A": [0.0], "B": [0.0]})
    assert hb.equal_weight(sig).abs().sum(axis=1).iloc[0] == pytest.approx(0.0)


# ---------------------------------------------------------------- funding timing
def _funding(vals):
    idx = pd.date_range("2024-01-01", periods=len(vals), freq="h")
    return pd.DataFrame({"BTC": vals, "ETH": vals}, index=idx)


def test_funding_timing_is_flat_while_funding_is_negative():
    f = _funding([-0.0001] * (hb.FUNDING_LOOKBACK_H + 10))
    r = hb.funding_timing_returns(f, cost_bps=0.0)
    assert r.iloc[hb.FUNDING_LOOKBACK_H + 2:].abs().max() == pytest.approx(0.0)


def test_funding_timing_collects_while_funding_is_positive():
    rate = 0.0001
    f = _funding([rate] * (hb.FUNDING_LOOKBACK_H + 10))
    r = hb.funding_timing_returns(f, cost_bps=0.0)
    assert r.iloc[-1] == pytest.approx(rate)


def test_funding_timing_never_beats_always_on_when_funding_is_always_positive():
    # the whole point of the DEAD verdict: gating a uniformly-positive carry can only
    # subtract, never add
    f = _funding([0.0001] * 200)
    timed = hb.funding_timing_returns(f, cost_bps=5.0).sum()
    always = f.mean(axis=1).sum()
    assert timed <= always
