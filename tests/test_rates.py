"""Tests for rates.py -- the yield-curve data infrastructure for generalizing structural
carry beyond crypto (docs/superpowers/specs/2026-08-04-carry-generalization-design.md).
No live network calls anywhere in this file -- every FRED fetch is mocked, matching
tests/test_nan_marks.py's injected-fixture pattern."""
import os
import time

import pandas as pd
import pytest

import tradefabe.rates as rates


@pytest.fixture
def scratch_cache(monkeypatch, tmp_path):
    """Redirect RATES_CACHE to a scratch path so no test touches the real cache file."""
    path = str(tmp_path / "yield_curve.csv")
    monkeypatch.setattr(rates, "RATES_CACHE", path)
    return path


def test_load_yield_curve_returns_fresh_cache_without_network_call(scratch_cache, monkeypatch):
    df = pd.DataFrame({"DGS2": [4.1, 4.2], "DGS10": [4.5, 4.6]},
                       index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    df.to_csv(scratch_cache)

    def _fail_if_called(*a, **k):
        raise AssertionError("requests.get must not be called when the cache is fresh")
    monkeypatch.setattr(rates, "requests", type("R", (), {"get": staticmethod(_fail_if_called)}))

    result, source = rates.load_yield_curve()
    assert source == "cache"
    assert list(result.columns) == ["DGS2", "DGS10"]
    assert len(result) == 2


class _FakeResponse:
    def __init__(self, text):
        self.text = text
    def raise_for_status(self):
        pass


def test_load_yield_curve_fetches_from_fred_on_cache_miss(scratch_cache, monkeypatch):
    csv_text = (
        "observation_date,DGS2,DGS10,DGS30\n"
        "2024-01-02,4.33,3.95,4.10\n"
        "2024-01-03,4.35,3.99,4.15\n"
    )
    calls = []

    def _fake_get(url, params=None, timeout=None):
        calls.append((url, params, timeout))
        return _FakeResponse(csv_text)

    monkeypatch.setattr(rates.requests, "get", _fake_get)

    result, source = rates.load_yield_curve(start="2024-01-01")

    assert source == "FRED"
    assert calls[0][0] == rates.FRED_URL
    assert calls[0][1] == {"id": "DGS2,DGS10,DGS30"}
    assert list(result.columns) == ["DGS2", "DGS10", "DGS30"]
    assert result.loc[pd.Timestamp("2024-01-02"), "DGS10"] == 3.95
    assert os.path.exists(scratch_cache)   # cache was written


def test_load_yield_curve_drops_rows_before_start(scratch_cache, monkeypatch):
    csv_text = (
        "observation_date,DGS10\n"
        "2023-12-29,3.88\n"
        "2024-01-02,3.95\n"
    )
    monkeypatch.setattr(rates.requests, "get",
                         lambda url, params=None, timeout=None: _FakeResponse(csv_text))
    result, _ = rates.load_yield_curve(series=("DGS10",), start="2024-01-01")
    assert pd.Timestamp("2023-12-29") not in result.index
    assert pd.Timestamp("2024-01-02") in result.index


def test_empty_fred_field_parses_as_nan(scratch_cache, monkeypatch):
    csv_text = (
        "observation_date,DGS10\n"
        "2024-01-02,3.95\n"
        "2024-01-03,\n"          # empty field, e.g. a no-quote trading day
    )
    monkeypatch.setattr(rates.requests, "get",
                         lambda url, params=None, timeout=None: _FakeResponse(csv_text))
    result, _ = rates.load_yield_curve(series=("DGS10",), start="2024-01-01")
    assert pd.isna(result.loc[pd.Timestamp("2024-01-03"), "DGS10"])


def test_load_yield_curve_falls_back_to_stale_cache_on_fetch_failure(scratch_cache, monkeypatch):
    stale = pd.DataFrame({"DGS10": [3.90]}, index=pd.to_datetime(["2024-01-02"]))
    stale.to_csv(scratch_cache)
    old = time.time() - 3600 * 999
    os.utime(scratch_cache, (old, old))

    def _raise(*a, **k):
        raise RuntimeError("simulated network failure")
    monkeypatch.setattr(rates.requests, "get", _raise)

    result, source = rates.load_yield_curve()
    assert source == "cache (stale)"
    assert result.loc[pd.Timestamp("2024-01-02"), "DGS10"] == 3.90


def test_load_yield_curve_falls_back_to_synthetic_with_no_cache(scratch_cache, monkeypatch):
    assert not os.path.exists(scratch_cache)

    def _raise(*a, **k):
        raise RuntimeError("simulated network failure")
    monkeypatch.setattr(rates.requests, "get", _raise)

    result, source = rates.load_yield_curve(start="2020-01-01")
    assert "SYNTHETIC" in source
    assert not result.empty
    assert list(result.columns) == list(rates.RATES_SERIES)


def test_synthetic_curve_is_deterministic():
    a = rates._synthetic_curve(rates.RATES_SERIES, "2020-01-01")
    b = rates._synthetic_curve(rates.RATES_SERIES, "2020-01-01")
    pd.testing.assert_frame_equal(a, b)
