import os

import pandas as pd

from tradefabe import dashboard, remote
from tradefabe.dashboard import piggyback_blend


def test_load_pairs_backtest_returns_none_when_artifact_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "ART", str(tmp_path))
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)
    assert dashboard.load_pairs_backtest() is None


def test_load_pairs_backtest_reads_the_real_artifact_when_present():
    path = os.path.join(dashboard.ART, "pairs_returns.csv")
    if not os.path.exists(path):
        return  # study hasn't been run in this environment -- nothing to assert
    result = dashboard.load_pairs_backtest()
    assert result is not None
    assert not result.empty


def test_piggyback_blend_zero_weight_equals_bench_alone():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    oos = pd.DataFrame({
        "bench_6040": [0.01, -0.005, 0.02, 0.0, 0.01],
        "strat_a": [0.03, 0.03, -0.01, 0.02, 0.0],
    }, index=idx)
    result = piggyback_blend(oos, ["strat_a"], 0)
    expected_bench_growth = (1 + oos["bench_6040"]).cumprod()
    pd.testing.assert_series_equal(result["combo"], expected_bench_growth, check_names=False)


def test_piggyback_blend_full_weight_equals_sleeve_mean():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    oos = pd.DataFrame({
        "bench_6040": [0.01, -0.005, 0.02, 0.0, 0.01],
        "strat_a": [0.03, 0.03, -0.01, 0.02, 0.0],
        "strat_b": [-0.01, 0.01, 0.01, 0.04, -0.02],
    }, index=idx)
    result = piggyback_blend(oos, ["strat_a", "strat_b"], 100)
    sleeve_mean = oos[["strat_a", "strat_b"]].mean(axis=1)
    expected_growth = (1 + sleeve_mean).cumprod()
    pd.testing.assert_series_equal(result["combo"], expected_growth, check_names=False)


def test_piggyback_blend_returns_bench_and_combo_stats():
    idx = pd.date_range("2020-01-01", periods=30, freq="D")
    oos = pd.DataFrame({
        "bench_6040": [0.001] * 30,
        "strat_a": [0.002] * 30,
    }, index=idx)
    result = piggyback_blend(oos, ["strat_a"], 30)
    assert "bench_stats" in result and "Sharpe" in result["bench_stats"]
    assert "combo_stats" in result and "Sharpe" in result["combo_stats"]
