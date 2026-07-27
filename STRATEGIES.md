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

**Declared deviation from the pre-registration above — and this row's DEAD verdict is
BENCHMARK-DEPENDENT.** `funding_timing_1h` was pre-registered against CASH. Cash cannot be
used: it has zero drawdown, so `calmar(bench)` is NaN and gate 3 reduces to `MaxDD >= 0` —
gates 2 and 3 are **unpassable by construction** for anything holding risk. It was
benchmarked against **always-on carry** instead: the economically meaningful question
(does timing beat holding?) and the hardest non-degenerate benchmark available.

The honest accounting, which an earlier version of this section got wrong by claiming the
substitution "can only make ALIVE harder":

| benchmark | gate 2 | gate 3 | verdict |
|---|---|---|---|
| cash (pre-registered) | False (NaN) | False | DEAD — degenerate, unpassable by construction |
| **always-on carry (used)** | **False** (Calmar 1.33 vs 15.22) | **False** (MaxDD −4.6% vs −0.7%) | **DEAD** |
| 60/40 (this family's default) | True (Calmar 1.33 vs 1.02) | True (−4.6% vs −17.0%) | **ALIVE** |

Cash made ALIVE *impossible*, so substituting anything at all made it **possible** — that
is looser, not stricter. What defends the choice is not the direction of the deviation but
that always-on carry is **strictly harder than the 60/40 this family uses for its other two
rows**, and that under 60/40 this row would have been ALIVE. Stating that last clause is
the point: the DEAD verdict here depends on the benchmark, and a reader is entitled to know
which one was picked and what the alternative would have said.

**The conclusion that survives every benchmark quibble:** with costs switched OFF, the
overlay scores Sharpe 5.37 against a random on/off timing null averaging **12.11**. Random
timing beats it before costs. No choice of benchmark rescues that.

**Gate 1 is VACUOUS at hourly frequency — read these DSRs as uninformative, not as
passes.** All three cleared gate 1 with DSR 1.000, including the two that lost 70%/yr and
14%/yr. The matched null is the reason: random hourly trading pays so much turnover cost
that its Sharpe is −79.5 / −9.8 / −18.3. "Beats luck" therefore only asks whether a
strategy loses money *more slowly than random churn*, which is nearly free to satisfy.

The precise defect is that the null is matched on **frequency but not on turnover** — it
trades far more than the candidates do:

| | candidate turnover | null turnover | ratio |
|---|---|---|---|
| `crypto_reversal_1h` | 0.400/bar | 1.278/bar | 3.2× |
| `equity_tsmom_1h` | 0.161/bar | 1.391/bar | 8.7× |
| `funding_timing_1h` | 0.0074 flips/bar | 0.5007 flips/bar | **68×** |

So gate 1's entire bar is a cost differential, not a signal comparison. Switch costs off and
the nulls score +12.11 / +0.04 / −0.02 — at which point none of the three candidates clears
anything. Gates 2 and 3 did all the real work.

**A future hourly candidate that clears gate 1 has demonstrated almost nothing.** The
noise-floor construction in DOCTRINE v1.0.1 was designed for monthly/weekly/daily
rebalancing, where the cost term does not swamp the signal term. This is a limitation of
applying it at high turnover, not a reason to relax it. **The owed fix, before any further
hourly candidate is judged: match the null's DUTY CYCLE to the candidate's, not just its
clock.** Until then, treat gate 2 as the binding constraint in this family and say so.

Parameter choices are pre-committed here and are **not** to be tuned after seeing results —
a different lookback is a NEW row and a NEW graveyard entry (rule 2 below). The three
lookbacks (24h funding mean, 6h reversal, 24-bar trend) were fixed by analogy to the
existing daily specs, not by scanning.

`funding_timing_1h` is a variant of the one ALIVE strategy in this lab, which makes it the
highest-risk row here for exactly the reason DOCTRINE's opening section warns about: tuning
a survivor until it looks better. Its verdict is only meaningful because the spec above was
frozen first. **Benchmark for it is cash** (absolute return), matching `carry_backtest.py`'s
precedent for market-neutral books; the two directional rows are judged against 60/40.

### M. Learned forecaster / Kronos (edge claimed: a pretrained sequence model extracts
structure from raw OHLCV that hand-written signals miss. #105)

**PRE-REGISTRATION — specs frozen 2026-07-26, before any of the three was run.** Results
land in a separate commit; this one deliberately carries none.

**The model.** [Kronos](https://github.com/shiyu-coder/Kronos) (AAAI 2026, MIT licence) is
a decoder-only transformer over hierarchically-tokenized OHLCV K-lines, pretrained
autoregressively on 12B bars from 45 exchanges. We use `Kronos-base` (102.3M params) with
`Kronos-Tokenizer-base` — the largest *open* checkpoint; `Kronos-large` (499.2M) is not
released. Base weights are **frozen**: this family tunes inference knobs only. Fine-tuning
is deliberately out of scope because it does not fix the contamination below — the base
weights already saw 2018–2025 regardless of what we fine-tune on afterwards.

Kronos forecasts **full OHLCV**, not just close. That is the one capability no other signal
in this roster has, and `kronos_wick_agg` exists specifically to use it; a family that only
consumed the forecast close would be a worse-tested version of family A.

#### Declared deviation 1: this family's OOS window is not 2018

DOCTRINE's `OOS_START` is 2018-01-01. **That window is contaminated for this family** and
cannot be used. Kronos's pretraining corpus ends at approximately **2025-06-05** — inferred
from the authors' own `finetune/config.py` (`dataset_end_time = '2025-06-05'`, and a
`test_time_range` closing the same day), corroborated by the repo's 2025-07-01 creation and
the paper's 2025-08-02 arXiv date. A backtest over 2018–2025 asks the model to "predict"
bars whose successors are in its weights. No purge, embargo, or CPCV fold can undo that;
it is not leakage in the data pipeline, it is leakage in the parameters.

So family M declares **`KRONOS_OOS_START = 2025-06-05`**. Pre-cutoff results are computed
and reported for completeness, labelled **CONTAMINATED**, and are **never eligible for an
ALIVE verdict** or a `graveyard.csv` ALIVE row. Direction of this deviation: it makes ALIVE
strictly *harder* (a 1.1-year window versus 7.5), which is the defensible direction per the
`new-strategy` skill's rule.

#### Declared deviation 2: the accepted regime limitation, and what a win here is worth

The clean window is 2025-06-05 → today: **~287 trading days, ~1.14 years, one macro
regime.** Measured 2026-07-26: SPY +26.3% (Sharpe 1.73), QQQ +33.0% (Sharpe 1.48), BTC-USD
−38.6% (Sharpe −0.82). Equities went one way and crypto went the other, with no vol event
comparable to 2018, 2020, or 2022.

Two consequences, both accepted before running anything:

1. **"Profitable" is close to free on the long side and close to impossible on the short.**
   Any long-biased equity book clears zero return here without the model contributing
   anything; any long-biased crypto book fails for the same reason. This is exactly what
   the 60/40 benchmark gate is for, and it is why **profitability is not the promotion
   criterion in this family — the gates are.**
2. **At n≈287 the best-of-N effect is the same size as the result.** The standard error on
   an annualized Sharpe is ≈0.94 over 1.14 years, so selecting the best of 4 zero-skill
   candidates yields ≈0.96 Sharpe and the best of 10 yields ≈1.44, from noise alone. This
   is precisely the quantity DSR deflates, which is why gate 1 is left exactly as it is and
   `family_n_tested` continues to count all prior graveyard rows rather than being reset
   for a "new" family.

**An ALIVE verdict in family M therefore means less than an ALIVE verdict elsewhere in this
file** — same caveat family L (#86) carries, for a different reason — and must be read with
this attached. The expected outcome of this study is DEAD across the board; that is
information about the window, not a failure of the study.

#### Why the live books, not the backtest, are the real test here

For every other family in this roster the backtest is the primary evidence and the paper
book is confirmation. **Family M inverts that.** Its backtest window is short *and*
selectable — we choose which candidates to report. Forward paper-trading is neither: every
day past today is guaranteed post-cutoff, uncontaminated, and unselected by construction.
The monitor-only books accumulate the only evidence about Kronos that cannot be gamed.

This does not buy a doctrine exemption. Under **DOCTRINE v1.2 a backtest-DEAD book is
monitor-only forever and can never become `paper-confirmed`**, and on a 1.14-year window
that is the likely permanent status of everything below. Accepted up front.

#### Frozen inference parameters — provenance stated, not scanned

Per the `new-strategy` skill: a parameter chosen by analogy is legitimate, one chosen by
scanning requires the *range* to be pre-registered instead. None of these was scanned.

| param | value | where it came from |
|---|---|---|
| checkpoint | `NeoQuasar/Kronos-base` | largest open checkpoint; not selected by comparing performance |
| tokenizer | `NeoQuasar/Kronos-Tokenizer-base` | the matching tokenizer, forced |
| `max_context` | 512 | hard architectural ceiling for `base`, not a choice |
| `clip` | 5 | library default |
| `T` | 0.6 | **the authors' own** backtest value (`finetune/config.py: inference_T`) |
| `top_p` | 0.9 | authors' own (`inference_top_p`) |
| `top_k` | 0 (off) | authors' own (`inference_top_k`) |
| `sample_count` | 30 | the conventional n≥30 floor for an empirical quantile; the authors' 5 is enough for a point forecast but not for the predictive *spread* that `carry_kronos_vol` and `kronos_null` consume |
| `pred_len` | 5 bars | by analogy to the existing 5-day specs in this repo — `sig_str_reversal`'s 5-day fade and `daytrade_tests.wick_study`'s `fwd5` horizon |

Adopting the authors' sampling values wholesale, rather than picking our own, is
deliberate: it removes three degrees of freedom we would otherwise have to pre-register as
ranges. **Any change to a value above is a NEW row and a NEW graveyard entry** (rule 2).

| strategy | spec | freq | status |
|---|---|---|---|
| `kronos_dir_daily` | the vanilla use of the model. Sign of the Kronos-forecast 5-day return over the standard 15-ETF `UNIVERSE`, long/short, vol-targeted and capped through `engine.sized_weights` exactly like every other daily book | D | **QUEUED** |
| `kronos_wick_agg` | **predicted hammer** — the OHLC-only signal. On the 14-name universe of `research/daytrade_tests.py`, long a name when its forecast bars satisfy the *same* hammer test that study applied to realized bars (`lower_wick > 2 × body` and `(close − low)/range > 0.66`, after a 5-bar pullback), held 5 bars. **Aggressive by pre-registered construction:** long-only, equal-weight across triggering names, gross 1.0 whenever ≥1 name fires and flat otherwise — *no* vol targeting, *no* `MAX_LEG` cap, unlike every other daily book here | D | **QUEUED** |
| `carry_kronos_vol` | delta-neutral BTC+ETH funding carry with notional scaled by Kronos's forecast vol: `notional = min(1, TARGET_VOL / forecast_vol)`, where `forecast_vol` is the cross-path SD of the 5-bar cumulative return over the 30 sampled paths. **Capped at 1.0 — it may de-risk but never lever past always-on carry**, or it could beat the benchmark on leverage rather than timing | D | **QUEUED** |

**`carry_kronos_vol`'s benchmark is always-on carry, pre-registered here rather than
declared afterwards.** Family L already established that cash is unusable as a benchmark
for a market-neutral book — cash has zero drawdown, so `calmar(bench)` is NaN and gate 3
degenerates to `MaxDD >= 0`, making gates 2 and 3 unpassable by construction for anything
holding risk. `funding_timing_1h` had to declare that as a post-hoc deviation; there is no
excuse for repeating it as a surprise, so it is fixed in advance. This is also the hardest
non-degenerate benchmark available and asks the economically real question: **does
vol-scaling beat simply holding the position it is meant to improve?**

`carry_kronos_vol` is a variant of the one ALIVE strategy in this lab and therefore carries
the same warning `funding_timing_1h` did: it is the highest-risk row here precisely because
the temptation is to tune a survivor until it looks better. Its verdict is only meaningful
because the spec above was frozen first.

**Null: duty-cycle matched (#101) from the start.** Nulls are random circular rotations of
each candidate's own signal (`harness.sig_rotated`, passed as `like=`), not per-bar random
signals. The opt-in caveat on #101 exists to keep old graveyard rows comparable to the
per-bar null they were scored against; family M has no prior rows, so it takes the better
null immediately. `kronos_wick_agg`'s long-only, sparse duty cycle makes this
non-negotiable — a per-bar null would trade far more than it does and hand it a cost
advantage it never earned, which is the exact failure family L documented at 68×.

**Not a strategy row: `harness.kronos_null()`.** Kronos's third published capability is
*generation* (the paper claims +22% fidelity on synthetic K-lines). A generator of
realistic synthetic price paths — preserving fat tails, vol clustering, and cross-asset
correlation — is a strictly better null than rotating one real history, because it samples
many plausible worlds instead of re-cutting one. It is being built as **opt-in harness
infrastructure alongside the #101 rotation null, not as a candidate**, and it needs no
alpha to be useful: a null generator is allowed to be a mediocre forecaster. Prerequisite
before it is trusted anywhere: a check that generated paths are not recognizably memorized
real windows, since the contamination above applies to generation too.

Reproducibility: Kronos inference is stochastic and the weights are a 400MB external
download, so every forecast used by a verdict is **snapshotted to `artifacts/kronos_*.csv`**
— same requirement family L's rolling-window hourly bars carry, for the same reason. The
signal functions and frozen params live in `src/tradefabe/kronos.py` and the study imports
them from there, so the code that produces the verdict and the code running any live book
are the same function.

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
