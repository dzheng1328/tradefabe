"""Overnight effect (#23).

The whole finding rests on the return decomposition being correct and the cost being
charged for both sides every day. Both are pinned here on hand-built bars where the right
answer is known by construction."""
import numpy as np
import pandas as pd
import pytest

import overnight_backtest as ov


def _frames(opens, closes):
    idx = pd.bdate_range("2024-01-02", periods=len(opens))
    op = pd.DataFrame({"X": opens}, index=idx)
    cl = pd.DataFrame({"X": closes}, index=idx)
    return op, cl


def test_decomposition_splits_the_day_at_the_right_seams():
    # close 100 -> open 110 (overnight +10%) -> close 121 (intraday +10%)
    op, cl = _frames([100.0, 110.0], [100.0, 121.0])
    overnight, intraday, total = ov.decompose(op, cl)
    assert overnight["X"].iloc[-1] == pytest.approx(0.10)
    assert intraday["X"].iloc[-1] == pytest.approx(0.10)
    assert total["X"].iloc[-1] == pytest.approx(0.21)


def test_overnight_and_intraday_compound_to_the_full_day():
    rng = np.random.default_rng(0)
    n = 200
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    opens = closes * (1 + rng.normal(0, 0.003, n))
    op, cl = _frames(opens, closes)
    overnight, intraday, total = ov.decompose(op, cl)
    joined = pd.concat([overnight["X"], intraday["X"], total["X"]], axis=1,
                       sort=False).dropna()
    compounded = (1 + joined.iloc[:, 0]) * (1 + joined.iloc[:, 1]) - 1
    pd.testing.assert_series_equal(compounded, joined.iloc[:, 2], check_names=False)


def test_all_of_the_return_overnight_leaves_intraday_at_zero():
    # gaps up every night, flat every session -> intraday must be exactly 0
    closes = [100.0 * 1.01 ** i for i in range(50)]
    op, cl = _frames(closes, closes)          # open == close every day
    overnight, intraday, _ = ov.decompose(op, cl)
    assert intraday["X"].abs().max() == pytest.approx(0.0)
    assert overnight["X"].mean() > 0


def test_harvest_charges_both_sides_every_day():
    overnight = pd.DataFrame({"X": [0.0] * 10},
                             index=pd.bdate_range("2024-01-02", periods=10))
    r = ov.harvest_returns(overnight, cost_bps=5.0)
    # zero gross return, so every day should be exactly the round-trip cost
    assert r.tolist() == pytest.approx([-2 * 5.0 / 1e4] * 10)


def test_zero_cost_harvest_equals_gross():
    rng = np.random.default_rng(1)
    overnight = pd.DataFrame({"X": rng.normal(0.0005, 0.005, 100)},
                             index=pd.bdate_range("2024-01-02", periods=100))
    r = ov.harvest_returns(overnight, cost_bps=0.0)
    pd.testing.assert_series_equal(r, overnight.mean(axis=1))


def test_cost_scales_linearly_with_the_assumed_spread():
    overnight = pd.DataFrame({"X": [0.0] * 5},
                             index=pd.bdate_range("2024-01-02", periods=5))
    at1 = ov.harvest_returns(overnight, cost_bps=1.0).iloc[0]
    at10 = ov.harvest_returns(overnight, cost_bps=10.0).iloc[0]
    assert at10 == pytest.approx(10 * at1)
