"""research/pipeline_daily.py (#178, extended by #179, #180): the pipeline's daily driver.

Deliberately thin, per #178's own design questions: propose_idea() (#177) already
returns something prelim_screen() (#175) can run with no translation, and
prelim_screen() already logs every outcome for audit. #179 adds one more step on a
pass: preregister_candidate(). #180 adds a FOURTH step, run UNCONDITIONALLY every
cycle regardless of today's own proposal outcome: run_pending_oos_tests(). There's no
new mechanism to test here, only that the wiring calls the right thing at the right
time -- and, just as important, does NOT call prelim_screen() on a day nothing was
proposed, does NOT call preregister_candidate() on a day the screen fails, and DOES
still call the OOS-test step in every case (a backlog must clear even on a day with
nothing new to propose).
"""
import pipeline_daily as pd_

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
                                 preregister_fn=fake_preregister, oos_test_fn=lambda: [])
    assert result == {"proposed": False, "name": None, "passed": None,
                      "preregistered": False, "oos_tested": []}


def test_a_failed_screen_is_reported_and_never_preregistered():
    def fake_preregister(idea):
        raise AssertionError("a failed screen must never reach pre-registration")

    result = pd_.run_daily_cycle(propose_fn=lambda: IDEA, screen_fn=lambda c: False,
                                 preregister_fn=fake_preregister, oos_test_fn=lambda: [])
    assert result == {"proposed": True, "name": IDEA["name"], "passed": False,
                      "preregistered": False, "oos_tested": []}


def test_a_passed_screen_is_preregistered_with_the_exact_object_propose_returned():
    seen = {}

    def fake_preregister(candidate):
        seen["candidate"] = candidate
        return True

    result = pd_.run_daily_cycle(propose_fn=lambda: IDEA, screen_fn=lambda c: True,
                                 preregister_fn=fake_preregister, oos_test_fn=lambda: [])
    assert seen["candidate"] is IDEA
    assert result == {"proposed": True, "name": IDEA["name"], "passed": True,
                      "preregistered": True, "oos_tested": []}


def test_an_idempotent_preregister_result_is_reported_faithfully():
    """preregister_candidate() returns False for an already-registered name (#179's own
    idempotency) -- run_daily_cycle() must report that truthfully, not always True."""
    result = pd_.run_daily_cycle(propose_fn=lambda: IDEA, screen_fn=lambda c: True,
                                 preregister_fn=lambda c: False, oos_test_fn=lambda: [])
    assert result["preregistered"] is False


def test_the_oos_test_step_runs_even_on_a_day_nothing_was_proposed():
    """#180's own point: a backlog of pre-registered-but-untested candidates must clear
    on every cycle, not only on a cycle that also proposed something new today."""
    calls = []

    def fake_oos_test():
        calls.append(1)
        return [{"name": "rp_old_backlog_candidate", "verdict": "DEAD", "promoted": False}]

    result = pd_.run_daily_cycle(propose_fn=lambda: None, oos_test_fn=fake_oos_test)
    assert calls == [1]
    assert result["oos_tested"] == [{"name": "rp_old_backlog_candidate", "verdict": "DEAD",
                                     "promoted": False}]


def test_defaults_wire_to_the_real_functions():
    """No stand-ins snuck into the default wiring -- an unpatched call must reach the
    real #177/#175/#179/#180 functions, not a private copy."""
    import inspect
    src = inspect.getsource(pd_.run_daily_cycle)
    assert "pipeline_ideas.propose_idea" in src
    assert "harness.prelim_screen" in src
    assert "pipeline_register.preregister_candidate" in src
    assert "pipeline_verdict.run_pending_oos_tests" in src
