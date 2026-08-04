"""
pipeline_daily.py — the research pipeline's daily driver (#178, extended by #179-181;
#177's own in-process propose() call retired 2026-08-04, superseded by a Claude Code
Routine).

Originally: propose (#177's in-process Haiku API call) -> screen (#175) -> pre-register
on a pass (#179) -> OOS-test regardless (#180). #177's propose_idea() is no longer
called from here -- Dave's explicit call, 2026-08-04: proposal now comes from a
scheduled Claude Code Routine (real research, real tool use, running under his Pro
subscription, not a $0.05/day-capped closed-book Haiku call) that writes PIPELINE_LEDGER
(pipeline_ideas.csv) directly. research/pipeline_ideas.py's propose_idea()/build_signal()/
validate_proposal() etc. still exist and are still tested (their contract -- a name/
primitive/params/freq/rationale/citation row -- is exactly what the routine replicates
by hand) but nothing in the automated daily cron calls propose_idea() anymore; it's kept
as a still-usable manual fallback, not wired into this driver.

This module's job now: screen (#175) whatever's sitting in PIPELINE_LEDGER unscreened,
pre-register on a pass (#179), and OOS-test (#180) whatever's pre-registered and
untested -- both UNCONDITIONALLY every cycle, regardless of whether anything new landed
in the ledger today. That "unconditional, clears a backlog" property is deliberate for
both steps: pending_screens()/screen_pending_backlog() (#181) exist because
already_proposed_today() would otherwise make a since-retired propose() step swallow an
externally-added row as "nothing proposed today"; pipeline_verdict.run_pending_oos_tests()
(#180) has the identical shape one stage later.

Usage: PYTHONPATH=src:.:research python research/pipeline_daily.py
"""
from __future__ import annotations
import os

import pandas as pd

import harness
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
    Returns one {"name","passed","preregistered"} summary per candidate screened.

    This is also the ONE mechanical checkpoint an asset_class_trend_hedge candidate
    (#194) is guaranteed to pass through regardless of origin: the research routine
    writes PIPELINE_LEDGER rows directly, bypassing pipeline_ideas.validate_proposal()
    entirely, so its offline asset-class check can't be relied on alone. A candidate
    that fails either #194 guard is rejected here, before the (comparatively expensive)
    prelim screen ever runs on it -- and is still logged to PRELIM_LOG (NaN
    sharpe/bar -- the real calibration Sharpe check never ran) via harness._log_prelim(),
    the same private helper harness.prelim_screen() itself uses, so pending_screens()
    doesn't keep resurfacing a guard-rejected name forever; without this it would never
    appear "screened" and would be retried every single cycle."""
    screen = screen_fn or harness.prelim_screen
    preregister = preregister_fn or pipeline_register.preregister_candidate

    results = []
    calib_prices = None   # loaded lazily -- only an asset_class_trend_hedge candidate
                          # that already cleared the cheap asset-class check needs it
    for name in pending_screens():
        spec = pipeline_verdict._spec_for(name)

        if spec["primitive"] == "asset_class_trend_hedge":
            if not pkg_pipeline.legs_differ_by_asset_class(spec["params"]):
                print(f"[pipeline_daily] {name} (backlog) FAILED the asset-class guard "
                      f"(#194) -- skipping prelim screen")
                harness._log_prelim(name, spec["freq"], float("nan"), float("nan"), False)
                results.append({"name": name, "passed": False, "preregistered": False})
                continue
            if calib_prices is None:
                prices, _ = harness.load_prices()
                calib_prices = prices.loc[(prices.index >= harness.CALIB_START) &
                                          (prices.index <= harness.CALIB_END)]
            if not pkg_pipeline.legs_pass_calibration_corr_cap(
                    spec["primitive"], spec["params"], calib_prices):
                print(f"[pipeline_daily] {name} (backlog) FAILED the calibration-"
                      f"correlation guard (#194) -- skipping prelim screen")
                harness._log_prelim(name, spec["freq"], float("nan"), float("nan"), False)
                results.append({"name": name, "passed": False, "preregistered": False})
                continue

        sig_fn = pkg_pipeline.build_signal(spec["primitive"], spec["params"])
        passed = screen({"name": name, "sig_fn": sig_fn, "freq": spec["freq"]})
        print(f"[pipeline_daily] {name} (backlog) "
              f"{'PASSED' if passed else 'FAILED'} the prelim screen")
        preregistered = preregister(spec) if passed else False
        results.append({"name": name, "passed": passed, "preregistered": preregistered})
    return results


def run_daily_cycle(backlog_fn=None, oos_test_fn=None) -> dict:
    """Runs one day of the pipeline: screen+pre-register (#175/#179) whatever's pending
    in PIPELINE_LEDGER, then OOS-test (#180) whatever's pending pre-registration --
    unconditional, every cycle, regardless of whether anything new landed today. Both
    `*_fn` are injectable for testing; both default to the real functions. Returns a
    small summary dict; never raises on a normal "nothing pending" outcome, since that's
    expected, not exceptional."""
    backlog = backlog_fn or screen_pending_backlog
    oos_test = oos_test_fn or pipeline_verdict.run_pending_oos_tests

    return {"backlog_screened": backlog(), "oos_tested": oos_test()}


def main():
    run_daily_cycle()


if __name__ == "__main__":
    main()
