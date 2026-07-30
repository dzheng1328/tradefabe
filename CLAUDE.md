# tradefabe — orientation for agents working in this repo

Read this first. It's the fast path; `README.md` / `DOCTRINE.md` / `STRATEGIES.md` /
`ops/README.md` hold the detail this file only points at.

**This file is loaded into every session and re-injected after every compaction, so its cost
is paid many times per session. Keep it short.** A fixed-and-guarded bug does not belong
here — the guard is the memory. Write the one-line rule and the test that enforces it, not
the post-mortem. Date-stamp any count you add, or it silently goes stale.

## What this is
A doctrine-governed lab that tests trading strategies honestly, plus a paper-trading engine
that runs the survivors as autonomous simulated books. **Paper only.**

**Hard rule, no exceptions without Dave explicitly saying so in chat:** never execute a real
trade, never connect real money/credentials, never give personalized investment advice
(state that boundary instead). Standing constraint, not a per-task one.

**The repo lives at `~/tradefabe`** — moved out of `~/Documents` 2026-07-26 because iCloud
sync corrupted the venv and wrote conflict copies of tracked files. A compatibility symlink
remains at the old path; never point new config at it.

## Git workflow
Branch + PR, one per issue, `gh pr create` with a body giving the change and test plan, merge
after CI is green. Never push to `main`.

