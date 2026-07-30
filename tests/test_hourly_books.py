"""Family L as LIVE monitor-only books (#86).

All three are backtest-DEAD, so under DOCTRINE v1.2 they are monitor-only forever and can
never become `paper-confirmed` -- the same status every factory promotion carries. These
pin the parts that could silently drift:

  - the live book and the backtest must run the SAME signal function, not copies
  - the crypto book's holdings must never be valued against the daily price frame, which
    has no BTC-USD column and would silently report cash only
  - the funding gate must be off when funding is negative, and charge the flip
"""
import json

import numpy as np
import pandas as pd
import pytest

from tradefabe import books, hourly


# ------------------------------------------------------- shared code, not copies
def test_the_study_and_the_live_book_share_one_signal_function():
    """If these ever become separate definitions, a live book can drift from the spec it
    was judged on without a single test failing."""
    hb = pytest.importorskip("hourly_backtest")
    assert hb.sig_crypto_reversal is hourly.sig_crypto_reversal
    assert hb.sig_equity_tsmom is hourly.sig_equity_tsmom
    assert hb.equal_weight is hourly.equal_weight


def test_frozen_parameters_match_the_pre_registration():
    # STRATEGIES.md family L: 24h funding mean, 6h reversal, 24-bar trend
    assert hourly.FUNDING_LOOKBACK_H == 24
    assert hourly.REVERSAL_LOOKBACK_H == 6
    assert hourly.TSMOM_LOOKBACK_BARS == 24


# ------------------------------------------------------- signals
def _rising(n, cols=("A",)):
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({c: [100.0 * 1.01 ** i for i in range(n)] for c in cols}, index=idx)


def test_reversal_shorts_a_rising_market():
    px = _rising(hourly.REVERSAL_LOOKBACK_H + 3)
    assert hourly.target_weights(px, "crypto_reversal_1h").iloc[0] < 0


def test_tsmom_goes_long_a_rising_market():
    px = _rising(hourly.TSMOM_LOOKBACK_BARS + 3, cols=("A", "B"))
    assert (hourly.target_weights(px, "equity_tsmom_1h") > 0).all()


def test_weights_are_equal_weight_gross_one():
    px = _rising(hourly.TSMOM_LOOKBACK_BARS + 3, cols=("A", "B", "C"))
    w = hourly.target_weights(px, "equity_tsmom_1h")
    assert w.abs().sum() == pytest.approx(1.0)


# ------------------------------------------------------- funding gate
def _funding(vals):
    idx = pd.date_range("2024-01-01", periods=len(vals), freq="h")
    return pd.DataFrame({"BTC": vals, "ETH": vals}, index=idx)


def test_gate_is_on_when_funding_is_positive():
    f = _funding([0.0001] * (hourly.FUNDING_LOOKBACK_H + 5))
    assert hourly.funding_is_on(f).iloc[-1] == pytest.approx(1.0)


def test_gate_is_off_when_funding_is_negative():
    f = _funding([-0.0001] * (hourly.FUNDING_LOOKBACK_H + 5))
    assert hourly.funding_is_on(f).iloc[-1] == pytest.approx(0.0)


# ------------------------------------------------------- valuation
def test_the_crypto_book_caches_its_own_equity():
    """write_summary() values books against the DAILY frame, which has no BTC-USD column.
    Without a cached equity the book would be priced at cash-only -- a silent, large,
    wrong number on the dashboard rather than an error."""
    from tradefabe.paths import STATE_DIR
    p = STATE_DIR / "crypto_reversal_1h.json"
    if not p.exists():
        pytest.skip("book not opened in this checkout")
    b = json.loads(p.read_text())
    assert "equity" in b, "crypto book must cache equity; the daily frame cannot price it"
    daily_frame_prices = pd.Series({"SPY": 500.0, "IEF": 95.0})   # no BTC-USD/ETH-USD
    assert books.equity(b, daily_frame_prices) != b["equity"], \
        "this is exactly why the cached value is needed"


def test_all_three_names_are_registered_for_the_summary():
    assert set(hourly.ALL_NAMES) == {"crypto_reversal_1h", "equity_tsmom_1h",
                                     "funding_timing_1h"}


def test_runner_includes_only_books_that_exist_on_disk(monkeypatch, tmp_path):
    """A never-run hourly book must not appear as a phantom $100k row.

    Asserted BEHAVIOURALLY. This used to grep write_summary's source for ".exists()", which
    broke the moment #126 factored the check into runner._live_on_disk() -- the property was
    still true, the test was just looking at the wrong place. A test that can pass while the
    behaviour is broken, or fail while it is fine, is not testing the behaviour."""
    import pandas as pd
    from tradefabe import books, runner
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runner, "STATE_DIR", tmp_path)
    # exactly one hourly book on disk; the other two have never run
    live = hourly.ALL_NAMES[0]
    books.save({"name": live, "cash": 0.0, "positions": {}, "equity": 42.0,
                "history": [["2026-07-29T00:00", 42.0]], "last_run": None,
                "last_rebalance": None})

    summary = runner.write_summary(pd.Series(dtype=float))
    reported = set(summary["book"])
    assert live in reported
    for absent in hourly.ALL_NAMES[1:]:
        assert absent not in reported, f"{absent} has no ledger but was reported"


def test_run_hourly_never_raises(monkeypatch):
    """A data outage on one hourly book must not take down a cycle that also owns the
    daily ledger."""
    from tradefabe import runner
    monkeypatch.setattr(hourly, "run_price_books",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")))
    runner.run_hourly(verbose=False)      # must not propagate
