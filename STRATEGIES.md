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
| crypto funding/basis carry | long spot + short perp, collect funding | D | QUEUED — needs perp data + separate engine. **Top candidate for the raw-profit goal.** |
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
