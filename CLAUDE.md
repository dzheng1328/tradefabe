# tradefabe — orientation for agents working in this repo

Read this first. It's the fast path to full context; `README.md` / `DOCTRINE.md` /
`STRATEGIES.md` / `ops/README.md` have the detail this file only points at.

**This file is loaded into every session and re-injected after every compaction. Keep it
short.** A fixed-and-guarded bug does not belong here — the guard is the memory. Write
the one-line rule and the test that enforces it, not the post-mortem.

## What this is
A doctrine-governed lab that tests trading strategies honestly, plus a paper-trading
engine that runs the survivors as autonomous simulated books. **Paper only.**

**Hard rule, no exceptions without Dave explicitly saying so in chat:** never execute a
real trade, never connect real money/credentials, never give personalized investment
advice (state that boundary instead). This is a standing constraint, not a per-task one.

**Git workflow:** branch + PR, never direct pushes to `main`. One branch per issue,
`gh pr create` with a body summarizing the change and test plan, merge after CI is green.

**The repo lives at `~/tradefabe`** (moved out of `~/Documents` 2026-07-26 — iCloud sync
there corrupted the venv and wrote conflict copies of tracked files). A compatibility
symlink remains at the old path. Never point new config at it; use the real path.

## The one-line finding
49+ strategies tested (trend, congress-copy, insider-copy, thematic, day-trading wicks,
plus a growing automated factory of parametrized variants) — all DEAD against
pre-registered kill rules. Two things survived: diversified buy-and-hold, and
delta-neutral **crypto funding carry** (~12%/yr net 2023–26, paid for bearing real
crypto-infra tail risk). Don't relitigate this; extend it. New candidates go through the
same doctrine — no lower bar because "this one feels different" or "a machine found it".

## Layout
```
src/tradefabe/     installable engine: engine.py (data/sizing/returns core, single source
                   of truth), signals.py, books.py, piggyback.py, factory.py (template
                   library + live generation), carry_live.py, carry_risk.py, runner.py,
                   cli.py, desktop.py, risk_register.py, paths.py
app.py             Streamlit dashboard, port 8501. Two sidebar views: Paper Books (live
                   books, cards grouped by family) and Research Lab (verdicts, luck floor,
                   correlation, piggyback lab, DEAD-strategy detail). Plotly only, no
                   matplotlib in the runtime path. No emoji in the UI — use Material
                   Symbols (`icon=":material/..."`) or the `.tf-badge` component.
harness.py         research evaluator: doctrine gates (DSR/CPCV), noise floors,
                   graveyard.csv writer. Imports its core from src/tradefabe — no
                   duplicated math.
research/          one-off studies incl. factory_run.py (the strategy factory's driver)
tests/             pytest suite. pyproject's `pythonpath = [".", "research"]` is what makes
                   `import harness` / `import factory_run` resolve under pytest.
ops/               launchd plists (retired, see Automations), build_app.sh, setup_venv.sh
graveyard.csv      the verdict ledger — every strategy ever evaluated, alive or dead.
generated_templates.csv   the factory's OWN ledger — every live-generated candidate's full
                   spec, logged at generation time BEFORE its verdict is known.
artifacts/         generated curves/meta per study (tracked in git)
state/paper/       book ledgers, carry_risk.json, promotion registries. Tracked in git and
                   OWNED BY THE ACTION — see Automations before writing here locally.
```

## Commands
```sh
ops/setup_venv.sh                   # rebuild the venv (refuses to build inside a synced tree)
.venv/bin/pip install -e ".[dev,desktop]"   # BOTH extras — see the pywebview trap below
.venv/bin/tradefabe run             # one daily cycle: rebalance due books + carry risk monitor
.venv/bin/tradefabe mark            # mark to current price, no rebalance
.venv/bin/tradefabe status          # current book equities
.venv/bin/tradefabe reset           # wipe paper state, restart at $100k/book
.venv/bin/streamlit run app.py      # dashboard at localhost:8501
.venv/bin/python harness.py         # re-run doctrine evaluation, appends graveyard.csv
.venv/bin/pytest tests/             # test suite (also runs in CI on push/PR to main)
PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" \
  .venv/bin/python research/factory_run.py --n 20   # one factory cycle by hand
```
`PYTHONPATH` is not needed for anything but that last line (`factory_run.py` imports the
repo-root `harness` and `research/piggyback_backtest`, which only pytest resolves for you).

