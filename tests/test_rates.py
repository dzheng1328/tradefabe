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
