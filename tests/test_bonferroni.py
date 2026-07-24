"""DOCTRINE v1.3: the Bonferroni-corrected noise-floor bar and its family-size counter.
Requires pyproject.toml's [tool.pytest.ini_options] pythonpath=["."] so `import harness`
(a repo-root script, not part of the installed tradefabe package) resolves under pytest."""
from statistics import NormalDist

import numpy as np
import pytest

import harness


def test_bonferroni_bar_at_n1_matches_plain_p95_within_empirical_resolution():
    # n_tested=1 -> alpha/n = 0.05 -> the 95th percentile, same as the pre-v1.3 default,
    # and well within what 500 trials can resolve (finest ~= p99.8) -> empirical method.
    rng = np.random.default_rng(0)
    null = rng.normal(0.2, 0.3, 500)
    bar, method, pctile = harness.bonferroni_bar(null, n_tested=1)
    assert method == "empirical"
    assert pctile == pytest.approx(95.0)
    assert bar == pytest.approx(np.percentile(null, 95.0))


def test_bonferroni_bar_falls_back_to_normal_approx_past_empirical_resolution():
    # n_tested=1000 -> required percentile ~99.995, far past what 500 trials can resolve
    # (finest = 100*(1 - 1/500) = 99.8) -> must fall back to the fitted-normal method.
    rng = np.random.default_rng(0)
    null = rng.normal(0.2, 0.3, 500)
    bar, method, pctile = harness.bonferroni_bar(null, n_tested=1000)
    assert method == "normal-approx"
    mu, sigma = null.mean(), null.std(ddof=1)
    z = NormalDist().inv_cdf(1 - 0.05 / 1000)
    assert bar == pytest.approx(mu + z * sigma)


def test_bonferroni_bar_rises_monotonically_with_n_tested():
    # more strategies tested -> a stricter (higher) bar, always -- the whole point of the
    # correction. Checked across the empirical/normal-approx boundary, not just one side.
    rng = np.random.default_rng(0)
    null = rng.normal(0.2, 0.3, 500)
    bars = [harness.bonferroni_bar(null, n_tested=n)[0] for n in (1, 5, 20, 100, 1000)]
    assert bars == sorted(bars)
    assert bars[0] < bars[-1]


def test_bonferroni_bar_clamps_nonpositive_n_tested_to_one():
    rng = np.random.default_rng(0)
    null = rng.normal(0.2, 0.3, 500)
    bar0, m0, p0 = harness.bonferroni_bar(null, n_tested=0)
    bar1, m1, p1 = harness.bonferroni_bar(null, n_tested=1)
    assert (bar0, m0, p0) == (bar1, m1, p1)


def test_family_n_tested_unions_graveyard_with_new_candidates(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    gy.write_text("timestamp,strategy,freq,verdict\n"
                  "2026-01-01T00:00:00,foo,M,DEAD\n"
                  "2026-01-01T00:00:00,bar,M,ALIVE\n")
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))

    # a genuinely new name adds 1 to the family...
    assert harness.family_n_tested(["baz"]) == 3
    # ...but re-evaluating an already-logged name doesn't double-count it.
    assert harness.family_n_tested(["foo"]) == 2
    # a batch of several candidates, some overlapping the ledger, some not.
    assert harness.family_n_tested(["foo", "bar", "baz", "qux"]) == 4


def test_family_n_tested_with_no_graveyard_yet(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "does_not_exist.csv"))
    assert harness.family_n_tested(["first_ever"]) == 1
    assert harness.family_n_tested(["a", "b", "c"]) == 3
