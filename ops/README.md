# ops/ — build scripts, and the RETIRED launchd agents

> **The paper engine no longer runs here (#63).** It runs in GitHub Actions
> (`.github/workflows/paper-engine.yml`) because launchd does not fire while the Mac is
> asleep, which left multi-hour holes in the ledger. **The cloud is the sole owner of
> `state/`** — run `git pull` before reading the dashboard locally. The plists below are
> kept for reference and are installed as `*.plist.disabled`; re-enabling one while the
> Action runs would fork the ledger.

## Scripts (still current)

- `setup_venv.sh` — create the venv outside iCloud (#60). Use this, not `python3 -m venv`.
- `build_app.sh` — rebuild `~/Applications/tradefabe.app` (#61).

# Reference: the retired launchd agents

The three jobs that run this lab unattended. **These files are the source of truth**;
the copies macOS actually reads live in `~/Library/LaunchAgents/`. Historically the
installed copies were the only ones that existed, which meant a wipe or a machine change
lost them silently (same class of problem as issue #61's untracked `.app`).

| job | what it does | cadence |
|---|---|---|
| `com.dzheng.tradefabe` | `tradefabe run` — rebalance due books on their own M/W/D schedules, then mark | daily 18:00 |
| `com.dzheng.tradefabe.mark` | `tradefabe mark` — mark-only, no rebalance, so the live chart has more than one point/day | every 30 min |
| `com.dzheng.tradefabe.factory` | `research/factory_run.py --n 20` — one strategy-factory cycle (#38) | daily 17:00 |

The factory runs at 17:00, an hour before the 18:00 `run`, on purpose: it promotes its
best candidate to a live paper book, and `runner.py` reads the promotion registries at
import time, so a 17:00 promotion opens its book that same evening instead of a day later.

## Desktop app

`./ops/build_app.sh` rebuilds `~/Applications/tradefabe.app` from scratch (`--dest` to
build elsewhere). The bundle is not tracked; this script and `ops/icon.icns` are, which is
the part that was previously unrecoverable.

## Install / reinstall

```sh
cp ops/com.dzheng.tradefabe.factory.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.dzheng.tradefabe.factory.plist 2>/dev/null
launchctl load  ~/Library/LaunchAgents/com.dzheng.tradefabe.factory.plist
launchctl list | grep tradefabe          # confirm it registered
```

Run one immediately without waiting for the schedule:
`launchctl kickstart gui/$(id -u)/com.dzheng.tradefabe.factory`

Logs: `state/logs/{run,mark}.{log,err}` for the two older jobs,
`~/Library/Logs/tradefabe/factory.{log,err}` for the factory — see the TCC note below
for why that one is different.

## The EX_CONFIG trap (cost an hour; read this before adding a fourth job)

A launchd job that fails at *setup* exits **78 (EX_CONFIG)** and writes **nothing** to
its log — there is no error message anywhere, because the log is exactly what could not
be configured. Two separate causes bit this plist:

**1. Log paths under `~/Documents` are TCC-protected.** This repo *used to* live in
`~/Documents/tradefabe` (it now lives at `~/tradefabe`), and the Homebrew python binary
the factory job execs had no permission to write there when spawned by launchd. The
finding is kept because the compatibility symlink at the old location still resolves into
TCC territory for anything that follows it. The two older jobs get away with
`state/logs/` because they exec the `tradefabe` console script, which holds that grant;
a different binary does not inherit it. Confirmed by bisection — identical plist, only
the log path changed:

| `StandardOutPath` | result |
|---|---|
| `/tmp/...` | exit 0, runs |
| `~/Library/Logs/tradefabe/...` | exit 0, runs |
| `<repo>/state/logs/...` | **EX_CONFIG (78)**, empty log |

So the factory logs to `~/Library/Logs/tradefabe/`. If you ever move the other two jobs
onto a different interpreter, they will hit this too.

**2. Doubled hyphens inside XML comments.** `--` is illegal inside an XML comment.
`plutil -lint` accepts it happily; stricter parsers reject the whole file. Validate with
`xmllint --noout ops/*.plist`, never `plutil` alone. Writing `--n` or `--seed` in a
comment is enough to do it.

## Two more things to know

**Paths are absolute and hardcoded** to `/Users/dzheng/tradefabe`. launchd agents get no
shell profile and no useful working directory by default, so there is no `$HOME`-relative
form to fall back on. Moving the repo means editing all three files — which is exactly
what the 2026-07-26 move out of iCloud required. Point them at the real path, never at
the `~/Documents/tradefabe` compatibility symlink.

**`PYTHONPATH` is baked in on purpose.** It is not just convenience — it sidesteps the
Python 3.14 hidden-`.pth` bug (CLAUDE.md's Known gaps, issue #60) that otherwise makes
`import tradefabe` fail after a perfectly good editable install. The factory job needs
three roots on the path (`src`, repo root, `research`) because `factory_run.py` imports
`harness` and `piggyback_backtest`, which are repo-root/research scripts rather than
package modules.

## The factory job dirties the working tree

Unlike the other two — which only write to gitignored `state/` — a factory cycle appends
to three **git-tracked** files: `graveyard.csv`, `generated_templates.csv`, and
`artifacts/factory_returns.csv`. That is by design (the count IS the multiple-testing
record, see DOCTRINE.md), but it means `git status` is dirty every day the job runs.

Nothing auto-commits this, deliberately: a cron that commits to a tracked ledger on its
own is a good way to get a surprising history. Commit the day's rows yourself when you
next touch the repo.