## Automations — nine things run without you
Know all of them before assuming a file changed by magic.

**1–3. Scheduled** (`.github/workflows/paper-engine.yml`) — **the paper engine runs in the
cloud, not on the Mac.** launchd didn't fire while the machine slept. **The Action is the
SOLE OWNER of `state/`**: it commits the ledger every cycle, so `git pull` before reading
the dashboard locally, and don't commit local `state/` writes. The three launchd plists in
`ops/` are retired to `*.plist.disabled`; re-enabling one forks the ledger.
- **mark** — hourly (best-effort; GitHub often spaces these ~2h apart).
- **factory** — daily 21:00 UTC, `research/factory_run.py --n 20`.
- **run** — daily 22:00 UTC, an hour after factory so a promotion opens its book the same
  cycle (`runner.py` reads the promotion registries at import time).

By hand: `gh workflow run "paper engine" -f job=mark|run|factory`. Cost ~810 min/month
against the 2,000 free allowance. GitHub disables schedules on repos with no *human*
activity for ~60 days and the bot's own commits may not count — check that first if the
schedule goes quiet.

**4. CI** (`.github/workflows/tests.yml`) — `pytest tests/`. **Trigger is push/PR on
`main` ONLY.** A PR targeting any other branch gets no checks at all; `gh pr checks`
reports "no checks reported", which reads like a failure but means the workflow never
fired. This bites stacked PRs — run the suite locally before trusting one is green.

**5–7. In-process** (inside the scheduled jobs, so invisible in `launchctl list`):
- **`run_carry()`** — accrues real Hyperliquid funding. Called by both `run_daily()` and
  `run_mark()`, so it stamps a minute-resolution history row ~48x/day.
- **`check_carry_risk()`** — funding-flip + liquidation distance. Called by `run_daily()`
  **only**, so `carry_risk.json` refreshes daily, not hourly; the dashboard prints its
  `generated_at` and it lagging by up to a day is expected. Never raises.
- **Factory auto-promotion** — every cycle promotes its best-DSR candidate regardless of
  verdict, writing `state/paper/promoted*.json`. `runner.py` reads those at **import
  time**, so a promotion only takes effect in the next `run`/`mark` process.

**8–9. Dev config** — `.claude/settings.json` (tracked; lets agents run `gh`/`git`
unprompted, denies `gh repo delete` and force-push) and `.claude/launch.json` (dashboard
preview config). `.claude/settings.local.json` is Dave's gitignored overlay.

**Desktop app** (user-launched, not automated): `~/Applications/tradefabe.app`. Rebuild
with **`ops/build_app.sh`** — the bundle isn't in git but its build script is.

## Doctrine — read DOCTRINE.md before adding or judging any strategy
Pre-registered, OOS-only (2018+), data-derived noise floor (500 random strategies per
freq), fair 60/40 benchmark, three kill gates (beat luck / earn your place / not more
painful). **v1.4 is current**: gate 1 decides on Deflated Sharpe Ratio + Combinatorial
Purged CV (`harness.deflated_sharpe_ratio()`), motivated by exactly the high-volume
automated search the factory does. Bonferroni (`harness.bonferroni_bar()`) is still
computed and logged for continuity but no longer decides ALIVE/DEAD. v1.2 defines paper
promote/kill criteria: **a backtest-DEAD book stays monitor-only forever, never
`paper-confirmed`, no matter how good its paper data looks.** A v1.1 touching gate 2
(diversifier clause) was discussed and is **not approved** — don't apply it.

Roster, evidence, and family taxonomy: `STRATEGIES.md`. Add new candidates there *before*
running them — including the factory's `GENERATION_RANGES` (the range is the
pre-registration; the drawn value is logged to `generated_templates.csv`).

