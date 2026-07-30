"""DOCTRINE v1.4: Deflated Sharpe Ratio (PSR + extreme-value multiple-testing correction)
and Combinatorial Purged CV — the active gate-1 decision, replacing Bonferroni for the
verdict itself (bonferroni_bar() stays, logged only, see harness.evaluate()).
Requires pyproject.toml's [tool.pytest.ini_options] pythonpath=["."] so `import harness`
resolves under pytest, same as test_bonferroni.py."""
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

import harness


# ---------------------------------------------------------------- probabilistic_sharpe_ratio
def test_psr_is_half_when_observed_equals_benchmark():
    # z = 0 regardless of skew/kurtosis/n_obs -> Phi(0) = 0.5 exactly
    psr = harness.probabilistic_sharpe_ratio(0.05, 0.05, n_obs=500, skew=0.3, kurtosis=5.0)
    assert psr == pytest.approx(0.5)


def test_psr_increases_monotonically_with_observed_sharpe():
    vals = [harness.probabilistic_sharpe_ratio(sr, 0.0, n_obs=250) for sr in (-0.1, 0.0, 0.1, 0.3)]
    assert vals == sorted(vals)
    assert vals[0] < vals[-1]


def test_psr_matches_hand_computed_normal_case():
    # skew=0, kurtosis=3 (Normal) -> denom = 1 + 0.5*sr_observed^2, matching the textbook
    # Mertens/Lo asymptotic-variance formula for a Normal return series.
    sr_obs, sr_bench, n_obs = 0.10, 0.02, 400
    denom = 1 + 0.5 * sr_obs ** 2
    z = (sr_obs - sr_bench) * np.sqrt(n_obs - 1) / np.sqrt(denom)
    expected = NormalDist().cdf(z)
    got = harness.probabilistic_sharpe_ratio(sr_obs, sr_bench, n_obs, skew=0.0, kurtosis=3.0)
    assert got == pytest.approx(expected)


def test_psr_below_two_observations_is_uninformative():
    assert harness.probabilistic_sharpe_ratio(0.5, 0.0, n_obs=1) == pytest.approx(0.5)
    assert harness.probabilistic_sharpe_ratio(0.5, 0.0, n_obs=0) == pytest.approx(0.5)


# ---------------------------------------------------------------- expected_max_sharpe
def test_expected_max_sharpe_below_two_trials_returns_mean_unadjusted():
    assert harness.expected_max_sharpe(0.3, 0.1, n_trials=1) == pytest.approx(0.3)
    assert harness.expected_max_sharpe(0.3, 0.1, n_trials=0) == pytest.approx(0.3)


def test_expected_max_sharpe_rises_monotonically_with_n_trials():
    # more trials drawn from the same null -> the expected BEST of them keeps climbing
    vals = [harness.expected_max_sharpe(0.0, 0.3, n) for n in (2, 5, 20, 100, 1000)]
    assert vals == sorted(vals)
    assert vals[0] < vals[-1]


def test_expected_max_sharpe_with_zero_dispersion_is_just_the_mean():
    # no spread in the trial pool -> there's no "luckier draw" to have, at any N
    for n in (2, 50, 5000):
        assert harness.expected_max_sharpe(0.42, 0.0, n) == pytest.approx(0.42)


# ---------------------------------------------------------------- deflated_sharpe_ratio
def test_deflated_sharpe_ratio_gets_stricter_as_n_tested_grows():
    # same candidate, same null -> more competing trials raises the bar it must clear,
    # so DSR (probability of clearing it) falls -- the DSR analogue of
    # test_bonferroni_bar_rises_monotonically_with_n_tested.
    rng = np.random.default_rng(0)
    null = rng.normal(0.0, 0.05, 500)      # native-frequency (not annualized) null
    dsrs = [harness.deflated_sharpe_ratio(0.08, null, n, n_obs=1000)[0]
            for n in (1, 5, 20, 100, 1000)]
    assert dsrs == sorted(dsrs, reverse=True)
    assert dsrs[0] > dsrs[-1]


