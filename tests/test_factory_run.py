"""Integration test for the strategy factory's daily driver (research/factory_run.py,
#28) -- runs a full cycle (individual templates + one correlation-picked combo) against
a small synthetic price panel, with graveyard.csv monkeypatched to a scratch file in
both harness and piggyback_backtest (both write to it independently). Requires
pyproject.toml's pythonpath=[".", "research"] so `import factory_run` (which itself does
`from piggyback_backtest import ...`, a sibling repo-root-script-style import) resolves."""
import numpy as np
import pandas as pd
import pytest

import harness
import piggyback_backtest
import factory_run


def _synthetic_prices(n=1200, seed=3):
    """Enough history and enough assets for every template's longest lookback (24mo
    tsmom = 504 trading days) plus OOS_START (2018-01-01) to have real post-OOS data."""
    idx = pd.bdate_range("2015-01-02", periods=n)
    rng = np.random.default_rng(seed)
    cols = ["SPY", "QQQ", "IEF", "TLT", "GLD"]
    drift = rng.uniform(0.02, 0.08, len(cols)) / 252
    vol = rng.uniform(0.10, 0.20, len(cols)) / np.sqrt(252)
    rets = rng.normal(drift, vol, size=(n, len(cols)))
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=cols)


@pytest.fixture
def scratch_graveyard(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    monkeypatch.setattr(piggyback_backtest, "GRAVEYARD", str(gy))
    monkeypatch.setattr(factory_run, "load_prices", lambda: (_synthetic_prices(), "SYNTHETIC (test)"))
    return gy


def test_run_cycle_evaluates_n_templates_and_one_combo(scratch_graveyard, capsys):
    evaluated = factory_run.run_cycle(n=4, seed=42, verbose=False)
    assert len(evaluated) == 5   # 4 individual templates + 1 combo

    gy = pd.read_csv(scratch_graveyard)
    assert set(gy["strategy"]) == set(evaluated)
    assert gy["verdict"].isin(["ALIVE", "DEAD"]).all()
    assert gy["dsr"].notna().all()

    combo_rows = gy[gy["strategy"].str.startswith("factory_combo_")]
    assert len(combo_rows) == 1
    # the combo's n_tested must be strictly greater than any individual's -- it's
    # evaluated AFTER the 4 individuals have already been logged to the same graveyard.
    assert combo_rows["n_tested"].iloc[0] > gy[~gy["strategy"].str.startswith("factory_combo_")]["n_tested"].min()


def test_run_cycle_never_redraws_an_already_tested_template(scratch_graveyard):
    first = factory_run.run_cycle(n=len(factory_run.factory.TEMPLATES), seed=1, verbose=False)
    individuals_first = {n for n in first if not n.startswith("factory_combo_")}
    assert individuals_first == set(factory_run.factory.TEMPLATES.keys())   # exhausted the pool

    second = factory_run.run_cycle(n=4, seed=2, verbose=False)
    # every template already logged -> nothing left to draw; only a combo is impossible
    # too since complementary_pairs() needs >=2 FRESH candidates in `sample` this cycle.
    assert second == []


def test_run_cycle_skips_the_combo_when_fewer_than_two_candidates_drawn(scratch_graveyard):
    evaluated = factory_run.run_cycle(n=1, seed=5, verbose=False)
    assert len(evaluated) == 1
    assert not evaluated[0].startswith("factory_combo_")
