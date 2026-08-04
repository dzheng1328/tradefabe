"""
pipeline_daily.py — the research pipeline's daily driver (#178, extended by #179).

Genuinely thin on purpose, per #178's own design questions: #177's propose_idea()
already returns a dict harness.prelim_screen() (#175) can run against with no
translation, and prelim_screen() already logs every call -- pass or fail -- to
artifacts/prelim_log.csv for audit. There is no new mechanism in the propose/screen
steps, only the wiring: propose, then (if something was proposed) screen it.

#179 adds a THIRD step, automatic on a pass: pipeline_register.preregister_candidate()
freezes the candidate's spec to STRATEGIES.md and a durable ledger -- DOCTRINE v1.11's
fully-automatic checkpoint (Dave's explicit call, 2026-08-01), no human review before
the full OOS test (#180, not yet built) runs. A failed screen, or no proposal at all,
never reaches this step.

Usage: PYTHONPATH=src:.:research python research/pipeline_daily.py
"""
from __future__ import annotations

import harness
import pipeline_ideas
import pipeline_register


def run_daily_cycle(propose_fn=None, screen_fn=None, preregister_fn=None) -> dict:
    """Runs one day of the pipeline: propose (#177), screen (#175), and -- only on a
    pass -- pre-register (#179). Each `*_fn` is injectable for testing; all three
    default to the real functions. Returns a small summary dict; never raises on a
    normal "nothing happened today" outcome, since that's expected, not exceptional."""
    propose = propose_fn or pipeline_ideas.propose_idea
    screen = screen_fn or harness.prelim_screen
    preregister = preregister_fn or pipeline_register.preregister_candidate

    idea = propose()
    if idea is None:
        print("[pipeline_daily] nothing proposed today -- nothing to screen")
        return {"proposed": False, "name": None, "passed": None, "preregistered": False}

    passed = screen(idea)
    print(f"[pipeline_daily] {idea['name']} "
          f"{'PASSED' if passed else 'FAILED'} the prelim screen")
    if not passed:
        return {"proposed": True, "name": idea["name"], "passed": False, "preregistered": False}

    preregistered = preregister(idea)
    return {"proposed": True, "name": idea["name"], "passed": True,
            "preregistered": preregistered}


def main():
    run_daily_cycle()


if __name__ == "__main__":
    main()