## Strategy factory — automated, high-volume, still doctrine-gated
`src/tradefabe/factory.py` + `research/factory_run.py` test ~20 candidates per cycle
instead of one hand-picked strategy, through the same DSR/CPCV gate.
- **Live generation is deliberately NOT free-form.** Only the parameter RANGE per family
  is fixed in code (reviewed once); the drawn value is logged to `generated_templates.csv`
  **before** its verdict is known — the fix for the meta-level p-hacking risk DOCTRINE.md
  warns about.
- **Promotion picks the single best-DSR candidate each cycle regardless of verdict** —
  Dave's explicit call. A DEAD winner still becomes a live monitor-only book. This
  accumulates one new book per cycle by design, not a rotating slot.
- **The correlation-picked combo competes in that same ranking** — not promoted *in
  addition*. One new book per cycle either way. Combos live in `promoted_combos.json`,
  carrying their legs' full specs so a fresh process can rebuild both signals. Rebalance
  freq is the FINER of the two legs'.

## Live gotchas — check these before assuming something's broken
- **Install BOTH extras: `pip install -e ".[dev,desktop]"`.** `desktop.py` imports
  `webview` *lazily inside main()*, so omitting `[desktop]` leaves
  `import tradefabe.desktop` succeeding and the app dead on launch. Verifying by module
  import will not catch it; `setup_venv.sh` and `build_app.sh` now import `webview`
  explicitly for this reason.
- **Any live paper book needs a persisted backtest curve, or `app.py` crashes with a bare
  `KeyError`.** `book_panel_data()` looks the book up in `piggyback_returns.csv` →
  `factory_returns.csv` → `full_returns.csv`. Only the cycle's promoted winner gets one
  written (bounded growth). **A new source that can become a live book needs its own
  persisted-curve story** or this recurs. Test: `tests/test_book_panel_data.py`.
- **A book's live history must be stamped to the MINUTE, not the date.** Keying on the
  bare date makes the hourly mark overwrite one row per day, leaving charts a single point
  to draw. Any new book source must use `isoformat(timespec="minutes")`, matching
  `books.mark()`. Tests: `test_carry_live_history.py`, `test_live_equity_chart.py`.
- **Live-equity charts scale to the visible data, not to $0.** At $100k start capital a
  $0-anchored axis flattens every real sub-percent move into a straight line. Don't
  "restore" a zero baseline — `drawdown_chart()` is the one chart that legitimately
  anchors at 0.
- **`congress_copy` is verdicted but deliberately has no `graveyard.csv` row.**
  `research/congress_backtest.py` reproduces it (NANC alpha −0.28%/yr, t = −0.12, R² 0.93
  on SPY+QQQ — pure tech beta). It's judged by factor regression, not the doctrine gates,
  so a row would be mostly empty fields pretending to be a gate run.
- **`graveyard.csv` is tracked in git** — it used to be gitignored, which silently
  defeated its own purpose as the multiple-testing record. Don't let it slip back.
- **`tsmom_12m` and `green_line_200d` opening identical-to-the-cent is not a bug.**
  Resolved: `test_tsmom_and_green_line_genuinely_diverge` proves they can disagree; a
  uniform uptrend just happened to agree on sign. Don't re-open without new evidence.
- **iCloud conflict copies (`"<name> 2.<ext>"`)** are guarded three ways now (`.gitignore`,
  a CI step, `tests/test_repo_location.py`) — one such copy of the paper-engine workflow
  once ran as a second live workflow. The guards only hold while the repo stays outside
  `~/Documents`.

## Roadmap
**The Projects board is the source of truth** —
https://github.com/users/dzheng1328/projects/1. Reading it needs a token with the
`project` scope (`gh auth refresh -s project`; plain `repo` is not enough, and the error
message's suggested `read:project` can't write). Don't hand-maintain issue numbers here —
they go stale within a day.

**Currently open: #5 (Alpaca paper integration)** — blocked on Dave's API keys, which an
agent must not handle. Everything else is closed.

**Backfill note:** issues **#41–58** were created 2026-07-25 to record work done before
the tracker existed. They were opened and closed in the same breath. They are history, not
a queue — don't "re-do" one because it looks freshly filed.

## Explicitly off-limits
- `~/Documents/daily tickers` — a separate, unrelated project Dave deliberately stopped.
  Do not integrate, reference, or restart it here without him asking.
- Real trading, real credentials, real transfers — see the hard rule above.
