# tradefabe

A doctrine-governed lab for testing trading strategies honestly, plus a **paper-trading
engine** that runs the survivors as autonomous simulated books. **Paper only — no real
money is connected, and nothing here is investment advice.**

## What this project learned (the short version)
49+ strategies tested against pre-registered kill rules — every predictive/copy-based
approach (price patterns, congress-copying, insider-following, thematic picking, candlestick
wicks), plus a growing automated factory of parametrized variants (see below), all came out
dead or overfit. Two things survived scrutiny: **diversified buy-and-hold** and
**delta-neutral crypto funding carry** (~12%/yr in the 2023-26 window, paid for bearing
real crypto-infrastructure tail risk). Being machine-generated isn't a lower bar either —
same doctrine, same kill rules. Receipts in `graveyard.csv`, verdicts in
[STRATEGIES.md](STRATEGIES.md), rules in [DOCTRINE.md](DOCTRINE.md).

## Layout
```
src/tradefabe/     the installable engine: engine.py (data/sizing/returns core, single
                   source of truth), signals.py, books.py, piggyback.py, factory.py
                   (strategy-factory template library + live generation), carry_live.py,
                   carry_risk.py (funding-flip + liquidation monitor), runner.py, cli.py,
                   desktop.py
app.py             Streamlit dashboard. Two views (sidebar): Paper Books (live books
                   grouped by family, click-to-select cards, an interactive per-strategy
                   panel, landing view) and Research Lab (backtest summary, including a
                   detail view for strategies that never made it to a live book). Fully
                   interactive charts (Plotly), not static images.
harness.py         research evaluator: doctrine gates (Deflated Sharpe Ratio + Combinatorial
                   Purged CV as of v1.4), noise floors, graveyard. Built on the shared
                   src/tradefabe core, not a private copy of the math.
tsmom_backtest.py  standalone TSMOM study + plot, same shared core
combine.py         blending / piggyback experiments
research/          one-off studies (insider, congressional, carry, thematic, day-trading),
                   piggyback_backtest.py (combo verdicts), factory_run.py (the strategy
                   factory's daily driver, not yet on a cron)
tests/             pytest suite, runs in CI on every push/PR (.github/workflows/tests.yml)
graveyard.csv      the verdict ledger — every strategy ever evaluated, alive or dead
generated_templates.csv   the strategy factory's own ledger of every live-generated
                   candidate's spec, logged before its verdict is known
artifacts/         generated research outputs (tracked in git)
state/paper/       paper-book ledgers, carry_risk.json, and the factory's promotion
                   registries, written by the runner (gitignored)
```

## Quickstart
```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/tradefabe run       # one daily paper cycle: rebalance due books + carry risk monitor
.venv/bin/tradefabe mark      # mark all books to current price (finer chart resolution)
.venv/bin/tradefabe status    # current book equities
.venv/bin/streamlit run app.py  # dashboard at localhost:8501

.venv/bin/python harness.py   # re-run the research evaluation (writes artifacts/)
.venv/bin/python research/factory_run.py --n 20   # one strategy-factory cycle
.venv/bin/pytest tests/       # run the test suite
```

Paper books currently include `tsmom_12m`, `tsmom_ensemble`, `green_line_200d`,
`turn_of_month` (local simulated fills at close, pessimistic costs), `carry_btc_eth`
(accrues **real Hyperliquid funding** on a delta-neutral notional — when funding goes
negative in bear regimes, the book bleeds; watching that live is the point), plus a
growing set of strategy-factory promotions that accumulate one per daily cycle. The
dashboard's carry panel includes a risk monitor: a trailing 7-day funding-flip alert and
a short-leg liquidation-distance stress table, sized against Hyperliquid's own live
margin tiers (fetched fresh each run, not a hardcoded leverage guess).

Two launchd agents keep the paper engine running unattended: `com.dzheng.tradefabe` runs
`tradefabe run` daily at 18:00 local (the actual rebalance), and
`com.dzheng.tradefabe.mark` runs `tradefabe mark` every 30min so the live-equity chart has
more than one point per day. Logs in `state/logs/`. The strategy factory
(`research/factory_run.py`) isn't on a cron yet — still invoked by hand.

## Desktop app
`~/Applications/tradefabe.app` opens the dashboard in a native window with its own Dock icon
(auto-starts the Streamlit server if needed; closing the window stops a server it started).
Entry point: `tradefabe-app` (pywebview). **Not tracked in git** — hand-built (3 files under
`Contents/`), so if it's ever rebuilt from scratch, recreate it with the launcher exporting
`PYTHONPATH` before it execs `tradefabe-app` (see the gotcha below for why).

> macOS + Python 3.14 gotcha: `site` skips *.pth files carrying the `hidden` flag, which some
> sandboxed installers set — this can recur mid-session, not just after a reinstall. If
> `import tradefabe` fails: `chflags nohidden .venv/lib/python*/site-packages/*.pth`, or more
> reliably, run with `PYTHONPATH=<repo root>/src` set. A venv-level `sitecustomize.py` does
> **not** fix this — Homebrew's own Python ships one earlier on `sys.path` that shadows it.

## Principles
- Strategies are deterministic; **no LLM in the trade loop** (LLMs are for research,
  reporting, and auditing — a nondeterministic trader can't be honestly evaluated).
- Verdicts are out-of-sample, cost-pessimistic, pre-registered; dead strategies stay dead.
- Every strategy ever tested is logged in `graveyard.csv` — the multiple-testing record.

## Roadmap
Tracked as GitHub issues on this repo (milestone **Engine v1**), mirrored on a
[Projects board](https://github.com/users/dzheng1328/projects/1). 13 closed (shared
engine core, unit tests + CI, dashboard restructure around live paper books, carry
funding-flip + margin monitor, promote/kill criteria, and — most recently — the
strategy-factory initiative: DOCTRINE v1.4, the factory itself, auto-promotion, and two
dashboard views for it), 8 open (scheduling the factory via launchd, Alpaca paper
integration, a dashboard risk register panel, and a few backtest candidates still
pending).
