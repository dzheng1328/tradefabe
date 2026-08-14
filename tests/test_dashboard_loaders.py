import os

from tradefabe import dashboard


def test_load_pairs_backtest_returns_none_when_artifact_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "ART", str(tmp_path))
    assert dashboard.load_pairs_backtest() is None


def test_load_pairs_backtest_reads_the_real_artifact_when_present():
    path = os.path.join(dashboard.ART, "pairs_returns.csv")
    if not os.path.exists(path):
        return  # study hasn't been run in this environment -- nothing to assert
    result = dashboard.load_pairs_backtest()
    assert result is not None
    assert not result.empty
