"""Dashboard: rich per-strategy detail view for DEAD/backtest-only strategies (#31).
_dead_strategy_returns() is the pure lookup behind render_strategy_detail() -- split out
so it's testable without a Streamlit runtime. Requires pyproject.toml's
[tool.pytest.ini_options] pythonpath=["."] so `import app` resolves under pytest."""
import numpy as np
import pandas as pd
import pytest

import app
import tradefabe.dashboard as dashboard


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
    monkeypatch.setattr(dashboard, "_load_generated_ledger",
                        lambda: {"tsmom_gen_147d": {"family": "A",
                                                    "rationale": "Trend (generated): sign of the trailing 147-day return."}})
    assert app.strategy_description("tsmom_gen_147d") == "Trend (generated): sign of the trailing 147-day return."


def test_book_family_resolves_a_pipeline_name_via_the_ledger_fallback(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_pipeline_ledger",
                        lambda: {"rp_pair_zscore_GLD_SLV_60_2p0_4p0": {"family": "O",
                                                                       "rationale": "..."}})
    assert app.book_family("rp_pair_zscore_GLD_SLV_60_2p0_4p0") == "O"


def test_strategy_description_resolves_a_pipeline_name_via_the_ledger_fallback(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_pipeline_ledger",
                        lambda: {"rp_pair_zscore_GLD_SLV_60_2p0_4p0": {
                            "family": "O", "rationale": "Gold/silver ratio mean-reversion."}})
    assert app.strategy_description("rp_pair_zscore_GLD_SLV_60_2p0_4p0") == \
        "Gold/silver ratio mean-reversion."


def test_book_family_falls_back_to_other_for_an_unknown_pipeline_name(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_pipeline_ledger", lambda: {})
    assert app.book_family("rp_never_proposed") == "?"


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


def test_family_l_hourly_strategies_resolve_a_backtest_curve():
    """Family L (#86) added a FOURTH curve source. Its returns live in
    artifacts/hourly_returns.csv, not full/piggyback/factory, so without wiring it in
    every hourly strategy fell through to the summary-stats-only fallback and showed no
    chart at all in the detail view. Same class of gap as the live-book one CLAUDE.md
    documents: a new source that can produce a graveyard row needs its own curve story."""
    import os
    hourly = app.load_hourly_backtest.__wrapped__()
    if hourly is None:
        pytest.skip("hourly study not run here")
    empty = pd.DataFrame()
    for name in ("funding_timing_1h", "crypto_reversal_1h", "equity_tsmom_1h"):
        r = app._dead_strategy_returns(name, empty, None, None, hourly)
        assert r is not None, f"{name} has no resolvable backtest curve"
        assert len(r) > 100, f"{name} curve is suspiciously short: {len(r)}"


def test_dead_strategy_returns_still_falls_back_to_none_for_an_unknown_name():
    assert app._dead_strategy_returns("not_a_strategy", pd.DataFrame(), None, None, None) is None
