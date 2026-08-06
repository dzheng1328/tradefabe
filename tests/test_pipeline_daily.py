"""research/pipeline_daily.py (#178, extended by #179-181; #177's propose() call
retired 2026-08-04): the pipeline's daily driver.

Deliberately thin. Screening (#175) and pre-registration (#179) of whatever's pending in
PIPELINE_LEDGER, and OOS-testing (#180) of whatever's pending pre-registration, both run
UNCONDITIONALLY every cycle -- no gate on "did anything new happen today," since a
research routine (not this module) is what writes new PIPELINE_LEDGER rows now, and a
backlog from any source must still clear. There's no new mechanism to test here, only
that both steps actually run every cycle.
"""
import json
import os

import numpy as np
import pandas as pd
import pytest

import harness
import pipeline_daily as pd_
import pipeline_register
from tradefabe import rates as pkg_rates


def test_both_steps_run_with_nothing_pending():
    calls = []
    result = pd_.run_daily_cycle(backlog_fn=lambda: calls.append("backlog") or [],
                                 oos_test_fn=lambda: calls.append("oos") or [])
    assert calls == ["backlog", "oos"]
    assert result == {"backlog_screened": [], "oos_tested": []}


def test_the_oos_test_step_runs_even_with_an_empty_backlog():
    """#180's own point: a backlog of pre-registered-but-untested candidates must clear
    on every cycle, independent of whatever the screening backlog step found."""
    calls = []

    def fake_oos_test():
        calls.append(1)
        return [{"name": "rp_old_backlog_candidate", "verdict": "DEAD", "promoted": False}]

    result = pd_.run_daily_cycle(backlog_fn=lambda: [], oos_test_fn=fake_oos_test)
    assert calls == [1]
    assert result["oos_tested"] == [{"name": "rp_old_backlog_candidate", "verdict": "DEAD",
                                     "promoted": False}]


def test_the_screening_backlog_result_is_reported_faithfully():
    """#181's own point: a PIPELINE_LEDGER row added by a research routine (writing the
    ledger directly, not through this module) must still get screened -- reported
    through, not swallowed."""
    result = pd_.run_daily_cycle(
        backlog_fn=lambda: [{"name": "rp_routine_written", "passed": True, "preregistered": True}],
        oos_test_fn=lambda: [])
    assert result["backlog_screened"] == [{"name": "rp_routine_written", "passed": True,
                                           "preregistered": True}]


def test_defaults_wire_to_the_real_functions():
    """No stand-ins snuck into the default wiring -- an unpatched call must reach the
    real #175/#179/#180/#181 functions, not a private copy. propose_idea() (#177) is
    deliberately NOT referenced here anymore -- see the module's own docstring for why."""
    import inspect
    src = inspect.getsource(pd_.run_daily_cycle)
    assert "pipeline_ideas" not in src
    assert "screen_pending_backlog" in src
    assert "pipeline_verdict.run_pending_oos_tests" in src


# ---------------------------------------------------------------- pending_screens / screen_pending_backlog (#181)
@pytest.fixture
def scratch(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "PIPELINE_LEDGER", str(tmp_path / "pipeline_ideas.csv"))
    monkeypatch.setattr(harness, "PRELIM_LOG", str(tmp_path / "prelim_log.csv"))
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "graveyard.csv"))
    monkeypatch.setattr(harness, "GENERATED_LEDGER", str(tmp_path / "gen.csv"))
    monkeypatch.setattr(pipeline_register, "STRATEGIES_PATH", str(tmp_path / "STRATEGIES.md"))
    monkeypatch.setattr(pipeline_register, "PREREGISTERED_LEDGER", str(tmp_path / "preregistered.csv"))
    (tmp_path / "STRATEGIES.md").write_text("# Roster\n\n## Rules of the roster\n1. x\n")
    return tmp_path


def _write_ledger_row(name, primitive="single_asset_trend", params=None, freq="M"):
    params = params if params is not None else {"ticker": "SPY", "lookback": 90}
    row = {"timestamp": "2026-08-04T00:00:00+00:00", "name": name, "primitive": primitive,
           "freq": freq, "params": json.dumps(params), "rationale": "x", "citation": "y"}
    header = not os.path.exists(harness.PIPELINE_LEDGER)
    pd.DataFrame([row]).to_csv(harness.PIPELINE_LEDGER, mode="a", header=header, index=False)


def test_pending_screens_is_empty_with_no_ledger(scratch):
    assert pd_.pending_screens() == []


def test_pending_screens_lists_an_unscreened_name(scratch):
    _write_ledger_row("rp_single_asset_trend_SPY_90")
    assert pd_.pending_screens() == ["rp_single_asset_trend_SPY_90"]


def test_pending_screens_excludes_an_already_screened_name(scratch):
    _write_ledger_row("rp_single_asset_trend_SPY_90")
    row = {"timestamp": "x", "strategy": "rp_single_asset_trend_SPY_90", "freq": "M",
           "calib_sharpe": 0.1, "calib_null_p50": 0.0, "passed": True}
    pd.DataFrame([row]).to_csv(harness.PRELIM_LOG, index=False)
    assert pd_.pending_screens() == []


