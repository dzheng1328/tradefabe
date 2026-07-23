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
src/tradefabe/     the installable engine (signals, paper ledgers, live carry, CLI)
app.py             Streamlit dashboard (research results + live paper books)
harness.py         research evaluator: doctrine gates, noise floors, graveyard
tsmom_backtest.py  shared research core (data cache, stats)  [extraction → src/ on roadmap]
combine.py         blending / piggyback experiments
research/          one-off studies (insider, congressional, carry, thematic, day-trading)
artifacts/         generated research outputs (gitignored)
state/paper/       paper-book ledgers written by the runner (gitignored)
```

## Quickstart
```sh
python3 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/tradefabe run       # one daily paper cycle: 5 books (4 equity + live carry)
.venv/bin/tradefabe status    # current book equities
.venv/bin/streamlit run app.py  # dashboard at localhost:8501

.venv/bin/python harness.py   # re-run the research evaluation (writes artifacts/)
```

The 5 paper books: `tsmom_12m`, `tsmom_ensemble`, `green_line_200d`, `turn_of_month`
(local simulated fills at close, pessimistic costs) and `carry_btc_eth` (accrues **real
Hyperliquid funding** on a delta-neutral notional — when funding goes negative in bear
regimes, the book bleeds; watching that live is the point).

Schedule it daily with cron/launchd (see the roadmap issue) — each `tradefabe run` marks
all books and retargets whichever are due.

## Principles
- Strategies are deterministic; **no LLM in the trade loop** (LLMs are for research,
  reporting, and auditing — a nondeterministic trader can't be honestly evaluated).
- Verdicts are out-of-sample, cost-pessimistic, pre-registered; dead strategies stay dead.
- Every strategy ever tested is logged in `graveyard.csv` — the multiple-testing record.

## Roadmap
Tracked as GitHub issues on this repo (milestone **Engine v1**).
