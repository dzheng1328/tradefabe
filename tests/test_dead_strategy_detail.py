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


def test_strategy_description_resolves_known_names_from_the_static_dict():
    assert "trailing 12-month" in app.strategy_description("tsmom_12m")


def test_strategy_description_synthesizes_a_generic_line_for_any_combo_name():
    d = app.strategy_description("factory_combo_tsmom_3m_donchian_55d")
    assert "sleeve" in d and "60/40" in d
    assert not d.startswith("(no description yet")


def test_strategy_description_falls_back_to_the_placeholder_for_anything_else():
    assert app.strategy_description("some_totally_new_strategy").startswith("(no description yet")


def test_strategy_description_resolves_a_generated_name_via_the_ledger_fallback(monkeypatch):
    monkeypatch.setattr(app, "_load_generated_ledger",
                        lambda: {"tsmom_gen_147d": {"family": "A",
                                                    "rationale": "Trend (generated): sign of the trailing 147-day return."}})
    assert app.strategy_description("tsmom_gen_147d") == "Trend (generated): sign of the trailing 147-day return."


def test_every_graveyard_strategy_has_a_family_and_description():
    """Regression guard: every strategy actually in graveyard.csv today must resolve to
    a real family (not the "?" -> Other fallback) and a real description (not the
    "no description yet" placeholder) -- the whole point of #31 was that DEAD strategies
    stop being invisible to the family/description machinery. Uses book_family()/
    strategy_description(), not the raw dicts, since factory-generated combo names
    (#28) are handled by a pattern fallback rather than a static per-name entry."""
    import os
    gy = pd.read_csv(os.path.join(app.BASE, "graveyard.csv"))
    for name in gy["strategy"].unique():
        assert app.book_family(name) != "?", f"{name} has no resolvable family"
        assert not app.strategy_description(name).startswith("(no description yet"), \
            f"{name} has no resolvable description"
