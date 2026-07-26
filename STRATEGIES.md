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

**Overnight effect (#23, 2026-07-26, `research/overnight_backtest.py`):** **DEAD** — and
the most instructive DEAD in the roster, because the anomaly itself is *real*.

Decomposing 2004–2026 across the 15-ETF universe, gross of costs: **overnight
+8.45%/yr (Sharpe 1.06), intraday +0.01%/yr (Sharpe 0.00)** — the close→open window
accounts for **99%** of the full-day return. The documented effect is not a mirage.

It is also not harvestable. A close-to-open book trades **two sides every session**:
504 sides/yr, which at the engine's 5bps is **25.2%/yr of turnover drag**. Net Sharpe
−2.02 vs +1.05 with costs switched off. Gate 1 passes only because the matched null pays
the same crippling cost — i.e. it beats random twice-daily trading, which is a low bar
when the whole category loses money. Gates 2 and 3 kill it.

**Break-even is 1.72 bps per side.** Below that it makes money; above, it loses. That
number is the honest answer to "your cost assumption is too pessimistic": you would need
sub-2bp execution on both sides, every session, indefinitely.

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

Classic Turtle Trader channel lengths (Faith 2007). ICT/Smart-Money-Concepts were
excluded from the factory's template library because this project's price cache is
Close-only (`engine.load_prices`), and Fair Value Gaps/order blocks/liquidity sweeps all
need High/Low data. They are now tested separately in **family J** off their own hourly
OHLC fetch — not through the factory, which still runs Close-only daily.

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

### J. ICT / Smart-Money-Concepts (edge claimed: institutional order flow leaves readable
footprints — liquidity sweeps, imbalances, structure breaks. #24)

| strategy | spec (mechanical, hourly bars) | freq | status |
|---|---|---|---|
| `ict_fvg` | 3-bar Fair Value Gap: bar1.high < bar3.low (bull) / bar1.low > bar3.high (bear); trade gap direction, hold 6 bars | H | **DEAD** — Sharpe −1.58, worse than the random null's mean; fails all three gates |
| `ict_order_block` | last opposite bar before an impulse > 1.5×ATR that also breaks a 12-bar swing; trade impulse direction, hold 6 | H | **DEAD** — Sharpe −0.64, DSR 0.19 |
| `ict_liquidity_sweep` | pierce a 12-bar swing extreme then close back inside within 3 bars; FADE it, hold 6 | H | **DEAD** — Sharpe −0.03 (best of the four), DSR 0.70 — still short of the 0.95 bar |
| `ict_mss` | market structure shift: close beyond a 12-bar swing pivot; trade break direction, hold 6 | H | **DEAD** — Sharpe −1.04, DSR 0.04 |
| `ict_combo_order_block_liquidity_sweep` | correlation-picked pair (corr −0.05), equal weight | H | **DEAD** — Sharpe −0.38 |
| `ict_all_concepts` | all four equal-weighted, the "mix them all" candidate | H | **DEAD** — Sharpe −1.65 |
| `ict_power_of_3` | Asian/London/NY accumulation-manipulation-distribution | — | **NOT TESTED** — US ETFs trade 09:30–16:00 ET only; the Asian and London sessions do not exist in this data. Left untested rather than faked. |

All six DEAD (`research/ict_backtest.py`, 2026-07-26). The matched null — random entries at
the same trade frequency through the identical hold/cost path — has mean Sharpe **−1.43**,
because costs eat everything absent an edge. Three of the four concepts do not clear even
that. `ict_liquidity_sweep` is the only one near breakeven, and its DSR (0.70) is well
short of the 0.95 bar.

**Power caveat, stated up front:** hourly history is ~2.9 years (2023-08 → 2026-07,
yfinance's free cap) against the roster's 2018+ standard — one macro regime and far fewer
observations. A DEAD verdict here is *weaker* evidence than a DEAD verdict on the daily
roster. It is not, however, evidence of an edge that better data would reveal: the point
estimates are negative, not merely insignificant.

**Evidentiary note:** ICT thresholds come from practitioner folklore, not published
backtests — unlike TSMOM's 12-month lookback (Moskowitz-Ooi-Pedersen 2012) or BAB
(Frazzini-Pedersen 2014). These are one deterministic reading of each concept; a
practitioner would read them discretionarily and might disagree with any specific
threshold. That is exactly why they were pre-registered mechanically and tested rather
than argued about.

### K. Contribution-schedule overlays (edge claimed: hold cash back, deploy it into
drawdowns. Not a signal strategy — it changes WHEN new money arrives, not what you hold. #25)

| strategy | spec | freq | status |
|---|---|---|---|
| `dca_tiered_dipbuy` | 75% of contributions invested monthly; 25% to a reserve at the real T-bill rate; deploy 1× baseline extra at ≥20% off the 252-day high, 2× at ≥30% | M | **DEAD** — loses to plain 100% DCA in **5/5** windows on QQQ and **5/5** on SPY |

`research/dca_backtest.py`, 2026-07-26. Both paths contribute identical dollars on
identical dates, so terminal wealth compares directly.

| window (QQQ) | plain | tiered | gap |
|---|---|---|---|
| full history (2000→) | $3,698,587 | $3,402,422 | **−8.0%** |
| GFC onset (2007→) | $1,570,480 | $1,317,032 | **−16.1%** |
| covid onset (2020→) | $118,329 | $115,935 | −2.0% |
| 2022 bear onset | $66,614 | $62,550 | −6.1% |

**The mechanism is cash drag, and the numbers name it: 83–92% of months sit within 20% of
a 52-week high.** The reserve helps only in the months it deploys and idles the rest of
the time. Windows that *start* at a crash flatter it most — and it still loses all of
them, which is the strongest form of the result: the overlay fails even on the entry
dates chosen to suit it.

**Two things that would have flattered it, avoided:** the reserve earns the actual
13-week T-bill (^IRX), whose mean over this sample is **~2.0%/yr**, not the ~4–5% a
present-day HYSA quote suggests; and the reserve is capped at its balance, so it cannot
deploy money it never had (the ≥30% tier ran dry in 32 months of the QQQ full history).

Source note: the idea came from an Instagram reel whose "grew my portfolio from this to
this" is an unverified before/after graphic and whose "comment stock to see what I'm
buying" is a lead-gen funnel. Neither counts as evidence either way — the mechanic was
tested on its own merits, and it lost.

### L. Intraday / hourly (edge claimed: signals that only exist at sub-daily horizons. #86)

**PRE-REGISTRATION — specs frozen 2026-07-26, before any of the three was run.** Results
land in a separate commit; this one deliberately carries none.

**The regime limitation, accepted up front, doctrine unchanged.** DOCTRINE's OOS window is
2018+. *Every* hourly source reachable here begins in 2023 — Hyperliquid funding
2023-05-12, yfinance 1h equities 2023-08-25, yfinance 1h crypto 2024-07-27 (Binance klines
return HTTP 451 from this location). So these three cannot span 2018's vol spike, COVID, or
the 2022 bear. Sample SIZE is fine (5k–28k observations); regime DIVERSITY is not. Dave's
explicit call (2026-07-26): accept it and label the verdicts regime-limited rather than
amend doctrine to suit the data. **An ALIVE verdict in this family therefore means less
than an ALIVE verdict elsewhere in this file, and must be read with that caveat attached.**

**Evaluation frequency is DAILY, not hourly** — returns are generated hourly, then
aggregated `(1+r).prod()-1` per day before the gates run. This is the same treatment
`carry_hl.py` already gives the surviving carry book (`resample("D").sum()`), and it keeps
`ANN=252`, the 60/40 benchmark, the noise floor, and CPCV all directly comparable to every
other row in this file. The noise floor is matched: 500 random *hourly* strategies pushed
through the identical cost path and the identical daily aggregation, so the null pays the
same turnover drag the candidate does.

| strategy | spec | freq | status |
|---|---|---|---|
| `funding_timing_1h` | delta-neutral BTC+ETH carry, notional scaled by the hourly funding rate: full size when the trailing 24h mean funding is positive, flat when negative | H | **DEAD** — Sharpe 5.37, +6.19%/yr, but **always-on carry over the identical window returns +10.40%/yr at Sharpe 12.42**. The timing overlay destroys 40% of the return and half the Sharpe. Fails gate 2 (Calmar 1.33 vs 15.22) and gate 3 (MaxDD −4.6% vs −0.7%) |
| `crypto_reversal_1h` | fade the trailing 6h return on BTC+ETH, equal weight, long/short | H | **DEAD** — Sharpe −2.94, −70.4%/yr, MaxDD −97.7%. **Turnover drag alone is 173%/yr** (0.400/bar × 8,679 bars/yr × 5bps) |
| `equity_tsmom_1h` | sign of the trailing 24-bar (≈5 session) return on the 15-ETF universe, long/short | H | **DEAD** — Sharpe −1.93, −14.4%/yr, MaxDD −40.7%. Turnover drag 14%/yr |

`research/hourly_backtest.py`, 2026-07-26. Hourly bars are **snapshotted** to
`artifacts/hourly_bars_*.csv` because yfinance's intraday window is a rolling 730 days —
without the snapshot these verdicts could not be reproduced in six months.

**All three now run as LIVE monitor-only paper books** (opened 2026-07-26, Dave's call).
Backtest-DEAD, so under DOCTRINE v1.2 they are monitor-only *forever* and can never become
`paper-confirmed` no matter how the live data looks — identical status to every factory
promotion. Their signals live in `src/tradefabe/hourly.py` and the study **imports them
from there**, so the code that produced the verdicts above and the code running the books
is the same function; two-line signal definitions duplicated across the two is exactly how
a live book silently drifts from the spec it was judged on.
**Cadence caveat:** they were tested on a strict 1h clock, but the engine's tightest loop
is `tradefabe mark` (~2h in practice), so `run_hourly()` rebalances on every mark and the
realised cadence is SLOWER than the tested spec. Live results will diverge from the
backtest for a reason that has nothing to do with whether the edge is real.

**The one-line result: none of the three survives its own turnover.** The two directional
rows lose money outright, and the funding overlay loses to simply holding the position it
was meant to improve.

**Declared deviation from the pre-registration above.** `funding_timing_1h` was
pre-registered to benchmark against CASH. Cash cannot be used: it has zero drawdown, so
`calmar(bench)` is NaN and gate 3 reduces to `MaxDD >= 0`, which no strategy holding any
risk can satisfy. It was benchmarked against **always-on carry** instead — the
economically meaningful question (does timing beat holding?) and *strictly harder* than
cash, since carry earns ~10%/yr and cash earns 0. A deviation that can only make ALIVE
harder to reach is not a thumb on the scale, but it is a deviation and is logged as one.

**Gate 1 is VACUOUS at hourly frequency — read these DSRs as uninformative, not as
passes.** All three cleared gate 1 with DSR 1.000, including the two that lost 70%/yr and
14%/yr. The matched null is the reason: random hourly trading pays so much turnover cost
that its Sharpe is −79.5 / −9.8 / −18.3. "Beats luck" therefore only asks whether a
strategy loses money *more slowly than random churn*, which is nearly free to satisfy.
Gates 2 and 3 did all the work here. **A future hourly candidate that clears gate 1 has
demonstrated almost nothing** — the noise-floor construction in DOCTRINE v1.0.1 was
designed for monthly/weekly/daily rebalancing, where the cost term does not swamp the
signal term. This is a limitation of applying it at high turnover, not a reason to relax
it; the honest fix is to treat gate 2 as the binding constraint in this family and say so.

Parameter choices are pre-committed here and are **not** to be tuned after seeing results —
a different lookback is a NEW row and a NEW graveyard entry (rule 2 below). The three
lookbacks (24h funding mean, 6h reversal, 24-bar trend) were fixed by analogy to the
existing daily specs, not by scanning.

`funding_timing_1h` is a variant of the one ALIVE strategy in this lab, which makes it the
highest-risk row here for exactly the reason DOCTRINE's opening section warns about: tuning
a survivor until it looks better. Its verdict is only meaningful because the spec above was
frozen first. **Benchmark for it is cash** (absolute return), matching `carry_backtest.py`'s
precedent for market-neutral books; the two directional rows are judged against 60/40.

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
