"""Duty-cycle-matched noise floor (#101).

`sig_random()` re-draws every bar, so a random strategy flips sign at nearly every
rebalance while a real trend signal mostly holds. Measured against `tsmom_12m`: the null
churns 3.7x more monthly and 19.9x more daily. Cost scales with turnover, so the null pays
a penalty the candidate never does -- which makes gate 1 systematically LENIENT.

`sig_rotated()` is the fix: a circular time-shift preserves turnover and persistence while
destroying alignment with future returns.

Opt-in via `noise_floor(..., like=signal)`. NOT the default -- see
test_the_rotated_null_inherits_directional_bias for the doctrine question that has to be
settled before it could be."""
import numpy as np
import pandas as pd
import pytest

import harness
from tradefabe.engine import size_and_rebalance, realized_vol


@pytest.fixture(scope="module")
def px():
    idx = pd.bdate_range("2016-01-04", periods=1400)
    rng = np.random.default_rng(5)
    return pd.DataFrame(
        {c: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 1400)))
         for c in ("SPY", "IEF", "QQQ", "GLD")}, index=idx)


@pytest.fixture(scope="module")
def slow_signal(px):
    """A persistent signal: sign of the trailing 252-bar return, like a real trend rule."""
    return np.sign(px / px.shift(252) - 1).fillna(0.0)


def _turnover(w):
    return w.shift(1).diff().abs().sum(axis=1).mean()


# ------------------------------------------------------------ the defect it fixes
def test_the_per_bar_random_null_churns_far_more_than_a_real_signal(px, slow_signal):
    rv = realized_vol(px)
    rng = np.random.default_rng(0)
    cand = _turnover(size_and_rebalance(px, slow_signal, "M", rv))
    rand = _turnover(size_and_rebalance(px, harness.sig_random(px, rng), "M", rv))
    assert rand > 2 * cand, f"expected the churn mismatch; got {rand:.4f} vs {cand:.4f}"


def test_rotation_roughly_preserves_turnover(px, slow_signal):
    rv = realized_vol(px)
    rng = np.random.default_rng(0)
    cand = _turnover(size_and_rebalance(px, slow_signal, "M", rv))
    rots = [_turnover(size_and_rebalance(px, harness.sig_rotated(slow_signal, rng), "M", rv))
            for _ in range(8)]
    assert 0.5 * cand < np.mean(rots) < 1.5 * cand, \
        f"rotation should trade like the candidate: {np.mean(rots):.4f} vs {cand:.4f}"


# ------------------------------------------------------------ rotation mechanics
def test_rotation_preserves_the_exact_multiset_of_signal_values(slow_signal):
    rng = np.random.default_rng(1)
    rot = harness.sig_rotated(slow_signal, rng)
    a = np.sort(slow_signal.values.ravel())
    b = np.sort(rot.values.ravel())
    assert np.array_equal(a, b), "a rotation must not change WHICH positions were held"


def test_rotation_actually_shifts(slow_signal):
    rng = np.random.default_rng(2)
    rot = harness.sig_rotated(slow_signal, rng)
    assert not rot.equals(slow_signal)
    assert list(rot.index) == list(slow_signal.index)
    assert list(rot.columns) == list(slow_signal.columns)


# ------------------------------------------------------------ the bar it produces
def test_the_matched_null_is_harder_to_beat(px, slow_signal):
    rv = realized_vol(px)
    old = harness.noise_floor(px, "M", 40, rv)
    new = harness.noise_floor(px, "M", 40, rv, like=slow_signal)
    assert np.percentile(new, 95) > np.percentile(old, 95), \
        "the whole point: the churny null set too low a bar"


def test_like_is_cached_separately_from_the_unmatched_null(px, slow_signal):
    rv = realized_vol(px)
    a = harness.noise_floor(px, "M", 20, rv)
    b = harness.noise_floor(px, "M", 20, rv, like=slow_signal)
    assert not np.array_equal(a, b), "the two nulls must not collide in the cache"


def test_the_default_path_is_unchanged(px):
    """Every row in graveyard.csv was scored against the per-bar random null. Changing
    that silently would make old and new verdicts incomparable."""
    rv = realized_vol(px)
    rng = np.random.default_rng(0)
    expected = []
    for _ in range(5):
        r = harness.net_returns(px, size_and_rebalance(px, harness.sig_random(px, rng), "M", rv))
        v = harness.stats(r[r.index >= harness.OOS_START])["Sharpe"]
        if np.isfinite(v):
            expected.append(v)
    got = harness.noise_floor(px, "M", 5, rv)
    assert np.allclose(got, expected), "default noise_floor behaviour drifted"


# ------------------------------------------------------------ the doctrine question
def test_the_rotated_null_inherits_directional_bias(px, slow_signal):
    """Why this is opt-in rather than the new default.

    A rotation keeps the candidate's net exposure, so a mostly-long signal produces a
    mostly-long null that also earns market drift. That makes it a stricter test of TIMING
    skill -- but it starts asking what gate 2 (beat the 60/40 benchmark) already asks.
    Whether gate 1 should absorb that is a DOCTRINE decision, not an implementation one."""
    rv = realized_vol(px)
    rng = np.random.default_rng(0)
    cand_bias = size_and_rebalance(px, slow_signal, "M", rv).sum(axis=1).mean()
    rot_bias = np.mean([size_and_rebalance(px, harness.sig_rotated(slow_signal, rng), "M", rv)
                        .sum(axis=1).mean() for _ in range(8)])
    rand_bias = size_and_rebalance(px, harness.sig_random(px, rng), "M", rv).sum(axis=1).mean()
    assert abs(rot_bias - cand_bias) < abs(rand_bias - cand_bias), \
        "rotation is expected to track the candidate's exposure; if it stops, re-read the docs"
