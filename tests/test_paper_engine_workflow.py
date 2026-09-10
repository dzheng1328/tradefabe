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


def _field_values(field: str, low: int, high: int) -> set[int]:
    # Only "*" (matches the whole range) and a single literal integer are used anywhere in
    # paper-engine.yml's schedule -- no lists/ranges/steps -- so that's all this parses.
    if field == "*":
        return set(range(low, high + 1))
    return {int(field)}


def test_no_two_schedule_crons_can_collide_on_the_same_minute():
    # The hourly "0 * * * *" mark cron this test used to require existed was removed
    # entirely (mark now runs via cron-job.org's workflow_dispatch, not a native
    # schedule -- see CLAUDE.md's Live gotchas and this workflow's header comments). What
    # #152 actually guards against is any two on.schedule entries matching the same clock
    # minute, whatever those entries happen to be -- so check that generically instead of
    # hardcoding an hourly entry that no longer exists.
    crons = _schedule_crons()
    assert crons, "expected at least one on.schedule entry in paper-engine.yml"
    parsed = [
        (c, _field_values(c.split()[0], 0, 59), _field_values(c.split()[1], 0, 23))
        for c in crons
    ]
    for i, (c1, min1, hr1) in enumerate(parsed):
        for c2, min2, hr2 in parsed[i + 1 :]:
            collide = bool(min1 & min2) and bool(hr1 & hr2)
            assert not collide, (
                f"crons {c1!r} and {c2!r} can both match the same clock minute -- GitHub "
                "Actions coalesces two same-minute schedule matches into ONE triggered run "
                "and github.event.schedule then reports only one of the two cron strings, "
                'exactly like #152\'s original "0 22 * * *" colliding with the hourly '
                '"0 * * * *"'
            )


def test_every_non_hourly_cron_has_a_matching_case_branch():
    crons = _schedule_crons()
    script = _pick_cycle_script()
    for c in crons:
        assert f'"{c}"' in script, (
            f"cron {c!r} is declared in on.schedule but has no matching pattern in the "
            '"pick cycle" step -- it will silently fall through to the mark branch'
        )