def test_screen_pending_backlog_screens_and_preregisters_on_a_pass(scratch):
    _write_ledger_row("rp_single_asset_trend_SPY_90")
    results = pd_.screen_pending_backlog(screen_fn=lambda c: True,
                                         preregister_fn=lambda spec: True)
    assert results == [{"name": "rp_single_asset_trend_SPY_90", "passed": True,
                        "preregistered": True}]


def test_screen_pending_backlog_never_preregisters_a_failed_screen(scratch):
    _write_ledger_row("rp_single_asset_trend_SPY_90")

    def fake_preregister(spec):
        raise AssertionError("a failed backlog screen must never reach pre-registration")

    results = pd_.screen_pending_backlog(screen_fn=lambda c: False,
                                         preregister_fn=fake_preregister)
    assert results == [{"name": "rp_single_asset_trend_SPY_90", "passed": False,
                        "preregistered": False}]


def test_screen_pending_backlog_passes_rationale_and_citation_to_preregister(scratch):
    """The gap this whole step exists to close: preregister_candidate() needs
    rationale/citation to render STRATEGIES.md prose, and those only exist in
    PIPELINE_LEDGER, not in the {"name","sig_fn","freq"} shape prelim_screen() itself
    consumes -- _spec_for() must carry them through."""
    _write_ledger_row("rp_single_asset_trend_SPY_90")
    seen = {}

    def fake_preregister(spec):
        seen["spec"] = spec
        return True

    pd_.screen_pending_backlog(screen_fn=lambda c: True, preregister_fn=fake_preregister)
    assert seen["spec"]["rationale"] == "x"
    assert seen["spec"]["citation"] == "y"


# ---------------------------------------------------------------- compositional-leg guards (#194)
def _calib_prices(seed, tickers, n=2000):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(harness.CALIB_START, periods=n)
    return pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
                         for t in tickers}, index=idx)


def test_screen_pending_backlog_rejects_same_asset_class_without_loading_prices(scratch, monkeypatch):
    def boom():
        raise AssertionError("load_prices must not be called -- the cheap asset-class "
                              "check should reject this before any data is touched")
    monkeypatch.setattr(harness, "load_prices", boom)

    _write_ledger_row("rp_asset_class_trend_hedge_SPY_QQQ", primitive="asset_class_trend_hedge",
                      params={"ticker_a": "SPY", "ticker_b": "QQQ",
                              "lookback_a": 90, "lookback_b": 60})

    def fake_preregister(spec):
        raise AssertionError("a guard-rejected candidate must never reach pre-registration")

    results = pd_.screen_pending_backlog(preregister_fn=fake_preregister)
    assert results == [{"name": "rp_asset_class_trend_hedge_SPY_QQQ", "passed": False,
                        "preregistered": False}]


def test_screen_pending_backlog_rejects_correlated_legs_on_calibration_data(scratch, monkeypatch):
    identical = _calib_prices(3, ["TLT"])["TLT"]
    calib_prices = pd.DataFrame({"TLT": identical, "SPY": identical})
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))

    _write_ledger_row("rp_asset_class_trend_hedge_TLT_SPY", primitive="asset_class_trend_hedge",
                      params={"ticker_a": "TLT", "ticker_b": "SPY",
                              "lookback_a": 60, "lookback_b": 60})

    def fake_preregister(spec):
        raise AssertionError("a guard-rejected candidate must never reach pre-registration")

    results = pd_.screen_pending_backlog(preregister_fn=fake_preregister)
    assert results == [{"name": "rp_asset_class_trend_hedge_TLT_SPY", "passed": False,
                        "preregistered": False}]


def test_a_guard_rejected_candidate_does_not_resurface_on_the_next_cycle(scratch, monkeypatch):
    """The bug this test exists to catch: a name rejected by the #194 guards must still
    be marked 'screened' (PRELIM_LOG), or pending_screens() retries it forever."""
    monkeypatch.setattr(harness, "load_prices",
                        lambda: (_ for _ in ()).throw(AssertionError("must not be called")))
    _write_ledger_row("rp_asset_class_trend_hedge_SPY_QQQ", primitive="asset_class_trend_hedge",
                      params={"ticker_a": "SPY", "ticker_b": "QQQ",
                              "lookback_a": 90, "lookback_b": 60})
    pd_.screen_pending_backlog(preregister_fn=lambda spec: True)
    assert pd_.pending_screens() == []


def test_screen_pending_backlog_still_screens_a_valid_compositional_candidate(scratch, monkeypatch):
    calib_prices = _calib_prices(3, ["TLT", "SPY"])
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))

    _write_ledger_row("rp_asset_class_trend_hedge_TLT_SPY", primitive="asset_class_trend_hedge",
                      params={"ticker_a": "TLT", "ticker_b": "SPY",
                              "lookback_a": 60, "lookback_b": 60})

    results = pd_.screen_pending_backlog(screen_fn=lambda c: True,
                                         preregister_fn=lambda spec: True)
    assert results == [{"name": "rp_asset_class_trend_hedge_TLT_SPY", "passed": True,
                        "preregistered": True}]


