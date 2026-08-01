"""
pipeline_daily.py — the research pipeline's daily driver (#178).

Genuinely thin on purpose, per #178's own design questions: #177's propose_idea()
already returns a {"name","sig_fn","freq"} dict harness.prelim_screen() (#175) can run
against with no translation, and prelim_screen() already logs every call -- pass or fail
-- to artifacts/prelim_log.csv for audit. There is no new mechanism here, only the
wiring: propose, then (if something was proposed) screen it, then report what happened.

Nothing here touches OOS data or graveyard.csv -- prelim_screen() is calibration-only by
construction (DOCTRINE v1.9), so a day this cycle runs costs little compute even on a
candidate that fails, and a fail costs nothing else: no family_n_tested() draw, no
graveyard.csv row, no OOS test. That's #178's whole point, not something it has to add.

Usage: PYTHONPATH=src:.:research python research/pipeline_daily.py
"""
from __future__ import annotations

import harness
import pipeline_ideas


def run_daily_cycle(propose_fn=None, screen_fn=None) -> dict:
    """Runs one day of the pipeline: propose (#177), then screen whatever came back
    (#175). `propose_fn`/`screen_fn` are injectable for testing -- default to the real
    propose_idea()/prelim_screen(). Returns a small summary dict; never raises on a
    normal "nothing happened today" outcome, since that's expected, not exceptional."""
    propose = propose_fn or pipeline_ideas.propose_idea
    screen = screen_fn or harness.prelim_screen

    idea = propose()
    if idea is None:
        print("[pipeline_daily] nothing proposed today -- nothing to screen")
        return {"proposed": False, "name": None, "passed": None}

    passed = screen(idea)
    print(f"[pipeline_daily] {idea['name']} "
          f"{'PASSED' if passed else 'FAILED'} the prelim screen")
    return {"proposed": True, "name": idea["name"], "passed": passed}


def main():
    run_daily_cycle()


if __name__ == "__main__":
    main()
