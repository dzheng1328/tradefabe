"""congress_backtest.ols() — the regression the congress_copy verdict rests on (#59).

Only the math is tested. The script itself hits yfinance, and pinning a live ETF's alpha
to a number would make CI fail every time the market moves; the verdict is "no DETECTABLE
alpha" (|t| < 2), not a specific point estimate. So: known-answer tests on the estimator.

pyproject's pythonpath includes "research", so `import congress_backtest` resolves."""
import numpy as np
import pytest

from congress_backtest import ols


def test_recovers_a_known_intercept_and_slopes():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 0.01, (2000, 2))
    y = 0.0004 + 0.7 * X[:, 0] + 0.3 * X[:, 1]      # exact, no noise
    beta, _ = ols(y, X)
    assert beta[0] == pytest.approx(0.0004, abs=1e-9)
    assert beta[1] == pytest.approx(0.7, abs=1e-9)
    assert beta[2] == pytest.approx(0.3, abs=1e-9)


def test_pure_beta_with_no_alpha_gives_an_insignificant_t_stat():
    # the congress_copy case: returns are entirely factor exposure plus noise, no edge.
    rng = np.random.default_rng(1)
    X = rng.normal(0, 0.01, (3000, 2))
    y = 0.65 * X[:, 0] + 0.35 * X[:, 1] + rng.normal(0, 0.002, 3000)
    beta, t = ols(y, X)
    assert abs(t[0]) < 2, "no-alpha data must not produce a significant intercept"
    assert beta[0] * 252 == pytest.approx(0.0, abs=0.02)


def test_a_real_intercept_is_detected():
    # guards against the estimator being unable to find alpha that IS there -- otherwise
    # the test above would pass for a broken implementation that always returns t=0.
    rng = np.random.default_rng(2)
    X = rng.normal(0, 0.01, (3000, 2))
    y = 0.0005 + 0.65 * X[:, 0] + rng.normal(0, 0.002, 3000)   # ~12.6%/yr alpha
    _, t = ols(y, X)
    assert t[0] > 2, "a large true alpha must be detected"
