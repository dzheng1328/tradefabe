# tradefabe

An honest lab for testing algorithmic trading strategies in **paper only** — built to *kill*
bad strategies fast, not to flatter them.

## Why
Most retail trading bots get backtested until they look good, then lose money live. This
project inverts that: the goal is a "verdict machine" that refuses to lie to you. The
evaluation rules are locked in [DOCTRINE.md](DOCTRINE.md).

## Layout
- `tsmom_backtest.py` — first-slice standalone backtest (cross-asset 12-month time-series momentum).
- `harness.py` — reusable evaluator enforcing the doctrine (data-derived noise floor, fair 60/40 benchmark, kill rule, graveyard log).
- `DOCTRINE.md` — the frozen, pre-registered evaluation rules.
- `graveyard.csv` — ledger of every strategy tested + its verdict (generated).

## Run
```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python harness.py
```

## Principles
- Strategies are **deterministic**; the LLM is for research/monitoring/reporting, never live entries.
- Verdicts are **out-of-sample only**; costs charged pessimistically; **no tuning to pass**.
- Every result — alive or dead — is logged. One death is data, not failure.
