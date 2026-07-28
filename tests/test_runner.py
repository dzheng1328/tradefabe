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

    runner._run_book(name, freq, factory.target_weights, px, "2024-06-01", px.iloc[-1],
                     verbose=False, stamp="2024-06-01T22:00")

    book = books.load(name)
    assert book["last_rebalance"] == "2024-06-01"     # fresh book -> always rebalances on first run
    assert book["positions"]                          # donchian_20d on a strong uptrend takes a real position
    # The BAR date and the CLOCK key are deliberately different since #109: run_daily()
    # used to pass one string for both, so its history key was a bare date, which parses
    # to midnight and sorted the cycle's result to the START of the day it belonged at the
    # end of. `last_rebalance` still answers "which bar", history answers "when".
    assert book["history"] == [["2024-06-01T22:00",
                                pytest.approx(books.equity(book, px.iloc[-1]), rel=1e-6)]]


# ---------------------------------------------------------------- GENERATED_BOOKS (#28b)
def test_generated_books_reflects_promoted_generated_json_at_import_time(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_GENERATED_PATH", tmp_path / "promoted_generated.json")
    spec = factory.generate_candidate(np.random.default_rng(0), "A")
    factory.promote_generated(spec)

    reloaded_runner = importlib.reload(runner)
    try:
        names = [g["name"] for g in reloaded_runner.GENERATED_BOOKS]
        assert names == [spec["name"]]
        assert spec["name"] in reloaded_runner.ALL_BOOKS
    finally:
        importlib.reload(runner)


def test_run_book_rebalances_a_generated_candidate_via_rebuilt_signal(monkeypatch, tmp_path):
    """A promoted generated book has no name-keyed static registry (unlike TEMPLATES) --
    runner.py must reconstruct its signal fn from persisted family+params and still
    rebalance identically."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    px = _trending_prices()
    spec = factory.generate_candidate(np.random.default_rng(0), "I")   # breakout family

    sig_fn = factory.rebuild_signal(spec["family"], spec["params"])
    get_weights = runner._make_generated_get_weights(sig_fn)
    runner._run_book(spec["name"], spec["freq"], get_weights, px, "2024-06-01", px.iloc[-1], verbose=False)

    book = books.load(spec["name"])
    assert book["last_rebalance"] == "2024-06-01"
    assert book["positions"]
