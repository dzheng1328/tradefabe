# tradefabe

A doctrine-governed lab for testing trading strategies honestly, plus a **paper-trading
engine** that runs the survivors as autonomous simulated books. **Paper only — no real
money is connected, and nothing here is investment advice.**

## What this project learned (the short version)
12+ retail strategies tested against pre-registered kill rules: every predictive/copy-based
approach (price patterns, congress-copying, insider-following, thematic picking, candlestick
wicks) came out dead or overfit. Two things survived scrutiny: **diversified buy-and-hold**
and **delta-neutral crypto funding carry** (~12%/yr in the 2023-26 window, paid for bearing
real crypto-infrastructure tail risk). Receipts in `graveyard.csv`, verdicts in
[STRATEGIES.md](STRATEGIES.md), rules in [DOCTRINE.md](DOCTRINE.md).

## Layout
```
src/tradefabe/     the installable engine: engine.py (data/sizing/returns core, single
                   source of truth), signals.py, books.py, carry_live.py, carry_risk.py
                   (funding-flip + liquidation monitor), runner.py, cli.py, desktop.py
app.py             Streamlit dashboard. Two views (sidebar): Paper Books (live books +
                   an interactive per-strategy panel, landing view) and Research Lab
                   (backtest summary). Fully interactive charts (Plotly), not static images.
harness.py         research evaluator: doctrine gates, noise floors, graveyard. Built on
                   the shared src/tradefabe core, not a private copy of the math.
tsmom_backtest.py  standalone TSMOM study + plot, same shared core
combine.py         blending / piggyback experiments
research/          one-off studies (insider, congressional, carry, thematic, day-trading)
tests/             pytest suite, runs in CI on every push/PR (.github/workflows/tests.yml)
artifacts/         generated research outputs (gitignored)
state/paper/       paper-book ledgers + carry_risk.json, written by the runner (gitignored)
```

## Quickstart
```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/tradefabe run       # one daily paper cycle: 5 books + carry risk monitor
.venv/bin/tradefabe status    # current book equities
.venv/bin/streamlit run app.py  # dashboard at localhost:8501

.venv/bin/python harness.py   # re-run the research evaluation (writes artifacts/)
.venv/bin/pytest tests/       # run the test suite
```

The 5 paper books: `tsmom_12m`, `tsmom_ensemble`, `green_line_200d`, `turn_of_month`
(local simulated fills at close, pessimistic costs) and `carry_btc_eth` (accrues **real
Hyperliquid funding** on a delta-neutral notional — when funding goes negative in bear
regimes, the book bleeds; watching that live is the point). The dashboard's carry panel
includes a risk monitor: a trailing 7-day funding-flip alert and a short-leg
liquidation-distance stress table, sized against Hyperliquid's own live margin tiers
(fetched fresh each run, not a hardcoded leverage guess).

A launchd agent (`com.dzheng.tradefabe`) runs `tradefabe run` daily at 18:00 local; logs in
`state/logs/`. Each run marks all books and retargets whichever are due.

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
[Projects board](https://github.com/users/dzheng1328/projects/1). 6 closed (shared
engine core, unit tests + CI, dashboard restructure incl. the paper-vs-backtest
divergence view, carry funding-flip + margin monitor), 4 open (Alpaca paper
integration, a piggyback book, pre-registered promote/kill criteria, a dashboard risk
register panel).
