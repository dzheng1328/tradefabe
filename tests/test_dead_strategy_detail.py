"""Dashboard: rich per-strategy detail view for DEAD/backtest-only strategies (#31).
_dead_strategy_returns() is the pure lookup behind render_strategy_detail() -- split out
so it's testable without a Streamlit runtime. Requires pyproject.toml's
[tool.pytest.ini_options] pythonpath=["."] so `import app` resolves under pytest."""
import numpy as np
import pandas as pd
import pytest

import app


def test_dead_strategy_returns_from_bare_strategy_columns():
    idx = pd.bdate_range("2018-01-02", periods=10)
    oos = pd.DataFrame({"tsmom_12m": np.linspace(0.001, 0.01, 10),
                        "bench_6040": np.zeros(10)}, index=idx)
    r = app._dead_strategy_returns("tsmom_12m", oos, piggy=None)
    pd.testing.assert_series_equal(r, oos["tsmom_12m"].fillna(0), check_names=False)


def test_dead_strategy_returns_from_piggyback_columns():
    idx = pd.bdate_range("2018-01-02", periods=10)
    oos = pd.DataFrame({"tsmom_12m": np.zeros(10)}, index=idx)
    piggy = pd.DataFrame({"piggyback_2b": np.linspace(-0.001, 0.001, 10)}, index=idx)
    r = app._dead_strategy_returns("piggyback_2b", oos, piggy)
    pd.testing.assert_series_equal(r, piggy["piggyback_2b"].dropna(), check_names=False)


def test_dead_strategy_returns_none_when_not_in_either_source():
    idx = pd.bdate_range("2018-01-02", periods=10)
    oos = pd.DataFrame({"tsmom_12m": np.zeros(10)}, index=idx)
    piggy = pd.DataFrame({"piggyback_2b": np.zeros(10)}, index=idx)
    assert app._dead_strategy_returns("insider_buying_21d", oos, piggy) is None


def test_dead_strategy_returns_none_when_piggy_is_none_and_not_in_oos():
    idx = pd.bdate_range("2018-01-02", periods=10)
    oos = pd.DataFrame({"tsmom_12m": np.zeros(10)}, index=idx)
    assert app._dead_strategy_returns("piggyback_2b", oos, piggy=None) is None


def test_every_graveyard_strategy_has_a_family_and_description():
    """Regression guard: every strategy actually in graveyard.csv today must have a
    BOOK_FAMILY entry and a STRATEGY_DESCRIPTIONS entry -- the whole point of #31 was
    that DEAD strategies stop being invisible to the family/description machinery."""
    import os
    gy = pd.read_csv(os.path.join(app.BASE, "graveyard.csv"))
    for name in gy["strategy"].unique():
        assert name in app.BOOK_FAMILY, f"{name} has no BOOK_FAMILY entry"
        assert name in app.STRATEGY_DESCRIPTIONS, f"{name} has no STRATEGY_DESCRIPTIONS entry"
