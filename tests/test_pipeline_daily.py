"""research/pipeline_daily.py (#178, extended by #179-181): the pipeline's daily driver.

Deliberately thin, per #178's own design questions: propose_idea() (#177) already
returns something prelim_screen() (#175) can run with no translation, and
prelim_screen() already logs every outcome for audit. #179 adds one more step on a
pass: preregister_candidate(). #180 adds a step run UNCONDITIONALLY every cycle
regardless of today's own proposal outcome: run_pending_oos_tests(). #181 adds
screen_pending_backlog() -- also unconditional -- for the gap #180 didn't cover: a row
can now land in PIPELINE_LEDGER from something other than propose_idea()'s own
in-process API call (a research routine writing the ledger directly), and
already_proposed_today() would make propose() return None on any day a row already
exists, so without this step that externally-added row would never get screened at
all. There's no new mechanism to test in propose/screen themselves, only that the
wiring calls the right thing at the right time -- and, just as important, does NOT
call prelim_screen() on a day nothing was proposed, does NOT call
preregister_candidate() on a day the screen fails, and DOES still call the backlog and
OOS-test steps in every case (a backlog must clear even on a day with nothing new to
propose).
"""
import json
import os

import pandas as pd
import pytest

import harness
import pipeline_daily as pd_
import pipeline_register

IDEA = {"name": "rp_single_asset_trend_SPY_90", "sig_fn": lambda prices: prices, "freq": "M",
        "primitive": "single_asset_trend", "params": {"ticker": "SPY", "lookback": 90},
        "rationale": "x", "citation": "y"}


def test_nothing_proposed_means_nothing_screened_or_preregistered():
    def fake_propose():
        return None

    def fake_screen(idea):
        raise AssertionError("prelim_screen must not be called when nothing was proposed")

    def fake_preregister(idea):
        raise AssertionError("preregister must not be called when nothing was proposed")

    result = pd_.run_daily_cycle(propose_fn=fake_propose, screen_fn=fake_screen,
                                 preregister_fn=fake_preregister,
                                 backlog_fn=lambda: [], oos_test_fn=lambda: [])
    assert result == {"proposed": False, "name": None, "passed": None,
                      "preregistered": False, "backlog_screened": [], "oos_tested": []}


def test_a_failed_screen_is_reported_and_never_preregistered():
    def fake_preregister(idea):
        raise AssertionError("a failed screen must never reach pre-registration")

    result = pd_.run_daily_cycle(propose_fn=lambda: IDEA, screen_fn=lambda c: False,
                                 preregister_fn=fake_preregister,
                                 backlog_fn=lambda: [], oos_test_fn=lambda: [])
    assert result == {"proposed": True, "name": IDEA["name"], "passed": False,
                      "preregistered": False, "backlog_screened": [], "oos_tested": []}


def test_a_passed_screen_is_preregistered_with_the_exact_object_propose_returned():
    seen = {}

    def fake_preregister(candidate):
        seen["candidate"] = candidate
        return True

    result = pd_.run_daily_cycle(propose_fn=lambda: IDEA, screen_fn=lambda c: True,
                                 preregister_fn=fake_preregister,
                                 backlog_fn=lambda: [], oos_test_fn=lambda: [])
    assert seen["candidate"] is IDEA
    assert result == {"proposed": True, "name": IDEA["name"], "passed": True,
                      "preregistered": True, "backlog_screened": [], "oos_tested": []}


def test_an_idempotent_preregister_result_is_reported_faithfully():
    """preregister_candidate() returns False for an already-registered name (#179's own
    idempotency) -- run_daily_cycle() must report that truthfully, not always True."""
    result = pd_.run_daily_cycle(propose_fn=lambda: IDEA, screen_fn=lambda c: True,
                                 preregister_fn=lambda c: False,
                                 backlog_fn=lambda: [], oos_test_fn=lambda: [])
    assert result["preregistered"] is False


def test_the_oos_test_step_runs_even_on_a_day_nothing_was_proposed():
    """#180's own point: a backlog of pre-registered-but-untested candidates must clear
    on every cycle, not only on a cycle that also proposed something new today."""
    calls = []

    def fake_oos_test():
        calls.append(1)
        return [{"name": "rp_old_backlog_candidate", "verdict": "DEAD", "promoted": False}]

    result = pd_.run_daily_cycle(propose_fn=lambda: None, backlog_fn=lambda: [],
                                 oos_test_fn=fake_oos_test)
    assert calls == [1]
    assert result["oos_tested"] == [{"name": "rp_old_backlog_candidate", "verdict": "DEAD",
                                     "promoted": False}]


def test_the_screening_backlog_step_runs_even_on_a_day_nothing_was_proposed():
    """#181's own point: a PIPELINE_LEDGER row added by something other than propose()
    (a research routine writing the ledger directly) must still get screened on a day
    propose() itself found nothing new -- these are independent, not one gating the
    other."""
    calls = []

    def fake_backlog():
        calls.append(1)
        return [{"name": "rp_routine_written", "passed": True, "preregistered": True}]

    result = pd_.run_daily_cycle(propose_fn=lambda: None, backlog_fn=fake_backlog,
                                 oos_test_fn=lambda: [])
    assert calls == [1]
    assert result["backlog_screened"] == [{"name": "rp_routine_written", "passed": True,
                                           "preregistered": True}]


def test_defaults_wire_to_the_real_functions():
    """No stand-ins snuck into the default wiring -- an unpatched call must reach the
    real #177/#175/#179/#180/#181 functions, not a private copy."""
    import inspect
    src = inspect.getsource(pd_.run_daily_cycle)
    assert "pipeline_ideas.propose_idea" in src
    assert "harness.prelim_screen" in src
    assert "pipeline_register.preregister_candidate" in src
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


def test_screen_pending_backlog_with_real_defaults_actually_preregisters(scratch):
    """End-to-end with the real prelim_screen()/preregister_candidate() (no fakes) on a
    trending synthetic-enough real ticker -- catches a wiring bug fakes would hide,
    same reasoning test_pipeline_ideas.py's real prelim_screen() test uses."""
    _write_ledger_row("rp_single_asset_trend_SPY_90")
    results = pd_.screen_pending_backlog()
    assert len(results) == 1
    assert results[0]["name"] == "rp_single_asset_trend_SPY_90"
    assert isinstance(results[0]["passed"], bool)
    # whatever the real calibration-only screen decided, the ledger must reflect it
    prelim = pd.read_csv(harness.PRELIM_LOG)
    assert list(prelim["strategy"]) == ["rp_single_asset_trend_SPY_90"]
    assert bool(prelim["passed"].iloc[0]) == results[0]["passed"]
