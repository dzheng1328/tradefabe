"""runner.py's factory-book integration (#29): FACTORY_BOOKS is read from
factory.load_promoted() at import time (same pattern EQUITY_BOOKS/PIGGYBACK_BOOKS
already use for their own registries), and _run_book() must work identically for a
factory-sourced book as it does for a hand-picked one -- no special-casing."""
import importlib

import numpy as np
import pandas as pd
import pytest

from tradefabe import books, factory, runner


def test_factory_books_reflects_promoted_json_at_import_time(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    factory.promote("donchian_20d")
    factory.promote("tsmom_3m")

    reloaded_runner = importlib.reload(runner)
    try:
        assert set(reloaded_runner.FACTORY_BOOKS) == {"donchian_20d", "tsmom_3m"}
        assert set(reloaded_runner.FACTORY_BOOKS) <= set(reloaded_runner.ALL_BOOKS)
    finally:
        importlib.reload(runner)   # restore the real promoted.json for later tests/imports


def test_factory_books_empty_when_nothing_promoted(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    reloaded_runner = importlib.reload(runner)
    try:
        assert reloaded_runner.FACTORY_BOOKS == []
    finally:
        importlib.reload(runner)


def _trending_prices(n=300):
    idx = pd.bdate_range("2024-01-02", periods=n)
    up = np.linspace(100.0, 300.0, n)
    return pd.DataFrame({"A": up, "B": np.full(n, 50.0)}, index=idx)


def test_run_book_rebalances_a_factory_template_identically_to_a_hand_picked_one(monkeypatch, tmp_path):
    """No network needed: _run_book() just needs a price frame + a get_weights callable
    -- factory.target_weights has the exact same (prices, name) -> pd.Series contract as
    signals.target_weights/piggyback.target_weights, so this is a direct substitution
    test, not a new code path."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    px = _trending_prices()
    name = "donchian_20d"
    freq = factory.TEMPLATES[name][1]

    runner._run_book(name, freq, factory.target_weights, px, "2024-06-01", px.iloc[-1], verbose=False)

    book = books.load(name)
    assert book["last_rebalance"] == "2024-06-01"     # fresh book -> always rebalances on first run
    assert book["positions"]                          # donchian_20d on a strong uptrend takes a real position
    assert book["history"] == [["2024-06-01", pytest.approx(books.equity(book, px.iloc[-1]), rel=1e-6)]]
