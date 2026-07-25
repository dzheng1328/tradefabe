# Strategy Roster

Every candidate is **pre-registered** here (signal + rebalance frequency) before its
out-of-sample verdict is rendered. The graveyard logs every attempt — the count *is* the
multiple-testing record. Pipeline for every strategy, no exceptions:

> **Stage 1** historical backtest vs DOCTRINE → **Stage 2** forward paper-trading (Alpaca,
> autonomous) → **Stage 3** real money (never without an explicit human decision).

**The strategy factory (#28, `src/tradefabe/factory.py` + `research/factory_run.py`).**
Rather than one candidate at a time by hand, `factory.TEMPLATES` is a pre-registered
library of parametrized signal generators — new lookback/window variants of families
already below, plus new family I — each with its own one-line economic rationale (same
bar as the rest of this roster). `factory_run.py` draws a bounded batch per cycle
(20/day as of #28b), runs every candidate through the identical doctrine gate (DOCTRINE
v1.4, no lighter bar for being machine-generated), and — since blind full enumeration
would inflate `n_tested` for no reason — picks the single least-correlated pair among
that cycle's candidates for one piggyback-style construction, rather than testing every
subset. The rows below ARE the pre-registration: the template's parameters are frozen in
`factory.py` before any candidate drawn from it is evaluated, exactly like a hand-picked
strategy's spec is frozen here before its verdict.

**Live generation (#28b, once `TEMPLATES` runs dry — which it does immediately at 20/day).**
Rather than cap the factory at a fixed list, `factory.GENERATION_RANGES` pre-registers a
*parameter range* per family (fixed here, reviewed once — e.g. family A: any trend
lookback from 10 to 504 days), and the SPECIFIC value is drawn fresh each cycle. This is
the compromise for "don't limit the search to 15 templates" that doesn't reopen the
meta-level p-hacking DOCTRINE.md's own opening section warns against: every draw is
logged to `generated_templates.csv` (git-tracked, append-only) **at generation time,
before its verdict is known** — the same "the count IS the record" principle
`graveyard.csv` already embodies, extended to the generation process itself. A generated
candidate that wins a cycle (see Promotion below) is named `<family>_gen_<params>` in
`graveyard.csv`/the dashboard, e.g. `tsmom_gen_147d`.

**Promotion (#28b, supersedes an earlier #29 rule).** The single best-DSR candidate each
cycle is promoted to a live paper book **regardless of verdict** — Dave's explicit call:
more live paper-tracked data is worth having even when the backtest says DEAD, as long
as it's honestly labeled. A promoted DEAD candidate is monitor-only, same status
DOCTRINE v1.2 already gives backtest-DEAD hand-picked books kept live for research
value. This accumulates one new book per cycle (Dave's explicit choice over a single
rotating "champion" slot) — expect the live roster to grow steadily, not just on the
rare cycle that finds a real winner.

## Families — deliberately different edge sources

### A. Trend / momentum (edge: gradual underreaction to news)
| strategy | spec | freq | status |
|---|---|---|---|
| `tsmom_12m` | sign of trailing 12-mo return | M | TESTED |
| `tsmom_ensemble` | blend of 3/6/12-mo trend | M | TESTED |
| `xsec_momentum` | long 12-mo winners, short losers | M | TESTED |
| `green_line_200d` | long above 200-day MA, short below | M | TESTED |
| `tsmom_3m` (factory) | sign of trailing 3-mo return | M | **DEAD** — DSR 0.23 |
| `tsmom_6m` (factory) | sign of trailing 6-mo return | M | **DEAD** — DSR 0.25 |
| `tsmom_9m` (factory) | sign of trailing 9-mo return | M | **DEAD** — DSR 0.50 |
| `tsmom_18m` (factory) | sign of trailing 18-mo return | M | **DEAD** — DSR 0.62 |
| `tsmom_24m` (factory) | sign of trailing 24-mo return | M | **DEAD** — DSR 0.48 |

### B. Mean reversion (edge: short-horizon overreaction — the *opposite* bet to A)
| strategy | spec | freq | status |
|---|---|---|---|
| `str_reversal_5d` | fade the trailing 5-day move | W | TESTED |
| `str_reversal_3d` (factory) | fade the trailing 3-day move | W | **DEAD** — DSR 0.00 |
| `str_reversal_10d` (factory) | fade the trailing 10-day move | W | **DEAD** — DSR 0.04 |
| `str_reversal_15d` (factory) | fade the trailing 15-day move | W | **DEAD** — DSR 0.10 |
| `str_reversal_20d` (factory) | fade the trailing 20-day move | W | **DEAD** — DSR 0.13 |
| pairs / cointegration | Engle-Granger pair spread z-score | D | QUEUED — needs pair-scan infra |

### C. Calendar / seasonality (edge: structural flow patterns, not prediction)
| strategy | spec | freq | status |
|---|---|---|---|
| `turn_of_month` | long all assets, last 4 + first 3 trading days | D | TESTED |
| `turn_of_month_narrow` (factory) | long all assets, last 2 + first 2 trading days | D | **DEAD** — clears DSR (1.00) but fails gate 2 (Calmar 0.06 vs bench 0.45) |
| `turn_of_month_wide` (factory) | long all assets, last 5 + first 5 trading days | D | **DEAD** — clears DSR (1.00) but fails gate 2 (Calmar 0.18 vs bench 0.45) |
| overnight effect | hold close→open only | D | QUEUED — needs Open prices in cache |

### D. Defensive anomaly (edge: leverage-constrained investors overpay for volatility)
| strategy | spec | freq | status |
|---|---|---|---|
| `low_vol_xsec` | long calmer half of universe, short wilder half (BAB-lite) | M | TESTED |
| `low_vol_xsec_30d` (factory) | same split, 30-day vol window (vs 60-day) | M | **DEAD** — DSR 0.01 |
| `low_vol_xsec_120d` (factory) | same split, 120-day vol window (vs 60-day) | M | **DEAD** — DSR 0.03 |

### E. Carry / structural (edge: get PAID a flow, no prediction needed)
| strategy | spec | freq | status |
|---|---|---|---|
| crypto funding/basis carry | long spot + short perp, collect funding | D | **REAL — the only survivor.** Hyperliquid 2023-26: ~12%/yr net, market-neutral, +1.3% through a −53% BTC crash, funding+ 88% of days. Caveats: backtest CANNOT see the fat tail (FTX-style counterparty collapse, stablecoin depeg); window excludes 2022/FTX; the yield is pay for bearing crypto-infra risk. See `carry_hl.py` |
| FX carry | long high-yield ccy ETFs vs low | M | QUEUED — needs rate data |

### F. Volatility risk premium (edge: implied > realized on average)
| strategy | spec | freq | status |
|---|---|---|---|
| VRP via defined-risk structures | short vol with hard caps | W | QUEUED — tail-risk design required first; -800% tail events documented |

### G. Information / signal-following (edge: copy legally-disclosed informed traders)
| strategy | spec | freq | status |
|---|---|---|---|
| `congress_copy` | mirror congressional purchases after 45-day disclosure | — | **DEAD** — NANC proxy alpha −0.4%/yr after SPY+QQQ beta (pure tech beta); Ziobrowski's +12% is pre-STOCK-Act; raw trade data locked (403) |
| `insider_buying` | buy on Form-4 open-market purchases (≥$100k), hold 21d | D | **DEAD** — trade-level backtest on 83k purchases: 3.2% CAGR / Sharpe 0.48, *below* the random-ticker luck floor (0.70) and far below SPY (0.84) |

Both DEAD. Congressional "outperformance" is stale + now just tech beta. Insider-buying's real
edge lives in illiquid microcaps where spreads/impact eat it; the tradeable slice has no edge and
lost to random stock-picking from the same pool. Backtests: `insider_backtest.py`, `congress_backtest.py`
(NANC/KRUZ/KNOW alpha vs SPY+QQQ). Survivorship (145 delisted names dropped) biased insider results UP, and it still died.

### H. Piggyback / combined constructions (edge: a standalone-DEAD strategy can still earn
its place as a diversifying sleeve on the passive core — see `combine.py`, doctrine's
"earns its place" gate 2 applied to a construction rather than a bare bet)

Fixed **30% sleeve** (`SLEEVE`, pre-committed, not optimized) of an equal-weight blend of
the named legs, on top of a **70% 60/40 core**, monthly rebalance. All 4 legs drawn from
Families A/C/D's already-DEAD strategies (#7). Sleeve composition chosen from a full
`itertools.combinations` search over all 7 DEAD equity candidates at depths 2/3/4,
ranked by piggyback Sharpe/Calmar and checked against a matched-blend luck floor per
depth — the search and its output are the pre-registration record for *why* these 4 and
not some other 4, per graphify session 2026-07-23. Frozen before the formal doctrine
verdict in `research/piggyback_backtest.py` / `graveyard.csv` was run.

| strategy | spec | freq | status |
|---|---|---|---|
| `piggyback_2a` | 70% 60/40 + 30% (`tsmom_12m` + `low_vol_xsec`) | M | **DEAD (corrected, v1.3)** — was ALIVE vs the uncorrected p95 matched floor (Sharpe 0.89 > 0.87); at the honest Bonferroni bar for N=12 (normal-approx, p99.58 → 0.90) it no longer clears gate 1 |
| `piggyback_2b` | 70% 60/40 + 30% (`low_vol_xsec` + `turn_of_month`) | M | **DEAD** — DEAD even before correction (tied the uncorrected floor); stays DEAD, corrected bar only widens the gap |
| `piggyback_3` | 70% 60/40 + 30% (`tsmom_12m` + `green_line_200d` + `low_vol_xsec`) | M | **DEAD (corrected, v1.3)** — was ALIVE (best Calmar of all 4, 0.52); corrected bar (0.89) exceeds its Sharpe (0.885) |
| `piggyback_4` | 70% 60/40 + 30% (`tsmom_12m` + `xsec_momentum` + `green_line_200d` + `low_vol_xsec`) | M | **DEAD (corrected, v1.3)** — was ALIVE; corrected bar (0.89) exceeds its Sharpe (0.881) |

**Why the correction bites so hard here, structurally, not just numerically:** every
piggyback already holds 70% of the benchmark by construction, so a RANDOM sleeve's
matched-null Sharpe clusters tightly around the benchmark's own 0.85 (std ≈ 0.03 across
150 trials, skew < 0.25 — a normal-approximation fallback is justified, not a fluke of
too few trials). There's very little room between "random sleeve" and "real sleeve" for
this construction shape to clear a properly corrected bar, regardless of which legs are
picked. `low_vol_xsec` still appears in every top-Sharpe pick from the original search
(DEAD standalone, Sharpe −0.03, but negatively correlated with nearly everything else in
the roster) — that correlation-structure finding stands; what changed is whether ANY
piggyback construction can statistically prove it beats a random one once multiple
testing is honestly priced in. Verdicts: `graveyard.csv` (original + corrected rows,
both kept — append-only ledger), `research/piggyback_backtest.py`.

### I. Breakout / channel (edge: react to a price EXTREME, not an average — a distinct
mechanism from family A's moving-average trend, added by the strategy factory, #28)

| strategy | spec | freq | status |
|---|---|---|---|
| `donchian_20d` (factory) | long a new 20-day high, short a new 20-day low | D | **DEAD** — clears DSR (1.00) but fails gate 2 (Calmar −0.08 vs bench 0.45) |
| `donchian_55d` (factory) | long a new 55-day high, short a new 55-day low | D | **DEAD** — clears DSR (1.00) but fails gate 2 (Calmar −0.11 vs bench 0.45) |

Classic Turtle Trader channel lengths (Faith 2007). ICT/Smart-Money-Concepts (#24) were
considered for this slot and deliberately excluded from the factory's template library:
this project's price cache is Close-only (`engine.load_prices`), and Fair Value Gaps/
order blocks/liquidity sweeps all need High/Low (or intraday) data this repo doesn't
fetch yet — faking them off Close-only data would mislabel an arbitrary heuristic as an
ICT concept. #24 remains its own issue, blocked on the same class of data gap for a
different reason (2yr-hourly recency).

**First factory cycle (2026-07-25, seed 20260725):** drew all 15 templates + one
correlation-picked combo (`str_reversal_15d` + `tsmom_6m`, corr −0.00 — genuinely
uncorrelated, not just low). **All 16 DEAD**, `n_tested` 27→28. The daily-rebalanced
calendar/breakout variants (`turn_of_month_narrow/wide`, `donchian_20d/55d`) all clear
DSR outright (1.00 — an artifact of the D-frequency noise floor's own SR* sitting deeply
negative, same shape as the existing `turn_of_month` row) but every one fails gate 2 on
Calmar, same failure mode as their already-tested siblings. No parameter variant of an
already-DEAD family manufactured a new edge — consistent with this roster's whole
track record, and exactly what a working multiple-testing correction should look like:
volume alone doesn't buy a pass.

## Rules of the roster
1. A strategy's spec (signal, universe, freq) is frozen **before** its OOS verdict.
2. One verdict per spec. Tweaks = a NEW row and a NEW graveyard entry.
3. Families are chosen to be **mutually uncorrelated bets** — trend vs reversal vs calendar
   vs defensive vs carry. Correlation matrix in the dashboard is the check.
4. DEAD standalone ≠ useless: low-corr sleeves may still earn a place as piggyback
   diversifiers on the 60/40 core (see combine.py / dashboard Piggyback Lab).

## Key evidence (gathered in research sessions)
- TSMOM: Moskowitz–Ooi–Pedersen 2012, ~1.0 Sharpe across 58 futures pre-costs (AQR/Quantpedia).
- Turn-of-month: documented since Lakonishok & Smidt 1988; still debated post-1990s (Quantpedia, QuantSeeker).
- Short-term reversal / RSI(2): Connors; SPY 1993– ~9%/yr while invested 28% of time (QuantifiedStrategies).
- Low-vol / BAB: Frazzini–Pedersen 2014, Sharpe ~0.78, ~2x US market (NBER).
- Funding carry: 8–20% APY documented in calm regimes, delta-neutral (multiple 2025–26 sources).
- Retail overfitting: backtest Sharpe explains <3% of live results; more tweaking widens the gap.
