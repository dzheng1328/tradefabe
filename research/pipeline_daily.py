"""
pipeline_daily.py — the research pipeline's daily driver (#178, extended by #179-181).

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

#181 adds a fifth step for the same reason: PIPELINE_LEDGER (pipeline_ideas.csv) can now
gain a row from something OTHER than propose_idea()'s own in-process API call -- a
research routine that writes the ledger directly (real research, real tool use, not the
cheap single-shot call). Once ANY row exists for today, already_proposed_today() makes
propose() return None, so the ORIGINAL propose->screen wiring above would silently never
screen that externally-added row -- it isn't "nothing proposed today," it's "something
was proposed by someone else." screen_pending_backlog() closes that gap the same way
#180 closed the pre-registered-but-untested one: find every PIPELINE_LEDGER name with no
prelim_log.csv row yet, and screen (then pre-register on a pass) each one, unconditional
of today's own propose() outcome.

Usage: PYTHONPATH=src:.:research python research/pipeline_daily.py
"""
from __future__ import annotations
import os

import pandas as pd

import harness
import pipeline_ideas
import pipeline_register
import pipeline_verdict
from tradefabe import pipeline as pkg_pipeline


def pending_screens() -> list[str]:
    """PIPELINE_LEDGER names that have never been screened (#175) yet -- the same
    "proposed but not yet acted on" backlog concept as pipeline_verdict.
    pending_candidates(), one stage earlier in the pipeline ("not yet screened" instead
    of "not yet OOS-tested"). Ordered oldest-first, same reasoning: a backlog clears in
    proposal order, not an arbitrary one."""
    if not os.path.exists(harness.PIPELINE_LEDGER):
        return []
    ledger = pd.read_csv(harness.PIPELINE_LEDGER)
    screened = set()
    if os.path.exists(harness.PRELIM_LOG):
        screened = set(pd.read_csv(harness.PRELIM_LOG)["strategy"].unique())
    names = list(dict.fromkeys(ledger["name"]))   # de-dup, preserve first-seen order
    return [n for n in names if n not in screened]


def screen_pending_backlog(screen_fn=None, preregister_fn=None) -> list[dict]:
    """Screens (#175) and pre-registers on a pass (#179) every PIPELINE_LEDGER name
    pending_screens() finds -- usually 0 or 1 (a research routine, like propose_idea(),
    is expected to write at most one row/day), but a real backlog (e.g. this step not
    having existed yet, or a screen run that failed mid-cycle) is handled the same way.
    Returns one {"name","passed","preregistered"} summary per candidate screened."""
    screen = screen_fn or harness.prelim_screen
    preregister = preregister_fn or pipeline_register.preregister_candidate

    results = []
    for name in pending_screens():
        spec = pipeline_verdict._spec_for(name)
        sig_fn = pkg_pipeline.build_signal(spec["primitive"], spec["params"])
        passed = screen({"name": name, "sig_fn": sig_fn, "freq": spec["freq"]})
        print(f"[pipeline_daily] {name} (backlog) "
              f"{'PASSED' if passed else 'FAILED'} the prelim screen")
        preregistered = preregister(spec) if passed else False
        results.append({"name": name, "passed": passed, "preregistered": preregistered})
    return results


def run_daily_cycle(propose_fn=None, screen_fn=None, preregister_fn=None,
                    backlog_fn=None, oos_test_fn=None) -> dict:
    """Runs one day of the pipeline: propose (#177), screen (#175), pre-register on a
    pass (#179), screen+pre-register any OTHER pending PIPELINE_LEDGER row regardless
    (#181), then OOS-test every pending pre-registered candidate regardless (#180). Each
    `*_fn` is injectable for testing; all five default to the real functions. Returns a
    small summary dict; never raises on a normal "nothing happened today" outcome, since
    that's expected, not exceptional."""
    propose = propose_fn or pipeline_ideas.propose_idea
    screen = screen_fn or harness.prelim_screen
    preregister = preregister_fn or pipeline_register.preregister_candidate
    backlog = backlog_fn or screen_pending_backlog
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

    result["backlog_screened"] = backlog()
    result["oos_tested"] = oos_test()
    return result


def main():
    run_daily_cycle()


if __name__ == "__main__":
    main()
