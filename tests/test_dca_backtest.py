"""Modified double-down DCA (#25).

The comparison is only fair if both paths contribute identical dollars on identical dates
and the reserve can't spend money it doesn't have. These pin that, plus the tier
thresholds, on synthetic price paths with known shapes."""
import numpy as np
import pandas as pd
import pytest

import dca_backtest as dca


def _path(values, start="2000-01-03"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def _zero_rate(idx):
    return pd.Series(0.0, index=idx)


def test_both_paths_contribute_identical_dollars():
    p = _path(np.linspace(100, 200, 900))
    res = dca.simulate(p, _zero_rate(p.index))
    assert res["contributed"] == pytest.approx(res["months"] * dca.ANNUAL / 12)


def test_a_monotonically_rising_market_never_triggers_a_dip_buy():
    # never off its high -> the reserve is never deployed, so it must all still be there
    p = _path(np.linspace(100, 400, 1200))
    res = dca.simulate(p, _zero_rate(p.index))
    b = res["buckets"]
    assert b["dip20"] == 0 and b["dip30"] == 0
    assert b["near_high"] == res["months"]
    expected = res["months"] * (dca.ANNUAL / 12) * (1 - dca.BASELINE_FRAC)
    assert res["tiered"]["reserve_left"] == pytest.approx(expected, rel=1e-9)


def test_plain_beats_tiered_when_the_market_only_rises():
    # pure cash drag, no dips: the held-back 25% earns nothing and misses the rally
    p = _path(np.linspace(100, 400, 1200))
    res = dca.simulate(p, _zero_rate(p.index))
    assert res["plain"]["terminal"] > res["tiered"]["terminal"]


def test_a_deep_crash_triggers_the_30pct_tier():
    rise = np.linspace(100, 200, 700)
    crash = np.linspace(200, 120, 200)          # -40% off the high
    p = _path(np.concatenate([rise, crash]))
    res = dca.simulate(p, _zero_rate(p.index))
    assert res["buckets"]["dip30"] > 0, "a 40% drawdown must reach the >=30% tier"


def test_reserve_is_never_driven_negative():
    rise = np.linspace(100, 200, 300)
    crash = np.full(600, 100.0)                 # long, deep, sustained -> drains reserve
    p = _path(np.concatenate([rise, crash]))
    res = dca.simulate(p, _zero_rate(p.index))
    assert res["tiered"]["reserve_left"] >= -1e-9
    assert res["tiered"]["months_starved"] > 0, "a sustained crash should exhaust it"


def test_cash_rate_accrues_on_the_idle_reserve():
    p = _path(np.linspace(100, 400, 1200))      # never dips, so reserve just sits
    idx = p.index
    flat = dca.simulate(p, _zero_rate(idx))["tiered"]["reserve_left"]
    paid = dca.simulate(p, pd.Series(5.0, index=idx))["tiered"]["reserve_left"]
    assert paid > flat, "a positive T-bill rate must grow the idle reserve"


# ---------------------------------------------------------------- xirr
def test_xirr_recovers_a_known_rate():
    # -100 now, +110 in exactly one year -> 10%
    dates = [pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")]
    assert dca.xirr([-100.0, 110.0], dates) == pytest.approx(0.10, abs=1e-3)


def test_xirr_is_negative_when_money_is_lost():
    dates = [pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")]
    assert dca.xirr([-100.0, 80.0], dates) < 0
