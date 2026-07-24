# Strategy Roster

Every candidate is **pre-registered** here (signal + rebalance frequency) before its
out-of-sample verdict is rendered. The graveyard logs every attempt — the count *is* the
multiple-testing record. Pipeline for every strategy, no exceptions:

> **Stage 1** historical backtest vs DOCTRINE → **Stage 2** forward paper-trading (Alpaca,
> autonomous) → **Stage 3** real money (never without an explicit human decision).

## Families — deliberately different edge sources

### A. Trend / momentum (edge: gradual underreaction to news)
| strategy | spec | freq | status |
|---|---|---|---|
| `tsmom_12m` | sign of trailing 12-mo return | M | TESTED |
| `tsmom_ensemble` | blend of 3/6/12-mo trend | M | TESTED |
| `xsec_momentum` | long 12-mo winners, short losers | M | TESTED |
| `green_line_200d` | long above 200-day MA, short below | M | TESTED |

### B. Mean reversion (edge: short-horizon overreaction — the *opposite* bet to A)
| strategy | spec | freq | status |
|---|---|---|---|
| `str_reversal_5d` | fade the trailing 5-day move | W | TESTED |
| pairs / cointegration | Engle-Granger pair spread z-score | D | QUEUED — needs pair-scan infra |

### C. Calendar / seasonality (edge: structural flow patterns, not prediction)
| strategy | spec | freq | status |
|---|---|---|---|
| `turn_of_month` | long all assets, last 4 + first 3 trading days | D | TESTED |
| overnight effect | hold close→open only | D | QUEUED — needs Open prices in cache |

### D. Defensive anomaly (edge: leverage-constrained investors overpay for volatility)
| strategy | spec | freq | status |
|---|---|---|---|
| `low_vol_xsec` | long calmer half of universe, short wilder half (BAB-lite) | M | TESTED |

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
lost to random stock-picking from the same pool. Backtests: `insider_backtest.py`, NANC/KRUZ/KNOW
regression above. Survivorship (145 delisted names dropped) biased insider results UP, and it still died.

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