**NEVER chain a branch delete after a merge in the same command.** `gh pr merge` fails
quietly on a bad flag or a `state/` conflict, and anything `;`-chained after it still runs —
the delete then CLOSES the unmerged PR, and GitHub will not reopen a PR whose branch is gone.
Cost: three reflog recoveries (#65, #80, #92).

```sh
gh pr merge <N> --squash
gh pr view <N> --json state,mergedAt   # must print MERGED before anything below
git branch -D <b>; git push origin --delete <b>
```
Verify `state=MERGED` as its own step. Never `--delete-branch`, never `&&`/`;` the cleanup on.

**Pass multi-line PR/commit/comment bodies through a heredoc with a QUOTED delimiter**
(`--body-file - <<'EOF'`). These bodies are full of backticks and the shell executes them
inside `"$(cat <<'EOF')"` — it has corrupted a commit message and an issue comment. `<<EOF`
still expands; `<<'EOF'` does not.

## The one-line finding
Every predictive strategy tested is DEAD against pre-registered kill rules — trend,
congress-copy, insider-copy, thematic, day-trading wicks, a pretrained OHLCV foundation
model, and an automated factory of parametrized variants (139 unique strategies in
`graveyard.csv` as of 2026-07-29, 0 ALIVE). Two things survived: diversified buy-and-hold,
and delta-neutral **crypto funding carry** (~12%/yr net 2023–26, paid for bearing real
crypto-infra tail risk). Don't relitigate this; extend it. New candidates go through the same
doctrine — no lower bar because "this one feels different" or "a machine found it".

## Layout — only what `ls` won't tell you
- **`src/tradefabe/engine.py`** is the data/sizing/returns core and the **single source of
  truth**. `harness.py` imports from it; neither keeps a private copy of the math.
- **`hourly.py`** (family L) and **`kronos.py` + `kronos_live.py`** (family M) each hold BOTH
  the signals and the live monitor books, so a study and its book call one function rather
  than two drifting copies. **`kronos.py`'s torch imports are lazy** — importing it proves
  nothing; call `kronos.is_available()`.
- **`app.py`** — Streamlit, port 8501. Plotly only. **No emoji**: Material Symbols
  (`icon=":material/..."`) or the `.tf-badge` component.
- **`tests/`** — pyproject's `pythonpath = [".", "research"]` is what makes `import harness` /
  `import factory_run` resolve under pytest.
- **`graveyard.csv`** — the verdict ledger, every strategy ever evaluated. **Tracked in git**;
  it was once gitignored, defeating its own purpose as the multiple-testing record.
- **`generated_templates.csv`** — the factory's own ledger, each candidate's full spec logged
  at generation time BEFORE its verdict is known.
- **`state/paper/`** — book ledgers, promotion registries. Tracked in git and
  **OWNED BY THE ACTION** — see Automations before writing here locally. `artifacts/` is
  tracked too.

## Commands
```sh
ops/setup_venv.sh                   # rebuild the venv (refuses to build inside a synced tree)
.venv/bin/pip install -e ".[dev,desktop]"   # BOTH extras — see the pywebview trap below
.venv/bin/tradefabe run             # one daily cycle: rebalance due books, carry, risk monitor
.venv/bin/tradefabe mark            # mark to current price, no rebalance
.venv/bin/tradefabe status          # current book equities
.venv/bin/tradefabe reset           # wipe paper state, restart at $100k/book
.venv/bin/tradefabe retire <book> --reason "..."   # freeze a book; DAVE ONLY, see Doctrine
.venv/bin/tradefabe unretire <book>
.venv/bin/streamlit run app.py      # dashboard at localhost:8501
.venv/bin/python harness.py         # re-run doctrine evaluation, APPENDS graveyard.csv
.venv/bin/pytest tests/             # parallel by default (433 tests, ~8s); also runs in CI
.venv/bin/pytest tests/ -n0         # serial — for readable tracebacks / --pdb / -x
PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" \
  .venv/bin/python research/factory_run.py --n 20   # one factory cycle by hand
```
`PYTHONPATH` is needed only for that last line (`factory_run.py` imports the repo-root
`harness` and `research/piggyback_backtest`, which only pytest resolves for you).

Anything that appends to `graveyard.csv` writes a permanent multiple-testing record. **One
verdict per spec** (roster rule 2) — re-running a judge duplicates rows and inflates
`n_tested` for every later candidate. `kronos_backtest.py --curves-only` exists for exactly
this reason: regenerate artifacts without re-recording a verdict.

## Automations — what runs without you
Know these before assuming a file changed by magic.

**Scheduled** (`.github/workflows/paper-engine.yml`) — **the paper engine runs in the cloud,
not on the Mac** (launchd didn't fire while the machine slept). **The Action is the SOLE
OWNER of `state/`**: it commits the ledger every cycle, so `git pull` before reading the
dashboard locally, and don't commit local `state/` writes. The `ops/*.plist` files still
exist but nothing is `launchctl load`ed — that, not a rename, is the only thing stopping a
second writer from forking the ledger. Check `launchctl list | grep tradefabe` is empty.
- **mark** — hourly (best-effort; GitHub often spaces these ~2h apart).
- **run** — daily 22:00 UTC. Installs the CPU torch wheel and caches the Kronos weights;
  the mark job does neither.
- **factory** — **PAUSED since 2026-07-27 (#98).** The cron is commented out, not deleted;
  `workflow_dispatch` still works. It promoted its best-DSR candidate every cycle regardless
  of verdict, so finding something and finding nothing produced the same outcome (another
  monitor-only book) while every draw raised `family_n_tested()` for all future candidates.

By hand: `gh workflow run "paper engine" -f job=mark|run|factory`. GitHub disables schedules
on repos with no *human* activity for ~60 days and the bot's own commits may not count —
check that first if the schedule goes quiet.

**CI** (`.github/workflows/tests.yml`) — `pytest tests/`. **Trigger is push/PR on `main`
ONLY.** A PR onto any other branch gets no checks; `gh pr checks` says "no checks reported",
which reads like failure but means the workflow never fired. Also confirm the green check is
for the CURRENT head — compare `gh run view <id> --json headSha` against `git rev-parse HEAD`,
because `--watch` can return a pass from an earlier push.

**In-process** (inside the scheduled jobs, so invisible in `launchctl list`). All never raise
— a data outage on a monitor book must not take down the cycle that owns the real ledger.
- **`run_hourly()`** (`hourly.py`) — family L's three monitor-only books (#86). Called by
  `run_daily()` AND `run_mark()`, and **rebalances on every mark**, unlike every other book.
  Tested on a strict 1h clock; the ~2h mark cadence is the closest the engine gets, so **live
  diverges from backtest for reasons unrelated to whether the edge is real.** All backtest-
  DEAD, hence monitor-only forever under v1.2.
- **`run_kronos()`** (`kronos_live.py`) — family M's two live monitor books (#126). Called by
  `run_daily()` **only**: they're freq D, so a mark has nothing to forecast and would pay the
  torch + 400MB-checkpoint cost ~12x/day for nothing. Skips silently without the `[kronos]`
  extra. Appends every live forecast to the same `artifacts/kronos_forecasts.csv` the
  verdicts came from — stochastic sampling means an unsnapshotted position can't be audited.
- **`run_carry()`** — accrues real Hyperliquid funding. Called by both, so it stamps a
  minute-resolution row ~48x/day.
- **`check_carry_risk()`** — funding-flip + liquidation distance, `run_daily()` **only**, so
  `carry_risk.json` lagging by up to a day is expected; the dashboard prints `generated_at`.
- **Factory auto-promotion** — writes `state/paper/promoted*.json`, which `runner.py` reads
  at **import time**, so a promotion only takes effect in the next process. (Idle while the
  factory is paused.)

**Dev config** — `.claude/settings.json` (tracked; lets agents run `gh`/`git` unprompted,
denies `gh repo delete` and force-push) and `.claude/launch.json`.
`.claude/settings.local.json` is Dave's gitignored overlay.

**Desktop app** (user-launched): `~/Applications/tradefabe.app`, rebuilt with
`ops/build_app.sh`. The bundle isn't in git; its build script is.

## Doctrine — read DOCTRINE.md before adding or judging any strategy
Pre-registered, OOS-only, data-derived noise floor (500 random strategies per freq), fair
60/40 benchmark, three kill gates (beat luck / earn your place / not more painful). `OOS_START`
is 2018 for every family except M, whose window starts at its model's pretraining cutoff.

- **Gate 1 decides on Deflated Sharpe Ratio + CPCV** (`harness.deflated_sharpe_ratio()`,
  v1.4). Bonferroni is still computed and logged for continuity but decides nothing.
- **v1.2 — paper promote/kill.** A backtest-DEAD book is **monitor-only forever, never
  `paper-confirmed`**, no matter how good its paper data looks.
- **v1.5 — CURRENT since 2026-07-29** (#112/#120). `n_tested` is segregated by origin so
  factory draws stop inflating the bar for hand-picked candidates (23 vs 139 on family M),
  and the duty-cycle-matched null is the default. **Forward-only**: no historical verdict is
  ever re-scored, so the `n_tested` column is **discontinuous at 2026-07-29**.
- **v1.6 — retiring a paper book is Dave's decision alone** (#113). No performance trigger,
  no drawdown threshold, no age rule; v1.2's kill criteria are **advisory findings, never
  actions**. Auto-killing losers would filter the forward record on results — manufacturing
  survivorship bias in the one dataset here that has none. Retired = frozen (no rebalance, no
  mark; history, `summary.csv` row and dashboard card preserved). **Never add an automatic
  path**: `tests/test_retirement.py` fails from two directions if you do.
- A v1.1 touching gate 2 (diversifier clause) was discussed and is **not approved**.

Roster, evidence, and family taxonomy: `STRATEGIES.md`. Add new candidates there *before*
running them — including the factory's `GENERATION_RANGES` (the range is the
pre-registration; the drawn value is logged to `generated_templates.csv`).

## Strategy factory — currently PAUSED (#98), still doctrine-gated when run
`src/tradefabe/factory.py` + `research/factory_run.py` test ~20 candidates per cycle through
the same DSR/CPCV gate.
- **Live generation is deliberately NOT free-form.** Only the parameter RANGE per family is
  fixed in code (reviewed once); the drawn value is logged **before** its verdict is known —
  the fix for the meta-level p-hacking risk DOCTRINE.md warns about.
- **Promotion picks the single best-DSR candidate per cycle regardless of verdict** — Dave's
  explicit call. A DEAD winner still becomes a live monitor-only book, one per cycle by
  design, not a rotating slot. This unbounded accumulation is what #98 paused it over.
- **The correlation-picked combo competes in that same ranking**, not promoted in addition.
  Combos live in `promoted_combos.json` carrying their legs' full specs so a fresh process
  can rebuild both signals; rebalance freq is the FINER of the two legs'.

## Live gotchas — check these before assuming something's broken
- **yfinance returns a PARTIAL trailing bar** for the current, still-open or non-trading day:
  the row exists, some tickers are NaN. `engine.drop_incomplete_tail()` trims it. **It cannot
  catch a 24/7 asset** — crypto's in-progress UTC day has all five columns populated, so
  `kronos_live.drop_current_day()` handles that separately. NaN also slips past naive guards
  (`nan or 0` is `nan`; `nan <= 0` is `False`), so `books.mark()` / `rebalance_to()` check
  `math.isfinite` and skip-and-warn rather than write. **A NaN in the ledger is permanent.**
  Tests: `test_nan_marks.py`, `test_kronos_live.py`.
- **The price cache expires after 12h** (`TRADEFABE_CACHE_HOURS`). Offline, a stale cache
  beats synthetic — real-but-old over invented.
- **Install BOTH extras: `pip install -e ".[dev,desktop]"`.** `desktop.py` imports `webview`
  *lazily inside main()*, so omitting `[desktop]` leaves the import succeeding and the app
  dead on launch. A module-import check will not catch it; `setup_venv.sh` and
  `build_app.sh` import `webview` explicitly for this reason. Same shape as `kronos.py`.
- **Any live paper book needs a persisted backtest curve, or `app.py` dies on a bare
  `KeyError`.** `book_panel_data()` resolves `piggyback_returns.csv` → `factory_returns.csv`
  → `hourly_returns.csv` → `kronos_returns.csv` → `full_returns.csv`. **A new source that can
  become a live book needs its own persisted-curve story, wired into the Paper Books lookup
  AND the Research Lab's `_dead_strategy_returns()`** — doing one only is the actual
  2026-07-26 outage. Tests: `test_book_panel_data.py`, `test_kronos_live.py`.
- **A book's live history must be stamped to the MINUTE, not the date.** A bare date makes
  the hourly mark overwrite one row per day, leaving charts a single point, and sorts to
  midnight. Use `isoformat(timespec="minutes")`, matching `books.mark()`. Tests:
  `test_carry_live_history.py`, `test_live_equity_chart.py`.
- **Live-equity charts scale to the visible data, not to $0.** At $100k start capital a
  $0-anchored axis flattens every sub-percent move into a straight line. Don't "restore" a
  zero baseline; `drawdown_chart()` is the one chart that legitimately anchors at 0.
- **`congress_copy` is verdicted but deliberately has NO `graveyard.csv` row.**
  `research/congress_backtest.py` reproduces it (NANC alpha −0.28%/yr, t = −0.12, R² 0.93 on
  SPY+QQQ — pure tech beta). Judged by factor regression, not the gates, so a row would be
  mostly empty fields pretending to be a gate run.
- **`tsmom_12m` and `green_line_200d` opening identical-to-the-cent is not a bug** — a
  uniform uptrend agreed on sign. `test_tsmom_and_green_line_genuinely_diverge` settles it;
  don't re-open without new evidence.
- **iCloud conflict copies (`"<name> 2.<ext>"`)** are guarded by `.gitignore`, a CI step and
  `tests/test_repo_location.py` — one such copy of the paper-engine workflow once ran as a
  second live workflow. The guards hold only while the repo stays outside `~/Documents`.

## Roadmap
**`gh issue list` is authoritative. The board is a lagging VIEW** —
https://github.com/users/dzheng1328/projects/1. When they disagree, the issues win. It has
drifted 13 issues behind before (#117 backfilled it) and will again, because keeping it
current is a manual step — step 7 of the `ship` skill. Reading it needs `project` scope
(`gh auth refresh -s project`; plain `repo` is not enough, and `read:project` can't write).

**Don't hand-maintain issue numbers or counts in this file** — they go stale within a day,
and a stale roadmap once convinced an agent the lab had been idle for a week. Run the command.

**Backfill note:** issues **#41–58** were created 2026-07-25 to record work predating the
tracker; opened and closed in the same breath. History, not a queue.

## Explicitly off-limits
- `~/Documents/daily tickers` — a separate project Dave deliberately stopped. Don't
  integrate, reference, or restart it here without him asking.
- Real trading, real credentials, real transfers — see the hard rule above.
