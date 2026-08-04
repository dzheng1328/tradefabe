---
name: workflow-watch
description: Trigger and/or monitor one of tradefabe's scheduled GitHub Actions workflows (paper engine, pipeline daily, cost check) -- polls status, and on completion pulls the real signal out of the log rather than just reporting pass/fail. Use whenever asked to check on, kick off, or debug a scheduled workflow run, instead of hand-rolling gh workflow run / gh run list / gh run view each time.
---

# workflow-watch

Four workflows exist in `.github/workflows/`. Only three can be triggered by hand:

| name (`gh workflow run "<name>"`) | file | manual trigger | notes |
|---|---|---|---|
| `paper engine` | `paper-engine.yml` | `gh workflow run "paper engine" -f job=mark\|run\|factory` (default `mark`) | writes `state/`, committed by the Action itself |
| `pipeline daily` | `pipeline-daily.yml` | `gh workflow run "pipeline daily"` | no inputs; has a `concurrency:` guard, a second trigger queues rather than races |
| `cost check` | `cost-check.yml` | `gh workflow run "cost check"` | no inputs; places real Alpaca PAPER orders |
| `tests` | `tests.yml` | **cannot be triggered manually** | push/PR on `main` only, no `workflow_dispatch` -- don't try, it'll error |

## 1. Confirm before triggering

Only fire a `gh workflow run` if the user explicitly asked for a run, or already agreed to
one in the conversation. These aren't read-only — `paper engine` and `cost check` place
real (paper) orders or move book state, `pipeline daily` can write to `STRATEGIES.md` and
`graveyard.csv`. Checking status of an *existing* run needs no confirmation; starting a new
one does.

## 2. Trigger, then find the run

```sh
gh workflow run "<name>" [-f job=...]
sleep 5   # the run needs a moment to register
gh run list --workflow="<name>" --limit 1 --json databaseId,status,createdAt
```

## 3. Poll without busy-waiting

Use `ScheduleWakeup` (60-90s out) rather than a sleep loop or repeated manual checks — these
runs typically finish in well under 2 minutes. Check `gh run view <id> --json status,conclusion`;
`status` must be `completed` before `conclusion` means anything.

## 4. On completion, pull the actual signal — don't just report pass/fail

Every script in this pipeline prints bracketed, module-prefixed status lines carrying the
real narrative (`[pipeline_daily]`, `[pipeline_verdict]`, `[pipeline_ideas]`,
`[merge_routine_branches]`, `[cost_check]`). A "success" conclusion on `pipeline daily`
that did nothing (nothing pending) looks identical in `gh run view --json conclusion` to
one that screened and pre-registered a real candidate — the difference is only in these
lines:

```sh
gh run view <id> --log 2>&1 | grep -E "\[pipeline_daily\]|\[pipeline_verdict\]|\[pipeline_ideas\]|\[merge_routine_branches\]"
```

Report what it actually *did*, not just that it passed.

## 5. On failure, diagnose before reporting

```sh
gh run view <id> --log-failed
```

Read the actual traceback/error, not just the red X. This pipeline has shipped real,
non-obvious bugs before (a `git add` on a nonexistent path silently dropping every commit,
a missing `concurrency:` guard) — "it failed" is not a report, the root cause is.

## 6. If checking CI on a PR rather than a scheduled run

Use `gh pr checks <N>` (or `--watch --interval 20` to block until done, cheaper than manual
polling). Before trusting a green check, confirm it ran against the CURRENT head:

```sh
gh run view <id> --json headSha -q .headSha
git rev-parse origin/<branch>
```

`--watch` can return a pass from an earlier push if the PR was updated mid-watch.