def test_screen_pending_backlog_with_real_defaults_actually_preregisters(scratch, monkeypatch):
    """End-to-end with the real prelim_screen()/preregister_candidate() (no fakes) --
    catches a wiring bug fakes would hide, same reasoning test_pipeline_ideas.py's own
    real-prelim_screen() test uses, including its fix for the same trap: load_prices()
    must be mocked to synthetic data, or this test does real network I/O and blows
    conftest.py's 5s per-test budget (measured 6.21s against the real network in CI)."""
    idx = pd.bdate_range(harness.CALIB_START, periods=3000)
    rng = np.random.default_rng(7)
    calib_prices = pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 3000))) for t in
         ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG",
          "GLD", "SLV", "DBC", "USO", "VNQ", "UUP"]}, index=idx)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))

    _write_ledger_row("rp_single_asset_trend_SPY_90")
    results = pd_.screen_pending_backlog()
    assert len(results) == 1
    assert results[0]["name"] == "rp_single_asset_trend_SPY_90"
    assert isinstance(results[0]["passed"], bool)
    # whatever the real calibration-only screen decided, the ledger must reflect it
    prelim = pd.read_csv(harness.PRELIM_LOG)
    assert list(prelim["strategy"]) == ["rp_single_asset_trend_SPY_90"]
    assert bool(prelim["passed"].iloc[0]) == results[0]["passed"]


# ---------------------------------------------------------------- curve_carry guard (Phase 2)
def _calib_curve(seed, n=2000):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(harness.CALIB_START, periods=n)
    dgs2 = 3.0 + rng.normal(0, 0.001, n).cumsum() * 0
    dgs10 = dgs2 + np.linspace(0.5, 2.5, n)
    return pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)


def test_screen_pending_backlog_rejects_an_ineffective_curve_carry_hedge(scratch, monkeypatch):
    idx = pd.bdate_range(harness.CALIB_START, periods=1000)
    rng = np.random.default_rng(9)
    dgs2 = np.full(1000, 3.0)
    dgs10_moves = rng.normal(0.001, 0.02, 1000)
    dgs10 = 3.5 + np.cumsum(dgs10_moves)
    calib_curve = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)
    tlt = 100 * np.exp(np.cumsum(-dgs10_moves * 15 + rng.normal(0, 0.0002, 1000)))
    ief = np.full(1000, 100.0)
    calib_prices = pd.DataFrame({"TLT": tlt, "IEF": ief}, index=idx)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))
    monkeypatch.setattr(pkg_rates, "load_yield_curve", lambda: (calib_curve, "test"))

    _write_ledger_row("rp_curve_carry_60", primitive="curve_carry", params={"lookback": 60})

    def fake_preregister(spec):
        raise AssertionError("a guard-rejected candidate must never reach pre-registration")

    def boom_screen(candidate):
        raise AssertionError("prelim_screen must never run -- the guard should reject "
                             "this before the expensive screen is reached")

    results = pd_.screen_pending_backlog(screen_fn=boom_screen, preregister_fn=fake_preregister)
    assert results == [{"name": "rp_curve_carry_60", "passed": False, "preregistered": False}]


def test_a_curve_carry_guard_rejection_does_not_resurface_on_the_next_cycle(scratch, monkeypatch):
    idx = pd.bdate_range(harness.CALIB_START, periods=1000)
    rng = np.random.default_rng(9)
    dgs2 = np.full(1000, 3.0)
    dgs10_moves = rng.normal(0.001, 0.02, 1000)
    dgs10 = 3.5 + np.cumsum(dgs10_moves)
    calib_curve = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)
    tlt = 100 * np.exp(np.cumsum(-dgs10_moves * 15 + rng.normal(0, 0.0002, 1000)))
    ief = np.full(1000, 100.0)
    calib_prices = pd.DataFrame({"TLT": tlt, "IEF": ief}, index=idx)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))
    monkeypatch.setattr(pkg_rates, "load_yield_curve", lambda: (calib_curve, "test"))

    _write_ledger_row("rp_curve_carry_60", primitive="curve_carry", params={"lookback": 60})
    pd_.screen_pending_backlog(
        screen_fn=lambda c: (_ for _ in ()).throw(AssertionError("must not be called")),
        preregister_fn=lambda spec: True)
    assert pd_.pending_screens() == []


def test_screen_pending_backlog_still_screens_a_valid_curve_carry_candidate(scratch, monkeypatch):
    calib_prices = _calib_prices(3, ["TLT", "IEF"])
    calib_curve = _calib_curve(3)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))
    monkeypatch.setattr(pkg_rates, "load_yield_curve", lambda: (calib_curve, "test"))

    _write_ledger_row("rp_curve_carry_60", primitive="curve_carry", params={"lookback": 60})

    results = pd_.screen_pending_backlog(screen_fn=lambda c: True,
                                         preregister_fn=lambda spec: True)
    assert results == [{"name": "rp_curve_carry_60", "passed": True, "preregistered": True}]