def test_deflated_sharpe_ratio_returns_probability_in_unit_interval():
    rng = np.random.default_rng(1)
    null = rng.normal(0.0, 0.05, 500)
    dsr, sr_star = harness.deflated_sharpe_ratio(0.05, null, n_tested=12, n_obs=500)
    assert 0.0 <= dsr <= 1.0
    assert np.isfinite(sr_star)


# ---------------------------------------------------------------- cpcv_splits
def test_cpcv_splits_produces_exact_combination_count():
    from math import comb
    n_groups, n_test = 6, 2
    paths = harness.cpcv_splits(600, n_groups=n_groups, n_test_groups=n_test, embargo=0)
    assert len(paths) == comb(n_groups, n_test)


def test_cpcv_splits_indices_are_in_range_and_sorted():
    n_obs = 300
    for idx in harness.cpcv_splits(n_obs, n_groups=6, n_test_groups=2, embargo=3):
        assert idx.min() >= 0
        assert idx.max() < n_obs
        assert np.array_equal(idx, np.sort(idx))


def test_cpcv_splits_embargo_shrinks_blocks_that_follow_a_train_block():
    n_obs, n_groups = 600, 6
    block_size = n_obs // n_groups
    no_embargo = harness.cpcv_splits(n_obs, n_groups, n_test_groups=1, embargo=0)
    with_embargo = harness.cpcv_splits(n_obs, n_groups, n_test_groups=1, embargo=10)
    # test_groups of size 1: every path (except block 0, nothing precedes it to embargo
    # against) should have exactly `embargo` fewer observations than the no-embargo case.
    shrunk = [len(a) - len(b) for a, b in zip(no_embargo, with_embargo)]
    assert shrunk[0] == 0                      # first block has no preceding train block
    assert all(s == 10 for s in shrunk[1:])


# ---------------------------------------------------------------- cpcv_oos_sharpes
def test_cpcv_oos_sharpes_recovers_a_known_constant_sharpe():
    # constant per-period Sharpe by construction (mean/std fixed every day) -> every
    # resampled path should land close to the same native-frequency Sharpe.
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.001, 0.01, 900))
    sharpes = harness.cpcv_oos_sharpes(r, n_groups=6, n_test_groups=2, embargo=5)
    assert len(sharpes) > 0
    assert sharpes.mean() == pytest.approx(0.1, abs=0.05)   # 0.001/0.01 = 0.1 native Sharpe


def test_cpcv_oos_sharpes_empty_for_too_short_a_series():
    r = pd.Series(np.random.default_rng(0).normal(0, 0.01, 5))
    assert len(harness.cpcv_oos_sharpes(r, n_groups=6)) == 0


# ---------------------------------------------------------------- evaluate() end-to-end
def _synthetic_strategy_and_bench(seed, drift, n=1200):
    """Independent (uncorrelated) strategy/benchmark return series with OOS_START in the
    middle of the sample, so evaluate() has real pre/post-OOS data to slice."""
    idx = pd.bdate_range("2015-01-02", periods=n)
    rng = np.random.default_rng(seed)
    strat = pd.Series(rng.normal(drift, 0.01, n), index=idx)
    bench = pd.Series(rng.normal(0.0002, 0.008, n), index=idx)
    return strat, bench


