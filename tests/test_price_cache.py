"""The price cache must expire (2026-07-26).

`load_prices()` returned `data/prices.csv` unconditionally whenever the file existed, with
no expiry of any kind. A local checkout therefore scored every strategy against whatever
prices it happened to fetch first -- found five days stale in practice. `data/` is
gitignored so the cloud engine (fresh container, no cache) was never affected, which is
exactly why it went unnoticed locally.

Also pinned: a STALE cache must beat synthetic data when the network is down. Synthetic
prices are labelled "do not trust the numbers"; stale prices are at least real."""
import os
import sys
import time
import types

import numpy as np
import pandas as pd
import pytest

from tradefabe import engine


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "prices.csv"
    idx = pd.bdate_range("2020-01-01", periods=600)
    rng = np.random.default_rng(0)
    df = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))))
                       for t in ("SPY", "IEF", "QQQ", "GLD")}, index=idx)
    df.to_csv(path)
    monkeypatch.setattr(engine, "DATA_CACHE", str(path))
    return path


def _age(path, hours):
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


def _no_network(monkeypatch):
    fake = types.ModuleType("yfinance")
    def boom(*a, **k):
        raise RuntimeError("network down")
    fake.download = boom
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_a_fresh_cache_is_used(cache, monkeypatch):
    monkeypatch.setattr(engine, "CACHE_MAX_AGE_HOURS", 12.0)
    _age(cache, 1)
    _, src = engine.load_prices()
    assert src == "cache"


def test_a_stale_cache_is_not_silently_reused(cache, monkeypatch):
    # the actual bug: 5 days old and returned as if current
    monkeypatch.setattr(engine, "CACHE_MAX_AGE_HOURS", 12.0)
    _age(cache, 24 * 5)
    _no_network(monkeypatch)
    _, src = engine.load_prices()
    assert src != "cache", "a 5-day-old cache must not be reported as current"


def test_a_stale_cache_still_beats_synthetic_when_offline(cache, monkeypatch):
    monkeypatch.setattr(engine, "CACHE_MAX_AGE_HOURS", 12.0)
    _age(cache, 24 * 5)
    _no_network(monkeypatch)
    px, src = engine.load_prices()
    assert src == "cache (stale)"
    assert "SYNTHETIC" not in src, "real-but-old data beats invented data"
    assert len(px) == 600


def test_synthetic_only_when_there_is_no_cache_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "DATA_CACHE", str(tmp_path / "absent.csv"))
    _no_network(monkeypatch)
    _, src = engine.load_prices()
    assert "SYNTHETIC" in src


def test_the_ttl_is_configurable(cache, monkeypatch):
    _age(cache, 24)
    monkeypatch.setattr(engine, "CACHE_MAX_AGE_HOURS", 48.0)
    _, src = engine.load_prices()
    assert src == "cache"


def test_cache_freshness_boundary(cache, monkeypatch):
    monkeypatch.setattr(engine, "CACHE_MAX_AGE_HOURS", 12.0)
    _age(cache, 11)
    assert engine._cache_is_fresh(str(cache)) is True
    _age(cache, 13)
    assert engine._cache_is_fresh(str(cache)) is False
