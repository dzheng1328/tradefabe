"""
pipeline_daily.py — the research pipeline's daily driver (#178, extended by #179, #180).

Genuinely thin on purpose, per #178's own design questions: #177's propose_idea()
already returns a dict harness.prelim_screen() (#175) can run against with no
translation, and prelim_screen() already logs every call -- pass or fail -- to
artifacts/prelim_log.csv for audit. There is no new mechanism in the propose/screen
steps, only the wiring: propose, then (if something was proposed) screen it.

#179 adds a THIRD step, automatic on a pass: pipeline_register.preregister_candidate()
freezes the candidate's spec to STRATEGIES.md and a durable ledger -- DOCTRINE v1.11's
fully-automatic checkpoint (Dave's explicit call, 2026-08-01), no human review before
the full OOS test runs. A failed screen, or no proposal at all, never reaches this step.

#180 adds a FOURTH step, run UNCONDITIONALLY every cycle regardless of what happened to
today's own proposal (or whether one was even made): pipeline_verdict.run_pending_oos_
tests() OOS-tests every pre-registered candidate that doesn't have a graveyard.csv row
yet. Unconditional, not gated on today's `preregistered` result, so a backlog -- e.g.
this step being added after a few days of #179 running alone -- clears on the next
cycle rather than staying stuck forever.

Usage: PYTHONPATH=src:.:research python research/pipeline_daily.py
"""
from __future__ import annotations

import harness
import pipeline_ideas
import pipeline_register
import pipeline_verdict


def run_daily_cycle(propose_fn=None, screen_fn=None, preregister_fn=None,
                    oos_test_fn=None) -> dict:
    """Runs one day of the pipeline: propose (#177), screen (#175), pre-register on a
    pass (#179), then OOS-test every pending pre-registered candidate regardless (#180).
    Each `*_fn` is injectable for testing; all four default to the real functions.
    Returns a small summary dict; never raises on a normal "nothing happened today"
    outcome, since that's expected, not exceptional."""
    propose = propose_fn or pipeline_ideas.propose_idea
    screen = screen_fn or harness.prelim_screen
    preregister = preregister_fn or pipeline_register.preregister_candidate
    oos_test = oos_test_fn or pipeline_verdict.run_pending_oos_tests

    idea = propose()
    if idea is None:
        print("[pipeline_daily] nothing proposed today -- nothing to screen")
        result = {"proposed": False, "name": None, "passed": None, "preregistered": False}
    else:
        passed = screen(idea)
        print(f"[pipeline_daily] {idea['name']} "
              f"{'PASSED' if passed else 'FAILED'} the prelim screen")
        if not passed:
            result = {"proposed": True, "name": idea["name"], "passed": False,
                      "preregistered": False}
        else:
            preregistered = preregister(idea)
            result = {"proposed": True, "name": idea["name"], "passed": True,
                      "preregistered": preregistered}

    result["oos_tested"] = oos_test()
    return result


def main():
    run_daily_cycle()


if __name__ == "__main__":
    main()