def test_evaluate_logs_v14_columns_and_a_strong_uncorrelated_edge_clears_gate_1(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    rng = np.random.default_rng(0)
    null = rng.normal(0.0, 0.06, 500)   # native-frequency null, deliberately tight/low

    strat, bench = _synthetic_strategy_and_bench(seed=1, drift=0.0015)  # strong, real drift
    harness.evaluate("test_strong_edge", strat, bench, null, "D", n_tested=1)

    row = pd.read_csv(gy).iloc[0]
    for col in ("dsr", "dsr_sr_star", "cpcv_n_paths", "cpcv_sharpe_mean", "cpcv_sharpe_std"):
        assert col in row.index
    assert row["cpcv_n_paths"] > 0
    assert row["dsr"] > 0.95          # obviously-real edge clears the v1.4 gate 1 bar
    assert row["verdict"] == "ALIVE"  # and gates 2/3 aren't binding for an uncorrelated,
                                      # low-drawdown synthetic series


def test_evaluate_kills_pure_noise_against_a_wide_null(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    rng = np.random.default_rng(0)
    null = rng.normal(0.05, 0.15, 500)   # wide, generous null

    strat, bench = _synthetic_strategy_and_bench(seed=2, drift=0.0)  # zero true edge
    harness.evaluate("test_pure_noise", strat, bench, null, "D", n_tested=50)

    row = pd.read_csv(gy).iloc[0]
    assert row["dsr"] < 0.95
    assert row["verdict"] == "DEAD"


def test_evaluate_prints_the_caller_supplied_bench_label(monkeypatch, tmp_path, capsys):
    """#122: the benchmark print used to say "(60/40)" unconditionally, even for callers
    passing a non-60/40 series (e.g. always-on carry). bench_label lets each caller say
    what it actually passed instead of a misleading constant."""
    gy = tmp_path / "graveyard.csv"
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    rng = np.random.default_rng(0)
    null = rng.normal(0.0, 0.06, 500)
    strat, bench = _synthetic_strategy_and_bench(seed=3, drift=0.0)

    harness.evaluate("test_default_label", strat, bench, null, "D", n_tested=1)
    assert "(60/40)" in capsys.readouterr().out

    harness.evaluate("test_custom_label", strat, bench, null, "D", n_tested=1,
                      bench_label="always-on carry")
    out = capsys.readouterr().out
    assert "(always-on carry)" in out
    assert "(60/40)" not in out


# ---------------------------------------------------------------- last_verdict (#29)
def test_last_verdict_none_when_never_evaluated(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "does_not_exist.csv"))
    assert harness.last_verdict("anything") is None


def test_last_verdict_reads_back_a_just_written_row(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    rng = np.random.default_rng(0)
    null = rng.normal(0.0, 0.06, 500)
    strat, bench = _synthetic_strategy_and_bench(seed=1, drift=0.0015)
    harness.evaluate("test_strong_edge", strat, bench, null, "D", n_tested=1)
    assert harness.last_verdict("test_strong_edge") == "ALIVE"
    assert harness.last_verdict("never_evaluated") is None


def test_last_verdict_returns_the_most_recent_of_multiple_rows_for_the_same_name(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    gy.write_text("timestamp,strategy,verdict\n"
                  "2026-01-01T00:00:00,foo,DEAD\n"
                  "2026-02-01T00:00:00,foo,ALIVE\n")
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    assert harness.last_verdict("foo") == "ALIVE"


# ---------------------------------------------------------------- rows_for (#28b)
def test_rows_for_empty_when_graveyard_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "does_not_exist.csv"))
    assert harness.rows_for(["a", "b"]).empty


def test_rows_for_filters_to_requested_names_only(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    gy.write_text("timestamp,strategy,verdict,dsr\n"
                  "2026-01-01T00:00:00,a,DEAD,0.10\n"
                  "2026-01-01T00:00:00,b,DEAD,0.20\n"
                  "2026-01-01T00:00:00,c,DEAD,0.30\n")
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    rows = harness.rows_for(["a", "c"])
    assert set(rows["strategy"]) == {"a", "c"}


def test_rows_for_keeps_only_the_most_recent_row_per_name(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    gy.write_text("timestamp,strategy,verdict,dsr\n"
                  "2026-01-01T00:00:00,a,DEAD,0.10\n"
                  "2026-02-01T00:00:00,a,ALIVE,0.99\n")
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    rows = harness.rows_for(["a"])
    assert len(rows) == 1
    assert rows.iloc[0]["verdict"] == "ALIVE"
    assert rows.iloc[0]["dsr"] == pytest.approx(0.99)
