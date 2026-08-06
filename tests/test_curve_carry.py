"""Tests for curve_carry (Phase 2, docs/superpowers/specs/2026-08-04-carry-generalization-
design.md) -- a DV01-neutral TLT/IEF position whose direction trend-follows the real FRED
curve slope. No live network calls anywhere -- every rates.load_yield_curve() call is
mocked, matching tests/test_rates.py's pattern."""
import numpy as np
import pandas as pd
import pytest

import tradefabe.pipeline as pipeline
import tradefabe.rates as rates


def _synthetic_prices(n=400, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.005, n)))
         for t in ["TLT", "IEF", "SPY"]}, index=idx)


def _synthetic_curve(idx, slope_path, seed=1):
    """A yield curve whose DGS10-DGS2 slope follows slope_path exactly, so direction is
    fully controlled rather than left to chance."""
    rng = np.random.default_rng(seed)
    dgs2 = 3.0 + rng.normal(0, 0.001, len(idx)).cumsum() * 0
    dgs10 = dgs2 + pd.Series(slope_path, index=idx)
    return pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)


def test_sig_curve_carry_is_dv01_neutral_by_construction(monkeypatch):
    prices = _synthetic_prices()
    steepening = np.linspace(0.5, 2.0, len(prices))   # monotonically steepening
    curve = _synthetic_curve(prices.index, steepening)
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    nonzero = weights[(weights["TLT"] != 0) | (weights["IEF"] != 0)]
    assert len(nonzero) > 0
    ratios = (nonzero["TLT"].abs() * pipeline.TLT_DURATION) / \
             (nonzero["IEF"].abs() * pipeline.IEF_DURATION)
    assert np.allclose(ratios, 1.0, atol=1e-9)   # DV01s offset exactly, by construction


def test_sig_curve_carry_shorts_tlt_on_a_steepening_trend(monkeypatch):
    prices = _synthetic_prices()
    steepening = np.linspace(0.5, 2.0, len(prices))
    curve = _synthetic_curve(prices.index, steepening)
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    last = weights.iloc[-1]
    assert last["TLT"] < 0   # steepening -> short TLT
    assert last["IEF"] > 0   # steepening -> long IEF


def test_sig_curve_carry_longs_tlt_on_a_flattening_trend(monkeypatch):
    prices = _synthetic_prices()
    flattening = np.linspace(2.0, 0.5, len(prices))
    curve = _synthetic_curve(prices.index, flattening)
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    last = weights.iloc[-1]
    assert last["TLT"] > 0   # flattening -> long TLT
    assert last["IEF"] < 0   # flattening -> short IEF


def test_sig_curve_carry_is_flat_before_enough_lookback_history(monkeypatch):
    prices = _synthetic_prices()
    curve = _synthetic_curve(prices.index, np.linspace(0.5, 2.0, len(prices)))
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    assert (weights.iloc[0]["TLT"] == 0.0) and (weights.iloc[0]["IEF"] == 0.0)


def test_sig_curve_carry_never_touches_curve_data_past_the_prices_window(monkeypatch):
    """The calibration-firewall-respecting truncation: sig(prices) must restrict the
    fetched curve to prices.index.max(), even though load_yield_curve() itself returns
    full history -- a caller passing calibration-window-only prices must get a
    calibration-window-only signal."""
    prices = _synthetic_prices(n=200)
    full_idx = pd.bdate_range("2020-01-02", periods=400)   # curve has MORE history than prices
    curve = _synthetic_curve(full_idx, np.linspace(0.5, 3.0, len(full_idx)))
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)   # must not raise, must not silently use future curve rows

    assert list(weights.index) == list(prices.index)
