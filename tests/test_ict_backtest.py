"""ICT concept definitions (#24).

The verdicts depend entirely on the mechanical rules being what the docstrings claim, so
these are known-answer tests on hand-built bars. Critically they also pin the LOOKAHEAD
guards: a pivot must only be visible after confirmation, and a signal must only be
tradeable on the following bar. Both are easy to break silently and would manufacture a
fake edge."""
import numpy as np
import pandas as pd
import pytest

import ict_backtest as ict


def _bars(rows):
    """rows: list of (open, high, low, close)."""
    idx = pd.date_range("2026-01-02 09:30", periods=len(rows), freq="h")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def _flat(n, price=100.0):
    return [(price, price + 0.1, price - 0.1, price)] * n


# ---------------------------------------------------------------- lookahead guards
def test_signals_are_lagged_one_bar():
    # _hold must shift, or a signal formed on bar t trades at bar t's own return
    raw = pd.Series([0.0, 1.0, 0.0, 0.0, 0.0], index=pd.RangeIndex(5))
    pos = ict._hold(raw, h=2)
    assert pos.iloc[1] == 0.0, "position must not exist on the bar the signal formed"
    assert pos.iloc[2] == 1.0, "position starts the bar AFTER the signal"


def test_hold_expires_after_h_bars():
    raw = pd.Series([0.0, 1.0, 0.0, 0.0, 0.0, 0.0], index=pd.RangeIndex(6))
    pos = ict._hold(raw, h=2)
    assert list(pos) == [0.0, 0.0, 1.0, 1.0, 0.0, 0.0]


def test_swing_pivots_are_not_visible_before_confirmation():
    # a spike at position n must not appear in the pivot series until n bars later
    n = ict.SWING_N
    rows = _flat(2 * n + 5)
    spike = 2 * n + 1
    rows[spike] = (100.0, 130.0, 99.9, 100.0)
    hi, _ = ict._swings(_bars(rows), n=n)
    assert not (hi.iloc[:spike] > 120).any(), "pivot leaked before it was confirmed"


# ---------------------------------------------------------------- concept rules
# NOTE: signals are lagged one bar (see _hold), so the gap-completing bar shows its
# position on the FOLLOWING bar. Each pattern gets a repeated trailing bar, chosen to
# overlap so it cannot itself open a new gap in the opposite direction.
def test_fvg_fires_on_a_bullish_three_bar_gap():
    # bar1.high 101 < bar3.low 106  ->  bullish gap
    rows = _flat(5) + [(100, 101, 99.5, 100.5), (103, 106, 102, 105), (107, 108, 106, 107)]
    rows.append((107, 108, 106, 107))
    sig = ict.sig_fvg(_bars(rows))
    assert sig.iloc[-1] > 0, "bullish FVG should be long on the bar after it completes"


def test_fvg_fires_short_on_a_bearish_gap():
    # bar1.low 106 > bar3.high 101  ->  bearish gap
    rows = _flat(5) + [(107, 108, 106, 107), (103, 106, 102, 104), (100, 101, 99, 100)]
    rows.append((100, 101, 99, 100))
    sig = ict.sig_fvg(_bars(rows))
    assert sig.iloc[-1] < 0, "bearish FVG should be short on the bar after it completes"


def test_fvg_is_flat_when_bars_overlap():
    rows = _flat(10)   # every bar overlaps its neighbours -> no gap anywhere
    assert (ict.sig_fvg(_bars(rows)) == 0).all()


def test_liquidity_sweep_fades_rather_than_follows():
    # pierce a swing HIGH then close back below it -> the concept says SHORT (it's a trap)
    n = ict.SWING_N
    rows = _flat(2 * n + 2)
    rows[n] = (100.0, 115.0, 99.9, 100.0)          # the swing high
    rows += _flat(n + 2)
    rows.append((100.0, 118.0, 99.0, 100.0))        # pierce high, close back inside
    sig = ict.sig_liquidity_sweep(_bars(rows))
    assert sig.iloc[-1] <= 0, "a swept high must fade (short), not follow (long)"


def test_every_concept_returns_a_bounded_position_series():
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 0.5, 400))
    df = pd.DataFrame({"Open": close, "High": close + 0.4, "Low": close - 0.4,
                       "Close": close},
                      index=pd.date_range("2026-01-02 09:30", periods=400, freq="h"))
    for name, fn in ict.CONCEPTS.items():
        s = fn(df)
        assert len(s) == len(df), f"{name} changed length"
        assert s.abs().max() <= 1.0, f"{name} produced |position| > 1"
        assert not s.isna().any(), f"{name} produced NaN"


def test_power_of_3_is_not_implemented_on_purpose():
    # it is defined on Asian/London/NY sessions, which do not exist in US ETF hours.
    # if someone adds it, they must also add the session data -- this guards the claim.
    assert "ict_power_of_3" not in ict.CONCEPTS
