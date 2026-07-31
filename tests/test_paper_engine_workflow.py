"""Regression guard for #152: two `on.schedule` crons landing on the same clock minute
in the same workflow get coalesced by GitHub Actions into a single triggered run, and
`github.event.schedule` then reports only ONE of the two matching cron strings -- never
both. The "pick cycle" step's case statement matched on the exact daily cron string, so
for 55/55 scheduled runs (2026-07-25 through 2026-07-31) it silently never matched the
daily branch: every real rebalance/Kronos-forecast cycle was skipped in favor of a bare
mark, and nothing here would have caught it -- there was no test at all for this file
before #152. This test parses the actual YAML rather than hand-copying values, so it
fails the moment the workflow and the case statement drift apart again."""
import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "paper-engine.yml"


def _schedule_crons() -> list[str]:
    doc = yaml.safe_load(WORKFLOW.read_text())
    # YAML parses the bare `on:` key as the boolean True, not the string "on" -- PyYAML's
    # implicit-boolean resolution for YAML 1.1, not a typo here.
    on = doc.get("on", doc.get(True))
    return [entry["cron"] for entry in on["schedule"]]


def _pick_cycle_script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text())
    for job in doc["jobs"].values():
        for step in job["steps"]:
            if step.get("name") == "pick cycle":
                return step["run"]
    raise AssertionError('no step named "pick cycle" found -- has it been renamed?')


def _minute_field(cron: str) -> str:
    return cron.split()[0]


def test_no_two_schedule_crons_can_collide_on_the_same_minute():
    crons = _schedule_crons()
    hourly = [c for c in crons if c == "0 * * * *"]
    others = [c for c in crons if c != "0 * * * *"]
    assert hourly, "the hourly mark cron is expected to exist and match this exact string"
    # ANY cron whose minute field is "0" fires at minute :00 of whichever hour(s) it
    # matches, which the hourly "0 * * * *" ALSO matches every single hour -- the exact
    # collision #152 was. Every other schedule entry must use a non-zero minute.
    for c in others:
        assert _minute_field(c) != "0", (
            f"cron {c!r} shares minute 0 with the hourly mark cron -- this collides "
            "exactly like #152's original \"0 22 * * *\" did, and GitHub Actions will "
            "silently coalesce the two into one triggered run"
        )


def test_every_non_hourly_cron_has_a_matching_case_branch():
    crons = [c for c in _schedule_crons() if c != "0 * * * *"]
    script = _pick_cycle_script()
    for c in crons:
        assert f'"{c}"' in script, (
            f"cron {c!r} is declared in on.schedule but has no matching pattern in the "
            '"pick cycle" step -- it will silently fall through to the mark branch'
        )
