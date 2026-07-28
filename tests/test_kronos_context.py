"""Deviation 3: the fed context is 90 daily bars, and that must not silently regress.

Feeding 512 daily bars is not a crash — it is a plausible-looking forecast that is 88%
normalization drift (research/kronos_context_diagnostic.py). A defect whose only symptom is
a confident wrong number needs a test, because nothing else will catch it.

No torch required: these exercise the pure context helpers.
"""
import numpy as np
import pandas as pd
import pytest

from tradefabe import kronos


def ohlcv(index, closes):
    c = pd.Series(np.asarray(closes, dtype=float), index=index)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999,
                         "close": c, "volume": 1e6}, index=index)


# ------------------------------------------------------------------ the frozen value
def test_the_fed_context_is_ninety_not_the_architectural_ceiling():
    """The whole point of deviation 3. DAILY_CONTEXT is what we FEED; MAX_CONTEXT is only
    what the model can accept. Collapsing the two reintroduces the defect."""
    assert kronos.DAILY_CONTEXT == 90
    assert kronos.MAX_CONTEXT == 512
    assert kronos.DAILY_CONTEXT < kronos.MAX_CONTEXT


# ------------------------------------------------------------------ context_zscore
def test_context_zscore_is_large_for_a_trending_series():
    """The condition that breaks long daily contexts: the last bar far from its window mean.
    A trend puts it there by construction, which is why trending daily series were the ones
    producing -11% SPY forecasts."""
    idx = pd.bdate_range("2025-07-01", periods=200)
    z = kronos.context_zscore(ohlcv(idx, np.linspace(100, 200, 200)))
    assert z > 1.5


def test_context_zscore_is_near_zero_for_a_mean_reverting_series():
    idx = pd.bdate_range("2025-07-01", periods=200)
    osc = 100 + np.sin(np.linspace(0, 20 * np.pi, 200))
    assert abs(kronos.context_zscore(ohlcv(idx, osc))) < 1.5


def test_context_zscore_is_nan_not_an_exception_on_a_flat_series():
    """A flat window has zero SD. Returning NaN keeps the guard non-fatal; raising here
    would break a legitimately quiet asset."""
    idx = pd.bdate_range("2025-07-01", periods=50)
    assert np.isnan(kronos.context_zscore(ohlcv(idx, [100.0] * 50)))


# ------------------------------------------------------------------ is_daily
def test_daily_and_slower_bars_are_daily():
    assert kronos.is_daily(pd.bdate_range("2025-07-01", periods=50))
    assert kronos.is_daily(pd.date_range("2025-07-01", periods=50, freq="W"))


def test_intraday_bars_are_not_daily():
    """Intraday is deliberately exempt from the 90-bar cap: over 512 intraday bars price
    barely moves against its window mean, so the artifact is negligible. Measured: BTC 1h
    forecast +0.09% against a realized +0.17%."""
    assert not kronos.is_daily(pd.date_range("2025-07-01", periods=50, freq="h"))
    assert not kronos.is_daily(pd.date_range("2025-07-01", periods=50, freq="5min"))


# ------------------------------------------------------------------ trim_context
def test_trim_context_cuts_daily_history_to_the_frozen_ninety():
    idx = pd.bdate_range("2024-01-01", periods=400)
    out = kronos.trim_context(ohlcv(idx, np.linspace(100, 200, 400)))
    assert len(out) == kronos.DAILY_CONTEXT
    assert out.index[-1] == idx[-1]          # keeps the MOST RECENT bars, not the oldest


def test_trim_context_lets_intraday_use_the_full_ceiling():
    idx = pd.date_range("2025-07-01", periods=900, freq="h")
    out = kronos.trim_context(ohlcv(idx, np.linspace(100, 110, 900)))
    assert len(out) == kronos.MAX_CONTEXT


def test_trim_context_never_exceeds_the_architectural_ceiling():
    """Even an explicit oversized request is clamped — the model cannot accept more than
    512 and would silently truncate somewhere less visible."""
    idx = pd.date_range("2025-07-01", periods=2000, freq="h")
    assert len(kronos.trim_context(ohlcv(idx, np.linspace(100, 110, 2000)), bars=9999)) \
        == kronos.MAX_CONTEXT


def test_trim_context_is_a_noop_on_already_short_history():
    idx = pd.bdate_range("2025-07-01", periods=30)
    assert len(kronos.trim_context(ohlcv(idx, np.linspace(100, 110, 30)))) == 30


# ------------------------------------------------------------------ the warning
def test_an_over_long_daily_context_warns(capsys):
    """The guard fires on exactly the configuration that produced the -11.7% SPY forecast."""
    idx = pd.bdate_range("2024-01-01", periods=512)
    kronos._warn_long_daily_context(ohlcv(idx, np.linspace(100, 200, 512)))
    err = capsys.readouterr().err
    assert "DAILY_CONTEXT" in err and "trim_context" in err


def test_a_trimmed_daily_context_does_not_warn(capsys):
    idx = pd.bdate_range("2024-01-01", periods=512)
    kronos._warn_long_daily_context(
        kronos.trim_context(ohlcv(idx, np.linspace(100, 200, 512))))
    assert capsys.readouterr().err == ""


def test_a_long_intraday_context_does_not_warn(capsys):
    idx = pd.date_range("2025-07-01", periods=512, freq="h")
    kronos._warn_long_daily_context(ohlcv(idx, np.linspace(100, 130, 512)))
    assert capsys.readouterr().err == ""
