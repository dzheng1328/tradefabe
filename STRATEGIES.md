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

**Promotion (#28b, supersedes an earlier #29 rule).** The single best-ranked candidate
each cycle — by CPCV-resampled OOS Sharpe, not raw DSR (#145: DSR saturates to 1.000 for
every daily-rebalanced family regardless of real quality) — is promoted to a live paper
book **regardless of verdict** — Dave's explicit call: more live paper-tracked data is
worth having even when the backtest says DEAD, as long as it's honestly labeled. A
promoted DEAD candidate is monitor-only, same status DOCTRINE v1.2 already gives
backtest-DEAD hand-picked books kept live for research value. This accumulates one new
book per cycle (Dave's explicit choice over a single rotating "champion" slot) up to
`MAX_FACTORY_PROMOTED` (#147) — past that, a cycle still evaluates and logs every
candidate, it just stops opening new books until a slot is freed by hand.

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
its place as a diversifying sleeve on the passive core — see `research/combine.py`, doctrine's
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

**AMENDMENT — `equity_tsmom_1h` data-source swap to Alpaca, pre-registered 2026-07-31,
before re-running (#156).** `research/hourly_backtest.py`'s equity leg
(`fetch_bars(UNIVERSE, "equity")`) swaps from yfinance (rolling 730-day window,
snapshotted 2023-08-25) to Alpaca (hourly equity bars reaching back to ~2016), closing
the regime-limitation gap above **for `equity_tsmom_1h` only**. `crypto_reversal_1h`
and `funding_timing_1h` are both BTC/ETH-denominated and are **not** re-run: Alpaca's
own crypto history only reaches ~2021, no further back than what's already covered, so
a re-run would add multiple-testing cost (`family_n_tested()`, raising the bar for
every future candidate) for zero new information.

Measured and confirmed via `research/alpaca_data_compare.py` (#135) before this
decision: price agreement between the two sources over their overlapping window is
tight (0.04%-0.25% mean abs delta once bar-alignment is accounted for), and Alpaca's
extra depth genuinely covers 2018's vol spike, COVID, and the 2022 bear for equities.

**No change to methodology, gates, thresholds, evaluation frequency, or the frozen
`equity_tsmom_1h` spec** (24-bar sign, long/short, 15-ETF universe) — data source only.
Per DOCTRINE rule 1 (forward-only), this produces a NEW graveyard row; the original
2026-07-26 verdict above is the pre-registration record and is not edited or removed.
Results land in a separate, later commit, same discipline as the original freeze above.

**Result, run 2026-07-31 — still DEAD, more decisively.** 2,729 daily observations from
2016-01-01 (vs. 791 under yfinance's 2023-08-25 start), correctly spanning 2018's vol
spike, COVID, and the 2022 bear via `evaluate()`'s v1.7 window logic (#115): the
candidate's own first observation now predates `OOS_START`, so the full 2018-present
doctrine window is used rather than being silently narrowed to whatever yfinance
happened to have. Sharpe **−3.64** (was −1.93), **MaxDD −100.0%** (was −40.7%, i.e. this
turnover-heavy long/short strategy is a full capital-destruction event once COVID's
whipsaw and the 2022 bear are in the sample, not merely unprofitable). Fails all three
gates outright. The regime-limitation caveat above no longer applies to this row; it
does still apply to `crypto_reversal_1h` and `funding_timing_1h`, neither re-run.

`crypto_reversal_1h` and `funding_timing_1h`'s columns in `artifacts/hourly_returns.csv`
are confirmed byte-identical to before this run (max abs diff 0.0 on every shared date)
— the wider `equity_tsmom_1h` window was deliberately NOT written into the shared file
at its full width (would have back-filled years of misleading flat-zero padding onto
the other two books' live dashboard charts via `book_panel_data()`'s `fillna(0)`); only
the doctrine verdict above used the full 2016-2026 series.

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
| **`daily_context`** | **90 bars** | **AMENDED — see deviation 3.** The authors' own `finetune/config.py: lookback_window`. This is how many bars we FEED, distinct from `max_context`, which is only the ceiling on what the model can accept |
| `clip` | 5 | library default |
| `T` | 0.6 | **the authors' own** backtest value (`finetune/config.py: inference_T`) |
| `top_p` | 0.9 | authors' own (`inference_top_p`) |
| `top_k` | 0 (off) | authors' own (`inference_top_k`) |
| `sample_count` | 30 | the conventional n≥30 floor for an empirical quantile; the authors' 5 is enough for a point forecast but not for the predictive *spread* that `carry_kronos_vol` and `kronos_null` consume |
| `pred_len` | 5 bars | by analogy to the existing 5-day specs in this repo — `sig_str_reversal`'s 5-day fade and `daytrade_tests.wick_study`'s `fwd5` horizon |

Adopting the authors' sampling values wholesale, rather than picking our own, is
deliberate: it removes three degrees of freedom we would otherwise have to pre-register as
ranges. **Any change to a value above is a NEW row and a NEW graveyard entry** (rule 2).

#### Declared deviation 3 (2026-07-27): the fed context is 90 bars, not 512

**The original pre-registration was defective and this amendment supersedes it. No verdict
was rendered under the old value — the defect was found by a model diagnostic run
deliberately BEFORE the study, and `graveyard.csv` still contains no family M row.**

`KronosPredictor.predict()` z-scores its context window (`x = (x - x_mean) / (x_std + 1e-5)`)
and generates in that normalized space. On a trending *daily* series the final bar sits far
from a long window's mean, and autoregressive generation drifts back toward zero — which
denormalizes into a large fabricated return. Measured 2026-07-27 on `Kronos-base`, 8
tickers, 5-bar horizon, 30 sampled paths, regressing the forecast return on `z_last` (the
last bar's z-score inside its own context window):

| fed context | corr(`z_last`, `fc_ret`) | R² | slope | \|mean forecast\| | \|mean actual\| |
|---|---|---|---|---|---|
| 64 | +0.193 | 0.04 | +0.22% per z | 0.76% | 1.35% |
| **90 (adopted)** | −0.376 | 0.14 | −0.56% per z | **1.17%** | 1.35% |
| 128 | +0.642 | 0.41 | +0.88% per z | — | — |
| 512 (original) | **−0.939** | **0.88** | **−7.44% per z** | — | — |

At 512, **88% of the forecast's variance is explained by where the last bar sits in its own
normalization window.** SPY forecast −11.7% against a realized −0.06%; BTC-USD, sitting
*below* its 512-day mean, forecast +13.3% — same mechanism, opposite sign. Across 20 SPY
dates every forecast was negative, mean −8.69%, sign agreement 45%. `sig_kronos_dir` at 512
would have been a dressed-up mean-reversion factor, and its verdict would have been a
verdict on a normalization artifact.

**Why 90 and not the best-scoring value.** At n=8 the standard error on a correlation is
≈0.38, so only the 512 row is decisively different from zero — 64, 90, and 128 are
statistically indistinguishable from clean, and choosing among them on their R² would be
fitting noise. So the value is chosen on **provenance, exactly as every other row in the
table above**: 90 is the authors' own `lookback_window` for fine-tuning, the one context
length they publish for non-intraday use. That it also happens to put the forecast magnitude
(1.17%) closest to realized (1.35%) is a confirmation, not the reason.

**This is out of the authors' tested regime, not a bug in their code.** Every published
Kronos example is intraday — 5-minute A-share bars, an hourly BTC/USDT demo — where 512 bars
span little price movement, `z_last` stays small, and the artifact is negligible. Confirmed
directly: BTC-USD hourly forecast +0.09% against a realized +0.17%. It also implies the
paper's headline RankIC would not surface this: a cross-sectional *rank* metric rewards
ranking assets by distance below their trailing mean, which is a coherent mean-reversion
factor that can score respectably while being useless as a return forecast.

Direction of this deviation: **neutral-to-harder.** It removes a large spurious signal
rather than adding one; whatever remains has to stand on its own. Reproduced by
`research/kronos_context_diagnostic.py`, which renders no verdict and evaluates no returns.

**`sample_count`, `T`, `top_p`, `top_k`, `pred_len`, the checkpoint, and all three strategy
specs are UNCHANGED.** This amendment moves exactly one number.

| strategy | spec | freq | status |
|---|---|---|---|
| `kronos_dir_daily` | the vanilla use of the model. Sign of the Kronos-forecast 5-day return over the standard 15-ETF `UNIVERSE`, long/short, vol-targeted and capped through `engine.sized_weights` exactly like every other daily book | D | **DEAD** |
| `kronos_wick_agg` | **predicted hammer** — the OHLC-only signal. On the 14-name universe of `research/daytrade_tests.py`, long a name when its forecast bars satisfy the *same* hammer test that study applied to realized bars (`lower_wick > 2 × body` and `(close − low)/range > 0.66`, after a 5-bar pullback), held 5 bars. **Aggressive by pre-registered construction:** long-only, equal-weight across triggering names, gross 1.0 whenever ≥1 name fires and flat otherwise — *no* vol targeting, *no* `MAX_LEG` cap, unlike every other daily book here | D | **DEAD** |
| `carry_kronos_vol` | delta-neutral BTC+ETH funding carry with notional scaled by Kronos's forecast vol: `notional = min(1, TARGET_VOL / forecast_vol)`, where `forecast_vol` is the cross-path SD of the 5-bar cumulative return over the 30 sampled paths. **Capped at 1.0 — it may de-risk but never lever past always-on carry**, or it could beat the benchmark on leverage rather than timing | D | **DEAD** |

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

#### RESULTS (2026-07-29): all three DEAD. The forecast has no directional skill.

Judged under **DOCTRINE v1.4** on the clean window **2025-06-05 → 2026-07-29 (288 bars)**,
from a snapshot of **9,185 forecasts** (449 dates × 29 tickers, `artifacts/kronos_forecasts.csv`,
~2.4h of `Kronos-base` inference at ~1.05 forecasts/s on Apple silicon MPS). `n_tested = 139`.

| candidate | Sharpe | Calmar | MaxDD | corr→bench | DSR (gate 1) | gate 2 | gate 3 | verdict |
|---|---|---|---|---|---|---|---|---|
| `kronos_dir_daily` | −1.17 | −0.86 | −5.0% | −0.19 | 0.000 vs SR\* 4.28 | ✗ (−0.86 vs 2.21) | ✓ | **DEAD** |
| `kronos_wick_agg` | +0.69 | 1.32 | −6.5% | +0.34 | 0.008 vs SR\* 2.82 | ✗ (1.32 vs 2.34) | ✓ | **DEAD** |
| `carry_kronos_vol` | +3.10 | 1.01 | −0.7% | +0.81 | 1.000 vs SR\* **−11.42** | ✗ (1.01 vs 32.71) | ✗ | **DEAD** |

**The single most useful number in this family is not in the table.** Over the 4,245 clean
(ticker, date) pairs where a forecast and a realized 5-day return both exist:

- **5-day sign agreement: 47.6%** — below a coin flip.
- **corr(forecast, realized) = −0.031.**
- mean |forecast| 1.76% vs mean |realized| 1.95%.

So after deviation 3 the forecasts are *well calibrated in magnitude* — the 90-bar fix did
remove the normalization artifact, which is exactly what it was for — and carry **no
directional information whatever** on daily US ETF bars past the pretraining cutoff. That is
a statement about the model on this data at this horizon, not about the gates: `kronos_dir_daily`'s
−1.17 Sharpe is what a zero-skill signal plus turnover cost looks like, and no gate
configuration would or should rescue it.

`kronos_wick_agg` was in-market on 21.2% of bars, averaging 1.26 names when it fired, and
returned a positive but sub-benchmark 0.69 Sharpe in a window where SPY did 1.73. Long-only
and long-biased in a rising market is precisely the "profitable is close to free" case
deviation 2 pre-committed to discounting; it cleared zero and nothing else.

`carry_kronos_vol` answers its pre-registered question cleanly and negatively: scaling notional
by Kronos's forecast vol made the carry book **strictly worse than holding it** — lower Calmar
(1.01 vs 32.71) and a *deeper* drawdown (−0.7% vs −0.2%) than always-on carry, because the
scale moves and each move pays cost on both legs. The vol forecast is not timing anything.

**Gate 1 was vacuous on `carry_kronos_vol` and its "True" must not be read as a pass** (#114).
`SR* = −11.42` annualized: the CPCV path Sharpes (mean 2.54, SD 4.45) put the deflated
threshold below zero, so *any* positive Sharpe clears it. The verdict rests entirely on gates
2 and 3. This is the first non-synthetic instance of the #114 pathology and is logged as such.
Two reporting defects surfaced alongside it, both cosmetic and both filed: `harness.evaluate()`
hardcodes the string `(60/40)` on its benchmark line even when the study passes a different
benchmark (here always-on carry), and the Bonferroni bar prints as `−10.81` for the same
reason it prints at all — continuity only, it decides nothing under v1.4.

**Not re-scored under v1.5.** v1.5 (#112) was pre-registered before this run and is
forward-only; family M is judged under v1.4 and stays there. Segregated `n_tested` would have
been **23** rather than 139 for these rows (measured with #120's `family_n_tested` against
this same ledger), which raises `DSR` but cannot change any of the three verdicts: **gate 2
fails on all three and has no `n_tested` term at all.** Recorded as a diagnostic, never as a
verdict.

**What this does and does not close.** It closes the *backtest* question for these three specs
under DOCTRINE rule 2 — any tweak is a new row. It does not close the family: per "Why the
live books, not the backtest, are the real test here" above, forward paper data is the
uncontaminated, unselected evidence, and DOCTRINE v1.2 permits these as **monitor-only books
forever, never `paper-confirmed`.**

#### Live monitor-only books, opened 2026-07-29 (#126)

Two of the three are live: **`kronos_wick_agg`** and **`carry_kronos_vol`**, both at $100k,
both monitor-only forever under v1.2 and never auto-retired under v1.6. Signals come from
`src/tradefabe/kronos.py` — the same functions the study called, imported by
`kronos_live.py` rather than copied, so the live/backtest splice chart compares one strategy
to itself. Every live forecast is appended to the same `artifacts/kronos_forecasts.csv` the
verdict was rendered from: one record, growing forward, because stochastic sampling means a
position that isn't snapshotted can never be audited.

**`kronos_dir_daily` is deliberately NOT live.** Dave's criterion for family M was "only the
ones that are profitable" over the clean window, and its OOS Sharpe was −1.17 on a negative
return, against +0.69 and +3.10 for the other two.

**The tension in that, stated rather than hidden:** choosing which books to *open* on their
backtest result is selection-on-result, and it does weaken the "unselected by construction"
claim above — the forward record is now of two pre-filtered books, not three. Two things keep
it defensible rather than fatal: it is the same selection every promotion in this lab already
makes (the factory promotes its best-ranked candidate), and it happens **once, at open, on a
pre-registered criterion**, not repeatedly on accumulating forward data — which is exactly
what v1.6 forbids. `kronos_live.LIVE_BOOKS` is a one-line change if the unfiltered record is
wanted later.

**Cost of running them.** Inference needs torch and a ~400MB checkpoint, so the daily `run`
job installs the CPU-only wheel and caches the weights; the hourly `mark` job does neither.
All three books are freq D, so a mark has nothing to forecast — it marks them from prices like
any other book. `kronos_wick_agg` needs its own hourly price source (`pricing.wick_hourly`):
its 14 single names are not in `UNIVERSE`, and without that every mark would price its
holdings at NaN. If the extra is missing or inference fails, `run_kronos()` skips the books
and touches no ledger — an 18-book cycle must not fall over because a model download did.

### N. Pairs / cointegration (edge claimed: relative-value mean reversion between two
economically-linked assets — a distinct mechanism from family B's single-asset reversal,
since the bet is on the SPREAD, not on either asset's own direction. #172)

**PRE-REGISTRATION — spec frozen 2026-08-01, before any of the six pairs was tested.**
Results land in a separate, later commit, same discipline as family L's freeze.

**Pair selection, and why it is not a scan.** A blind cointegration scan over all
C(15,2)=105 combinations of `UNIVERSE` would pick pairs *because* they cointegrate
in-sample — meta-level p-hacking, the same trap DOCTRINE's opening section names for
thresholds. Instead, six pairs were chosen for an economic reason to co-move, BEFORE any
cointegration test ran, and cointegration is used only as a pass/fail filter on this
fixed list, not a search criterion (Dave's call, 2026-08-01):

| pair | economic link |
|---|---|
| `GLD`/`SLV` | precious metals |
| `TLT`/`IEF` | treasury duration spread |
| `EFA`/`EEM` | developed vs. emerging international equities |
| `SPY`/`QQQ` | broad market vs. tech-heavy |
| `USO`/`DBC` | oil vs. broad commodities |
| `LQD`/`HYG` | investment-grade vs. high-yield credit |

All twelve tickers are distinct (no ticker appears in two pairs), so the six spreads
trade as one combined 12-asset signal through the same `sized_weights()`/
`size_and_rebalance()`/`net_returns()` pipeline every other family uses — no new sizing
or cost logic.

**Method — Engle & Granger (1987), the standard two-step cointegration test:**
1. Calibration window is 2007–2017, identical to DOCTRINE's own core split (never the
   OOS window a verdict is rendered on). Regress `log(price_A)` on `log(price_B)` (OLS,
   with intercept) to get the hedge ratio `β` and intercept `α`. FROZEN — never
   re-estimated in the OOS period, the same "no re-fitting during OOS" discipline every
   other family already follows.
2. ADF test the calibration-window residual (`log(A) - β·log(B) - α`) for stationarity.
   A pair clears the filter at p < 0.05 (standard significance level, not tuned per
   pair). A pair that fails does not trade OOS at all — dropped from the signal, not
   retried with a different window.

**Signal, entry/exit — Gatev, Goetzmann & Rouwenhorst (2006)'s standard construction:**
the frozen spread `log(A_t) - β·log(B_t) - α` is z-scored against its own trailing
60-day mean/std (matches `engine.VOL_WINDOW`'s existing convention — a live
normalization of the CURRENT spread level, not a re-fit of the cointegrating
relationship itself, which stays frozen from calibration). Enter long-the-spread (long
A, short β·B) at z < −2.0; enter short-the-spread at z > +2.0; exit at z crossing 0
(mean reversion realized); force-flat at |z| > 4.0 — a structural-break stop, same
spirit as the engine's existing `MAX_LEG`/`MAX_GROSS` caps, treating an extreme
divergence as evidence the cointegrating relationship broke rather than more reversion
to come.

**Rebalance freq D** (daily) — a spread can move meaningfully every session; matches
`donchian`/`turn_of_month`'s D frequency in families C/I. **Benchmark 60/40**, family
B's existing convention. **Noise floor:** `harness.noise_floor(prices, "D", trials=500,
like=<this signal>)` — DOCTRINE v1.5's duty-cycle-matched null, reused as-is (random
rotations of the actual six-pair signal, so the null pays the same turnover cost the
candidate does; no custom null construction needed, unlike family L's hourly-specific
`hourly_null`/`funding_null`, since this signal's turnover shape has no reason to differ
from the generic D-rebalanced case those were built to correct for). **Cost:** the
existing `COST_BPS=5.0` per side, unchanged.

**What would make this a genuinely different verdict than families A/B's DEAD rows:**
the edge, if real, comes from the SPREAD reverting (a relative-value bet with two hedged
legs), not from either asset's own direction — the closest prior test, family B's
single-asset `str_reversal_*` (all DEAD), never hedges out market-wide moves, so a
result here is not a parameter variant of an already-DEAD spec.

**Result, run 2026-07-31 — DEAD.** Only **`LQD`/`HYG`** cleared the cointegration
filter (ADF p=0.037); the other five failed it outright (p ranging 0.06–0.55) and were
dropped, never traded OOS, per the pre-registration:

| pair | β | ADF p-value | traded OOS? |
|---|---|---|---|
| `GLD`/`SLV` | 0.637 | 0.133 | no |
| `TLT`/`IEF` | 1.375 | 0.161 | no |
| `EFA`/`EEM` | 0.826 | 0.551 | no |
| `SPY`/`QQQ` | 0.732 | 0.058 | no |
| `USO`/`DBC` | 2.077 | 0.201 | no |
| `LQD`/`HYG` | 0.843 | **0.037** | **yes** |

The one tradeable spread (163 position changes over 2007–2026) showed essentially no
edge: Sharpe **0.00**, DSR 0.150 (fails gate 1 outright — not a close call), Calmar
−0.01 vs. the 60/40 benchmark's 0.45 (fails gate 2), MaxDD −12.1% within the gate-3
limit but moot given gates 1–2 already fail. `graveyard.csv` carries exactly the one
row this run produced — a debugging pass hit the append-only ledger three times before
landing here (two sizing/logic bugs found and fixed, see below), and those stale rows
were removed before this commit rather than left to pad `family_n_tested()`.

**Two real bugs found and fixed while building this, not just tuning:**
1. `engine.sized_weights()` divides by `prices.shape[1]` — correct for every other
   family, which densely populates every column with a view every day, but silently
   dilutes a structurally SPARSE pairs signal (only one pair's two columns ever
   nonzero) if the full 12-ticker candidate universe is passed through regardless of
   how many pairs actually cleared the filter. Fixed by narrowing the traded universe
   to only the tickers of pairs that passed, before sizing — confirmed the fix
   matters: MaxDD went from −2.1% (diluted, 1/12 sizing) to the correct −12.1% (1/2
   sizing) with the Sharpe unchanged (leverage-invariant, as expected).
2. The z-score entry condition allowed entering a position at |z| already past
   `Z_STOP` — self-contradictory, since that position would immediately force-flatten
   next bar. Fixed by bounding entry to `Z_ENTRY < |z| < Z_STOP`. Verified this
   doesn't change the LQD/HYG result (the edge case never fired in the real data), but
   is a real correctness fix, caught by `tests/test_pairs_backtest.py`'s own
   construction, not by re-running until the numbers looked right.

`research/pairs_backtest.py`, `tests/test_pairs_backtest.py`.

## Research pipeline — primitive vocabulary (#174/#177)

**PRE-REGISTRATION — frozen 2026-08-01, before any candidate was proposed through it.**
The daily automated research pipeline's idea-generation step (`research/pipeline_ideas.py`,
DOCTRINE v1.9/v1.10, #175/#176) is the one genuinely LLM-driven part of this repo
(README.md's own principle: strategies stay deterministic, "no LLM in the trade loop").
Rather than let the model write code or invent a mechanism, it picks a **primitive** and
**parameters** from the fixed vocabulary below — the same split `factory.GENERATION_RANGES`
already draws between a pre-registered range (fixed here, reviewed once) and the specific
value drawn (not pre-registered, since it's read off a range that already was). This is
what stops the pipeline from reopening the meta-level p-hacking risk DOCTRINE.md's opening
section warns about, in a new, LLM-shaped form.

| primitive | mechanism | parameters |
|---|---|---|
| `pair_zscore` | Mean-reversion of the z-scored log-spread between two `UNIVERSE` tickers (simple 1:1 spread — unlike family N's regressed hedge ratio, this primitive has no calibration step of its own; a fitting general-purpose first look, not a substitute for a properly pre-registered pair like family N's) | `ticker_a`, `ticker_b` ∈ UNIVERSE; `z_window` 20–120; `z_entry` 1.5–3.0; `z_stop` 3.0–6.0 |
| `cross_sectional_rank` | Long the top-K / short the bottom-K of the full `UNIVERSE`, ranked by a fixed metric | `metric` ∈ {momentum, low_vol, reversal}; `lookback` 20–252; `k` 1–7 |
| `single_asset_trend` | Long/short one ticker by the sign of its own trailing return | `ticker` ∈ UNIVERSE; `lookback` 20–252 |
| `static_spread_carry` | A fixed, always-on long-short between two tickers — a structural risk-premium bet, not mean-reversion | `ticker_a`, `ticker_b` ∈ UNIVERSE; `long_leg` ∈ {a, b} |
| `asset_class_trend_hedge` | Two independent `single_asset_trend` legs held in one candidate — the first primitive to combine two signals rather than express one. `ticker_a`/`ticker_b` must come from two DIFFERENT `tradefabe.pipeline.ASSET_CLASS` buckets (equity/rates/commodity/real_estate/currency, derived from the ticker, not asserted) | `ticker_a`, `ticker_b` ∈ UNIVERSE (different asset class); `lookback_a`, `lookback_b` 20–252 |
| `curve_carry` | A DV01-neutral TLT/IEF position whose direction trend-follows the real FRED curve slope (`DGS10 - DGS2`): steepening → short TLT / long IEF, flattening → long TLT / short IEF, sized so the two legs' duration exposure roughly offsets. Fixed to TLT/IEF only — no `ticker_a`/`ticker_b` choice like other primitives, since real duration data is only pre-registered for this pair | `lookback` 20–252 |

**Vocabulary expansion — `asset_class_trend_hedge` added 2026-08-04 (#194).** Dave's
explicit call: the original 4 primitives can only ever parameterize the same 4 shapes;
growing the vocabulary (not just picking among the 4) is the actual lever for the
routine to discover something genuinely new. This is the first COMPOSITIONAL primitive
— see #194's own issue text for why it starts here rather than with structural carry
(the only other mechanism class with a live survivor in this lab, but blocked on data
infrastructure this repo doesn't have yet). Because a compositional primitive can look
like it earns its place through variance reduction alone rather than real economic
logic, it carries two MECHANICAL guards no other primitive needs, neither reducible to a
rationale field the LLM could write around:
1. **Asset-class difference** (`pipeline.legs_differ_by_asset_class()`) — offline, checked
   in `validate_proposal()` for a manually-proposed candidate.
2. **Calibration-window (2007–2017) correlation cap** (`pipeline.legs_pass_calibration_corr_cap()`,
   `CALIB_CORR_CAP = 0.3`) — the two legs' own trend signals must actually decorrelate on
   calibration data alone, not just be asserted to.

Both guards run in `pipeline_daily.screen_pending_backlog()`, the one checkpoint every
pending name passes through regardless of origin — necessary because the scheduled
research routine (see the rate-limit note below) writes `pipeline_ideas.csv` rows
directly, bypassing `validate_proposal()` entirely, so the offline check alone can't be
relied on for a routine-written proposal.

**Vocabulary expansion — `curve_carry` added 2026-08-05 (Phase 2 of the carry-
generalization design, `docs/superpowers/specs/2026-08-04-carry-generalization-design.md`).**
Of 139+ strategies ever tested in this lab, exactly one predictive-adjacent mechanism has
ever survived: delta-neutral crypto funding carry. `curve_carry` is the first attempt to
generalize that mechanism class beyond crypto, using real Treasury yield-curve data
(`src/tradefabe/rates.py`, free FRED endpoint) rather than price-derived proxies. Unlike
`static_spread_carry`'s unhedged long-short (a directional duration bet, not actually
carry's risk structure), `curve_carry`'s legs are sized so their DV01s roughly offset —
`TLT_DURATION = 16.0`, `IEF_DURATION = 7.5`, pre-registered point estimates from the
verified 2026-08 range (TLT ~15–16.5yr, IEF ~7–8yr effective duration; iShares fact
sheets, mid-2026), fixed and reviewed once, never fetched live or re-derived from data —
isolating the position to curve-shape/roll-down carry instead of a parallel-shift level
bet, the standard institutional "duration-neutral curve steepener/flattener" shape.

**Guard: calibration-window hedge-effectiveness, not divergence from another primitive.**
`pipeline.curve_carry_hedge_is_effective()` checks that the position's own calibration-
window (2007–2017) daily returns decorrelate below `CALIB_CORR_CAP = 0.3` (reused, not
reinvented) from `DGS10`'s own daily change — confirming the DV01 hedge actually
cancelled level risk in calibration data, not just on paper. Wired into
`pipeline_daily.screen_pending_backlog()` the same way `asset_class_trend_hedge`'s guards
are: before the (comparatively expensive) prelim screen ever runs, and logged via
`harness._log_prelim()` on rejection so a guard-failed candidate doesn't resurface forever.

**Direction is mechanical, not routine-discretionary.** Every other primitive with a
directional choice (e.g. `static_spread_carry`'s `long_leg`) lets the routine pick it.
`curve_carry` doesn't — direction is `sign(slope_today − slope_{today−lookback})` on the
curve slope itself, reusing the exact trend-signal SHAPE `single_asset_trend` already
uses (sign of a trailing change over a pre-registered, routine-chosen window), just
applied to curve data instead of price data. `lookback` (20–252, same range) is the only
free parameter — no new arbitrary "steep enough" cutoff was invented for this primitive.

Every proposal is validated against these ranges mechanically (`pipeline_ideas.validate_proposal()`)
before anything else happens — an out-of-range parameter, an unknown primitive, or a
missing rationale/citation is rejected before a name is even assigned, let alone before
`prelim_screen()` (#175) runs. The name is assigned deterministically from
`(primitive, params)` (`pipeline_ideas.make_name()`), never chosen by the model, and is
always prefixed `rp_` — #176's origin-classification contract, satisfied by construction.

**Rate limit, as of 2026-08-05: up to 10 proposals/day, FIXED (not "until one
passes").** Proposal generation moved from `pipeline_ideas.py`'s in-process, $0.05/day-
capped Haiku API call (retired 2026-08-04) to a scheduled Claude Code Routine (claude.ai,
running under Dave's Pro subscription, real web-search tool use) — 10 separate daily
triggers, each producing at most one proposal, writing `pipeline_ideas.csv` directly.
FIXED at 10, not "keep researching until one clears the screen": the calibration screen
(#175) is deliberately lenient, so an until-success loop would eventually clear it by
pure chance almost regardless of merit — some runs, and some days, legitimately produce
zero candidates worth screening further, and that's the screen doing its job, not a
failure. `pipeline_ideas.py`'s own budget/API machinery still exists and is still
tested — the reference for `pipeline_ideas.csv`'s row shape, which the routine
replicates by hand — but nothing in the automated daily cron calls it anymore.

A malformed row, a duplicate of an already-tested or already-proposed spec, or a day
with fewer than 10 genuinely new ideas are all logged and treated as a **clean skip,
not a failure** — proposing fewer than the daily cap is a legitimate outcome, the same
principle DOCTRINE v1.9's prelim firewall already applies one step downstream.

**The daily cycle (#178, extended #180/#181, `research/pipeline_daily.py`)** screens
(#175) and pre-registers on a pass (#179) whatever's sitting in `pipeline_ideas.csv`
unscreened, then OOS-tests (#180) whatever's pre-registered and untested — both
unconditional every cycle, regardless of how many (if any) new rows landed today.
`.github/workflows/pipeline-daily.yml` runs this once a day, first merging in any
routine proposal that landed on a branch instead of main
(`research/merge_routine_branches.py`, a safety net, #181) before screening. A failed
screen, like an unproposed day, is a logged outcome, not a pipeline failure.

`research/pipeline_ideas.py`, `research/pipeline_daily.py`, `research/pipeline_verdict.py`,
`research/merge_routine_branches.py`, `src/tradefabe/pipeline.py`, `src/tradefabe/rates.py`,
`tests/test_pipeline_ideas.py`, `tests/test_pipeline_daily.py`, `tests/test_pipeline_verdict.py`,
`tests/test_merge_routine_branches.py`, `tests/test_tradefabe_pipeline.py`,
`tests/test_curve_carry.py`, `tests/test_rates.py`.

## Research pipeline — pre-registered candidates (#179)

Every candidate the research pipeline (#174) proposes and clears #175's prelim screen is pre-registered here AUTOMATICALLY -- DOCTRINE v1.11's fully-automatic checkpoint (Dave's explicit call, 2026-08-01), no human review before the full OOS test (#180) runs. Generated programmatically from the validated proposal (`research/pipeline_register.py`), not hand-written prose like the families above.

### `rp_asset_class_trend_hedge_SPY_GLD_252_252` (primitive `asset_class_trend_hedge`)

**PRE-REGISTRATION — frozen 2026-08-05, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=SPY, ticker_b=GLD, lookback_a=252, lookback_b=252. Rebalance freq: M.

Rationale: Structural context, not a track-record claim: the equity-bond correlation that makes a rates leg the default hedge for an equity leg has flipped positive again in 2026. The late-February 2026 Strait of Hormuz closure delivered exactly the shock that produces that regime -- an oil-driven supply/inflation shock lifts discount rates, compressing equity valuations and Treasury prices at the same time, and US 10-year Treasury returns have been negative alongside equity selloffs since. Gold's demand base is structurally different from both: official-sector buying ran 244 tonnes in Q1 2026 (10th 200t+ quarter in 11), is explicitly strategic reserve diversification rather than rate- or dollar-sensitive flow, and gold's low-to-negative equity correlation has persisted specifically through geopolitical and oil-driven inflation episodes. That is the mechanism for these two legs to offset: SPY's trend leg is driven by the earnings/discount-rate channel, GLD's by an official-sector reserve-diversification and debasement-hedge channel with opposite-signed sensitivity to the same real-rate and inflation shocks -- not merely two things that happen to be uncorrelated. Both lookbacks are the canonical 12-month time-series-momentum horizon (Moskowitz-Ooi-Pedersen 2012), chosen for being the pre-existing standard rather than picked, and freq M matches that horizon's turnover. Stated honestly: each leg on its own is in the trend family this lab has already killed many times over, and the claim under test is only whether the cross-asset-class pairing earns its place under gate 2 while gate 1's DSR still requires the combination itself to beat a duty-cycle-matched null. Distinct from the only prior pipeline proposal (rp_static_spread_carry_TLT_IEF_a, a rates term-premium carry bet) in primitive, mechanism and asset classes.

Citation: Moskowitz, Ooi & Pedersen (2012), 'Time Series Momentum', Journal of Financial Economics 104(2) -- source of the 12-month lookback. Equity-bond correlation regime and the late-Feb-2026 Strait of Hormuz trigger: Seeking Alpha, 'Stock-Bond Dynamics May Be In Flux, But Global Diversification Proved Its Worth In 2026' (seekingalpha.com/article/4916748); inflation >3% historically producing positive equity-bond correlation. Gold's persistent negative equity correlation through geopolitical and oil-driven inflation risk, and its elevated diversifier role when stock-bond correlation is high: State Street, 'Gold takes the diversification crown' and 'Gold 2026 Midyear Outlook' (ssga.com/us/en/intermediary/insights); World Gold Council, 'Why gold in 2026? A cross-asset perspective' (gold.org/goldhub/research/why-gold-2026-cross-asset-perspective). Official-sector demand of 244 tonnes in Q1 2026: World Gold Council, Gold Demand Trends Q1 2026 -- Central Banks (gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2026/central-banks), released 2026-04-29.


### `rp_static_spread_carry_GLD_UUP_a` (primitive `static_spread_carry`)

**PRE-REGISTRATION — frozen 2026-08-05, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=GLD, ticker_b=UUP, long_leg=a. Rebalance freq: M.

Rationale: Structural flow, not a track-record claim -- and deliberately the OPPOSITE of one: the official-sector buying this candidate is built on happened INTO a falling gold price, so nothing here is selection on recent performance. A fixed, always-on long GLD / short UUP is the most direct expression this UNIVERSE can make of one specific, currently-measurable structural flow: the official sector rotating reserve assets out of USD claims and into gold, with no directional forecast of either leg. The mechanism, from primary data. World Gold Council Gold Demand Trends Q2 2026 (published 2026-07-30) puts central bank NET gold demand at 289t in Q2 -- a record for any second quarter and roughly a FIVEFOLD increase on Q1's revised 57t -- with Poland the largest buyer and Uzbekistan (+16t), Kazakhstan (+15t), Jordan (+6t) and the Czech National Bank (+6t) also notable; Russia (-22t) and Turkey (-4t) were the only meaningful sellers. The load-bearing detail is not the tonnage but its price-insensitivity: that record quarter was bought while gold fell about 16% over the same period. A buyer who accelerates fivefold into a double-digit drawdown is not a momentum participant -- that is reserve-policy demand whose size is set by an allocation target rather than by price, which is exactly what a structural risk premium needs on the other side of it. The WGC's 2026 Central Bank Gold Reserves Survey gives the matching intention data: 89% of reserve managers expect global official gold holdings to rise over the next 12 months and 74% expect to CUT their USD holdings over the next five years. That is the same trade this spread expresses, stated by the people doing it: gold up, dollar down, funded out of one another. Short UUP rather than an unhedged long GLD because the hypothesis is about the ROTATION -- the relative claim -- not about gold's own dollar price, and because it is the one leg pairing in the current UNIVERSE that isolates it. The single biggest weakness, stated first rather than buried: this spread has NEGATIVE cash carry on BOTH legs, unlike this lab's one surviving carry book. Gold pays no yield and the GLD wrapper charges its expense ratio against the bullion itself; the short-UUP leg pays the USD-versus-basket short-rate differential, and that differential is wide against this trade right now -- the 1-year Treasury was 4.00% on 2026-08-04 against an ECB deposit rate of 2.25% (raised 2026-06-11) and a BoJ policy rate of 1.0% (held 2026-07-31), i.e. roughly 175-300bp/yr of running cost versus the two heaviest DXY-basket weights. So this is NOT carry in the funding-rate sense that crypto funding carry is; the entire thesis is that a price-inelastic official buyer absorbing supply compensates for a KNOWN negative running cost. That is a materially weaker structural claim than a mechanically-paid funding rate, and it should be read as the main reason the candidate might deserve to die rather than as a caveat appended to a bullish case. The second risk, and the reason it is worth testing anyway: the two legs share a common driver, so the spread is not two independent bets. Both respond to the same real-rate and US-fiscal-credibility shock -- the term-premium-driven bear steepening now visible at the long end (30-year 5.28%, 10-year 4.63%, 2-year 4.21% as of early August 2026) is widely attributed to fiscal supply rather than growth optimism, and that is the same shock the reserve-rotation thesis rests on. When it dominates, the legs reinforce and the spread is effectively a levered single bet on dollar debasement, not a hedged one. When a conventional Fed-tightening or flight-to-quality shock dominates instead, the dollar and gold both firm and the legs offset to roughly nothing. Neither regime is forecast here. What the OOS window will actually decide. 2018-present contains at least three episodes that should punish this construction hard if the premium is not real: the 2018 and 2022 dollar-strength runs (short UUP losing while real rates rose against gold -- the paired-loss case), and March 2020's dash-for-dollars, when gold sold off in the liquidity scramble while the dollar spiked, which is the worst single realization available. Against that, 2020-2021 and 2025 are the favorable realizations. If the average premium does not survive those drawdowns net of the negative carry above, the candidate should and will fail gate 3 or gate 2's Calmar test -- that is the hypothesis under test. Distinct from everything already tested here: no strategy in graveyard.csv and no pre-registered pair in STRATEGIES.md uses UUP at all, so this is the first use of the currency asset class in any spread on the roster -- family N's six cointegration pairs are GLD/SLV, TLT/IEF, EFA/EEM, SPY/QQQ, USO/DBC and LQD/HYG, all within-asset-class. It is also distinct in mechanism from all five prior pipeline proposals (a rates term-premium carry, an equity/gold trend hedge, a commodity front-of-curve roll carry, a corporate-credit carry, and a real-estate cap-rate carry): none of them touch a monetary/reserve-asset flow. freq M matches a static spread whose only turnover is the rebalance back to fixed weights, and is the right clock for a flow measured in quarterly reserve reports.

Citation: Official-sector gold demand, primary source: World Gold Council, 'Gold Demand Trends: Q2 2026' (published 2026-07-30) -- central bank net demand 289t in Q2, a record second quarter and a fivefold rise on Q1's revised 57t; Poland the largest buyer, Uzbekistan +16t, Kazakhstan +15t, Jordan +6t, Czech National Bank +6t, Russia -22t, Turkey -4t; total demand incl. OTC 1,269t in Q2 and 2,522t in H1 (+2% y/y, a record US$380bn) (gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q2-2026/central-banks). The price-insensitivity of that quarter (record buying into an approximately 16% quarterly price decline) as reported in coverage of the same release: 'Central Banks Buy Record 289t of Gold in Q2 2026, Buying Into a 16% Price Drop', TFTC, 2026 (tftc.io/central-bank-gold-purchases-record-289-tonnes-q2-2026). Reserve-manager intentions: World Gold Council, 'Central Bank Gold Reserves Survey 2026' -- 89% expect global official gold holdings to rise over the next 12 months, 74% expect lower USD holdings over the next five years (gold.org/goldhub/research/central-bank-gold-reserves-survey-2026). Negative-carry inputs: US 1-year Treasury 4.00%, 2-year 4.21%, 10-year 4.63%, 30-year 5.20-5.28% as of 2026-08-04 (streetstats.finance/rates/treasuries; 'Six Years into Bond Bear Market, 30-Year Treasury Yield Hits 5.28%...', Wolf Street, 2026-08-01); ECB deposit facility rate 2.25% following the 2026-06-11 hike (effective 2026-06-17); Bank of Japan short-term policy rate 1.0%, held 2026-07-31 after its June hike ('BOJ holds rates at 1%, warns of core inflation exceeding 2% target', CNBC, 2026-07-31). Term-premium/fiscal composition of the current steepening: Oxford Economics, 'Stock bond correlation will become positive again in 2026' (oxfordeconomics.com/resource/stock-bond-correlation-will-become-positive-again-in-2026) and ING Think, 'Dollar 2026 decline: more cyclical than structural' (think.ing.com/articles/dollars-2026-decline-more-cyclical-than-structural), the latter cited explicitly as the argument AGAINST a structural USD repricing being already established.


### `rp_asset_class_trend_hedge_TLT_DBC_252_60` (primitive `asset_class_trend_hedge`)

**PRE-REGISTRATION — frozen 2026-08-05, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=TLT, ticker_b=DBC, lookback_a=252, lookback_b=60. Rebalance freq: W.

Rationale: Every rates-leg diversification argument in this lab (and the 60/40 benchmark itself) rests on duration offsetting risk assets, but that offset is a function of WHICH shock dominates, not a constant: demand shocks and flight-to-quality produce negative stock/bond correlation, while inflation surprises and monetary-policy shocks produce positive correlation. Oxford Economics' 2026 view is that the correlation returns to positive territory, driven by rising term premia, supply shocks, and macro volatility from activist fiscal policy -- i.e. the regime's dominant shock right now is exactly the one under which duration stops hedging. Under that same shock, long duration and a broad commodity basket carry OPPOSITE inflation betas, and that is the specific mechanism I expect to make these two legs offset, not a correlation search: a supply/inflation surprise pushes inflation expectations and yields up (TLT down) precisely because commodity prices are a direct input to the CPI/PPI prints that move those yields (DBC up). The lookbacks are deliberately asymmetric and matched to each shock's own speed rather than tuned: the duration regime -- term premium, Treasury supply, QT -- moves over quarters, so TLT gets 252d; a commodity supply shock propagates into spot within weeks, so DBC gets 60d. Freq is W, the finer of the two legs (the factory's own combo convention), so the fast commodity leg is not a month stale at rebalance. Distinct from the DEAD universe-wide tsmom_* family, which applies one lookback across all 15 tickers and nets out any asset-class structure, and from rp_asset_class_trend_hedge_SPY_GLD_252_252, an equity-vs-commodity pair on symmetric lookbacks. Note this is a hedge-construction claim, not a directional one: if the inflation-beta opposition is real the two trend legs should decorrelate on the calibration window; if it is not, the mechanical CALIB_CORR_CAP check should reject this and that is the correct outcome.

Citation: Oxford Economics, 'Stock bond correlation will become positive again in 2026' (oxfordeconomics.com/resource/stock-bond-correlation-will-become-positive-again-in-2026/) -- correlation expected positive again in 2026 on rising term premia, supply shocks and activist-fiscal macro volatility. Shock-composition mechanism: Vanguard, 'The stock/bond correlation: increasing amid inflation' (nl.vanguard/content/dam/intl/europe/documents/en/the-stock-bond-correlation-eu-en-pro.pdf); AQR, 'A Changing Stock-Bond Correlation' (aqr.com/Insights/Research/Journal-Article/A-Changing-Stock-Bond-Correlation); Financial Analysts Journal 80(3), 'Empirical Evidence on the Stock-Bond Correlation' (doi.org/10.1080/0015198X.2024.2317333) -- demand/flight-to-quality shocks give negative correlation, inflation and monetary-policy shocks give positive. Commodity-vs-duration inflation-beta opposition: Morgan Stanley, 'Commodities Outlook 2026' (morganstanley.com/insights/articles/commodities-outlook-2026-resilience-through-market-volatility) and ETF.com, 'Best ETFs for Inflation in 2026' -- commodity prices feed directly into CPI/PPI, while the same prints push inflation expectations and yields up and long-bond prices down.


### `rp_single_asset_trend_GLD_126` (primitive `single_asset_trend`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker=GLD, lookback=126. Rebalance freq: M.

Rationale: Official-sector gold demand is now a large, mandate-driven, PRICE-INSENSITIVE flow, and that is the structural condition a trailing-sign trend rule on a single asset is supposed to monetize. Central banks have averaged ~1,000t/yr of net purchases over the past four years against a ~500t/yr average in the preceding decade, and Q2 2026 was the strongest second quarter on record at a net 289t (+62% y/y) -- bought straight into a ~16% quarterly decline in the gold price, led by Poland and China. A buyer whose size is set by a multi-year reserve-diversification mandate rather than by price is, by definition, an inelastic demand curve (Gabaix & Koijen 2021): flows of that shape are absorbed by a limited, slowly-arriving pool of intermediary capital (Duffie 2010), so their price impact is spread over weeks-to-quarters rather than impounded at once, which is what produces serial correlation in returns for a trend rule to capture. The 2026 configuration is what makes this testable rather than a one-sided bull thesis: the official bid absorbed but did NOT defend a 16% drawdown, so the sample now contains sustained moves in BOTH directions with the same inelastic buyer present -- a trend rule here is not a disguised long-gold bet. Parameters follow the mechanism, not a search: lookback=126 trading days is two reserve-reporting quarters, the cadence on which this flow is actually decided and disclosed, and freq=M matches that horizon while keeping turnover negligible. Distinct from the universe-wide tsmom_* / tsmom_gen_* families in graveyard.csv, which trend every UNIVERSE ticker as one ensemble and never isolate a single asset's own flow story, and from the already-DEAD rp_asset_class_trend_hedge_SPY_GLD_252_252, which paired a 252d GLD leg against an equity leg. Prior expectation is genuinely uncertain: the same inelasticity could equally show up as dip-buying that damps trends, which is exactly why it belongs in front of the gates rather than in a narrative.

Citation: World Gold Council, Gold Demand Trends Q2 2026 -- central banks net 289t in Q2 2026, strongest Q2 on record, +62% y/y, purchased during a ~16% quarterly price fall, led by Poland and China (gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q2-2026/central-banks; tftc.io/central-bank-gold-purchases-record-289-tonnes-q2-2026; discoveryalert.com.au/central-banks-buying-gold-price-correction-reserves-2026/). WGC Central Bank Gold Reserves Survey 2026 -- ~1,000t/yr four-year average vs ~500t/yr prior decade; 89% of reserve managers expect global gold reserves to rise over the next 12 months, a record 45% expect their own to rise, 74% expect lower USD holdings over five years (gold.org/goldhub/research/central-bank-gold-reserves-survey-2026; YTD 2026: Poland +64t, Uzbekistan +33t, China +25t per visualcapitalist.com/ranked-central-banks-buying-and-selling-gold-in-2026/). Mechanism: Gabaix & Koijen (2021), 'In Search of the Origins of Financial Fluctuations: The Inelastic Markets Hypothesis', NBER w28967; Duffie (2010), 'Asset Price Dynamics with Slow-Moving Capital', Journal of Finance 65(4).


### `rp_single_asset_trend_SLV_63` (primitive `single_asset_trend`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker=SLV, lookback=63. Rebalance freq: W.

Rationale: Silver's physical market is in an unusually extreme inventory state right now, and inventory state -- not price history -- is the pre-registered reason to look at a trend signal on this one ticker. The Silver Institute/Metals Focus project a SIXTH consecutive year of structural deficit in 2026, with ~762 Moz drawn out of global above-ground stocks since 2021; COMEX registered stocks (deliverable) have shrunk faster than eligible, London float hit a record-low ~17% unencumbered in Sep 2025, lease rates spiked to double-digit and at times 50-200% annualised, and the futures curve has been in its deepest backwardation since 1980. The theory of storage says exactly what that implies mechanically: when inventories cannot buffer a shock, the spot price -- not the stockpile -- has to absorb it, convenience yield rises, and the adjustment happens as large, persistent, self-reinforcing repricings rather than smooth mean-reverting moves. Gorton, Hayashi & Rouwenhorst (NBER w13249) is the direct empirical statement of the link: the returns to spot/futures momentum and backwardation strategies come substantially from being in commodities whose inventories are LOW, and low inventories also raise expected future spot volatility via stock-out risk. Silver's realised path in this episode fits that description structurally rather than anecdotally -- a record $121.62 print on 2026-01-29 and ~$61.58 on 2026-08-05, i.e. moves that persist over months in both directions, which is the regime a trailing-return-sign signal is built to hold and the regime a passive holder is worst positioned for. Lookback 63 trading days (~1 quarter) is set to the timescale of the squeeze/unwind legs actually observed (Oct-2025 liquidity seizure -> Jan-2026 peak -> mid-2026 unwind), and W rebalance because that mechanism operates over weeks-to-months while daily rebalancing would pay turnover cost on an asset with this much day-to-day noise for no signal gain. The real risk being borne is explicit: a stock-out regime resolves violently, so the same conditions that make moves persistent also make the reversal sharp -- this is a whipsaw bet, not a free one. Stated honestly and NOT relitigating the DEAD trend family: this lab has killed tsmom across the whole universe at 3/6/9/12/18/24m monthly, and the OOS window (2018-present) is mostly NOT a low-inventory silver regime, so the gate will judge this signal over years where its motivating condition was absent. That is the doctrine working as designed -- the conditioning argument is the reason to spend a slot on SLV specifically rather than a claim about what the verdict should be. No prior graveyard.csv or pipeline_ideas.csv row applies single_asset_trend to SLV.

Citation: Gorton, Hayashi & Rouwenhorst (2007/2013), 'The Fundamentals of Commodity Futures Returns', NBER Working Paper 13249 (nber.org/system/files/working_papers/w13249/w13249.pdf) -- inventories drive basis, momentum and futures risk premia; Working (1949)/Deaton & Laroque (1992) theory of storage. Current conditions: Silver Institute / Metals Focus sixth consecutive structural deficit projected for 2026 and 762 Moz of above-ground stock drawdown since 2021 (silverinstitute.org; indexbox.io silver inventories COMEX/LBMA; discoveryalert.com.au silver supply-demand imbalance 2026); London ~17% unencumbered float Sep 2025 and lease-rate spikes (bullionstar.com 'Silver Enters 2026 in a State of Structural Breakdown'; thesilverindustry.substack.com); deepest backwardation since 1980 (ebc.com silver supply deficit 2026); price marks $121.62 record 2026-01-29 and $61.58 on 2026-08-05 (tradingeconomics.com/commodity/silver).


### `rp_cross_sectional_rank_momentum_126_2` (primitive `cross_sectional_rank`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: metric=momentum, lookback=126, k=2. Rebalance freq: M.

Rationale: A cross-sectional, dollar-neutral top-K/bottom-K ranking pays off only from the RELATIVE ordering of a basket, not from the common factor that moves everything together -- so its structural precondition is that the common factor has stopped explaining most of cross-asset return variance. That precondition is unusually well satisfied by the mid-2026 policy configuration: the major blocs' rate paths have decoupled outright rather than merely de-synchronised in timing (the Fed easing toward a ~3-3.25% neutral by mid-2026 after 175bp of cuts from the 2023 peak, against an ECB that RAISED 25bp to 2.25% and a BoJ that raised 25bp to 1.00%, both effective mid-June 2026), so the single global discount-rate impulse that used to co-move equity, rates, commodity, real-estate and FX buckets is now several impulses pointing different directions. On top of that, the long end is being priced by issuance and QT rather than by the expected short-rate path (NY Fed ACM 10y term premium back to a clearly positive 0.79% at 2026-07-30, 30y above 5.25% against a ~4.70% 10y), and July 2026 showed simultaneous correlation BREAKS across several usually-linked cross-asset pairs -- gold rising alongside real yields, the gold/oil ratio at multi-decade extremes. Divergence generated by issuance calendars, reserve reallocation and bloc-specific policy cycles persists over quarters, which is why the lookback is 126d (a ~6-month horizon matched to those drivers) with a monthly rebalance rather than a fast signal. k=2 out of the 15-ticker UNIVERSE is deliberate and is the other half of the structural argument: it takes only the tails of the cross-section instead of a broad basket, since a broad-basket dispersion construction maximises exposure to exactly the correlation spike that ends this kind of regime (the March 2026 correlation shock is the recent worked example). Stated plainly rather than buried: this lab already holds a DEAD verdict on `xsec_momentum` (graveyard.csv, OOS Sharpe 0.307, monthly), and dozens of DEAD `low_vol_xsec*` rows, so this is the same primitive family as something already killed. It is a materially different construction -- a 12-month, long-top-half/short-bottom-half signal over the whole basket versus a 6-month, top-2/bottom-2 tail portfolio -- and it is motivated by a current structural condition rather than by re-tuning until the old spec passes, but a reviewer should weigh it against DOCTRINE's 'no knob-tuning to resurrect' rule with that overlap in full view. No claim is made here about any strategy's recent performance; the argument is about the correlation/dispersion structure the primitive needs, not about what has been working.

Citation: Central-bank divergence and the mid-2026 policy configuration: maseconomics.com/central-bank-divergence-in-2026-why-the-fed-ecb-boj-and-boe-are-moving-in-opposite-directions/; trustcapital.com/blog/ecb-vs-fed-vs-boj-policy-divergence-2026; gloriarms.com/insights/central-bank-watch/ (ECB +25bp to 2.25% eff. 2026-06-17, BoJ +25bp to 1.00% 2026-06-16; Fed toward 3-3.25% neutral by mid-2026). Term premium / long-end pricing: Adrian, Crump & Moench (2013), NY Fed ACM term premia (newyorkfed.org/research/data_indicators/term-premia-tabs), 10y ACM 0.79% at 2026-07-30; 30y >5.25% vs ~4.70% 10y late July 2026. Cross-asset correlation breaks, July 2026 (gold vs real yields, gold/oil ratio at multi-decade extremes): ahasignals.com/cross-asset-correlation-dashboard/. Dispersion-construction lesson from the March 2026 correlation shock: resonanzcapital.com/insights/after-the-correlation-shock-how-march-2026-broke-and-reshaped-a-popular-vol-trade. Fixed-income return dispersion widening in 2026: am.jpmorgan.com/sg/en/asset-management/institutional/insights/market-insights/market-updates/bulletins/market-outlook-2026/how-will-fiscal-and-monetary-policies-reshape-fixed-income-in-2026/.


### `rp_single_asset_trend_VNQ_126` (primitive `single_asset_trend`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker=VNQ, lookback=126. Rebalance freq: M.

Rationale: A single-ticker trailing-sign rule only has something to monetize when a KNOWN shock arrives in installments rather than all at once (Hong & Stein's gradual-information-diffusion condition), and US listed real estate is in exactly that state now for a mechanical, calendar-scheduled reason -- this is a claim about flow structure, not about how any strategy has recently performed. The MBA's 2025 CRE Survey of Loan Maturity Volumes (released 2026-02-09) puts 17% ($875bn) of the $5.0tn of outstanding commercial mortgages maturing during 2026 -- 17% of office-backed balances, 13% of multifamily -- and borrowers rolling that paper meet commercial mortgage rates well above the coupons the loans were written at, which is why much of the prior cohort was extended or modified rather than resolved. That flow is non-discretionary and dated: it resolves loan-by-loan across quarters, and each resolution reaches a REIT's NOI, appraisal marks and dividend policy on a reporting cadence rather than on the day the news became knowable. The discount-rate input is being repriced at the same time and from an independent direction: a term-premium-driven bear steepener has the 30y at 5.20% against a 10y at 4.63% as of 2026-08-04 (2s10s widened 81->99bp in the week of 2026-07-27), and the long end is the segment REIT cash flows are discounted against. No direction is forecast here -- the sign rule takes whichever side the resolution actually takes; the claim is only that the adjustment is slow and staggered enough for a trailing sign to track. lookback=126 spans two quarterly maturity cohorts; freq=M matches the quarterly cadence at which the underlying information actually updates, so a finer rebalance would only add turnover against an input that has not changed.

Citation: Mortgage Bankers Association, '17 Percent of Commercial and Multifamily Mortgage Balances to Mature in 2026' (2026-02-09, 2025 CRE Survey of Loan Maturity Volumes): https://www.mba.org/news-and-research/newsroom/news/2026/02/09/17-percent-of-commercial-and-multifamily-mortgage-balances-to-mature-in-2026 -- $875bn (17%) of $5.0tn maturing in 2026, down 9% from $957bn in 2025; $396bn at depositories, $200bn CMBS/CLO/ABS; borrowers facing rates well above original coupons, driving extensions/modifications. Curve levels: https://centralbank.watch/tools/yield-curve/us-yield-curve/ and https://fractionalx.com/blog/what-the-yield-curve-is-actually-telling-us-in-2026 (30y 5.20% / 10y 4.63% at 2026-08-04; bear steepening attributed to term premium on fiscal supply, not to easing expectations). Mechanism: Hong & Stein (1999), 'A Unified Theory of Underreaction, Momentum Trading and Overreaction in Asset Markets', Journal of Finance 54(6), 2143-2184 -- gradual information diffusion as the precondition for trend persistence.


### `rp_asset_class_trend_hedge_SPY_IEF_252_63` (primitive `asset_class_trend_hedge`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=SPY, ticker_b=IEF, lookback_a=252, lookback_b=63. Rebalance freq: W.

Rationale: Equity/duration offset structurally restored by falling inflation volatility. Through 2026 stocks and bonds have largely moved TOGETHER, with bonds acting as a risk accelerator rather than a hedge; the sign flip dates to 2021 and is driven by inflation surprises, which push equity and Treasury prices the same way (Nationwide; AQR/Morningstar on the inflation-regime dependence of the correlation sign). The structural condition is now changing: 3-year realized inflation volatility has fallen to its lowest level since spring 2020 -- historically associated with modestly NEGATIVE stock/bond correlation -- and the Fed is the only major central bank still easing (BlackRock). SPECIFIC MECHANISM expected to make the two legs offset: growth shocks, not inflation shocks, are what produce flight-to-quality, so an equity downtrend driven by a growth shock coincides with an intermediate-Treasury uptrend as the front end reprices toward cuts. That channel is an offset; the inflation channel is co-movement, which is why the offset was suspended 2021-2025 and why falling inflation vol is the structural trigger to test it now. Lookbacks are asymmetric by argument, not tuning: the equity leg gets 252d because the growth cycle is the slow-moving variable, the IEF leg gets 63d because flight-to-quality repricing plays out over weeks, so ~one quarter is the horizon at which the Treasury leg registers a shock at all; weekly rebalance follows the faster leg. Rates context: 2Y 4.21 / 10Y 4.63 / 30Y 5.20 as of 2026-08-04, 2s10s ~50bp against a 100-150bp typical-expansion range, so the front end has room to rally on a growth shock. HONEST CAVEATS, stated before the verdict: (1) the calibration window 2007-2017 sits inside the PRIOR negative-correlation regime so the mechanism should be checkable there, but both legs were in secular uptrends across most of it, so the two trend SIGNS may fail the |corr|<=0.3 cap -- that would be a fair mechanical rejection, not a bug; (2) this shape is close to a trend-following 60/40, and gate 2 should punish it if there is nothing here beyond benchmark beta. No performance claim about any live strategy informed this choice; primitive picked partly because asset_class_trend_hedge is tied for least-proposed all-time (2 uses) and no equity-vs-rates pair has been proposed under it.

Citation: https://www.nationwide.com/financial-professionals/blog/markets-economy/articles/stocks-and-bonds-are-moving-together-now-what-for-portfolios (stocks and bonds moving together in 2026; bonds a risk accelerator since 2021); https://www.blackrock.com/us/financial-professionals/insights/bonds-offer-more-diversification (3-yr inflation volatility lowest since spring 2020, a level associated with modestly negative stock/bond correlation; Fed easing); https://www.aqr.com/Insights/Research/Journal-Article/A-Changing-Stock-Bond-Correlation and https://www.morningstar.com/portfolios/what-higher-inflation-means-stock-bond-correlations (inflation regime drives the correlation sign); https://centralbank.watch/tools/yield-curve/us-yield-curve/ (2Y 4.21 / 10Y 4.63 / 30Y 5.20 as of 2026-08-04); https://convextrade.com/metrics/bamlh0a0hym2 (Fed easing, 2s10s re-steepened, bond volatility dormant as of Jul 30 2026)


### `rp_curve_carry_126` (primitive `curve_carry`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: lookback=126. Rebalance freq: W.

Rationale: FIRST curve_carry PROPOSAL EVER -- the primitive has 0 uses in pipeline_ideas.csv against static_spread_carry 6 / pair_zscore 4 / asset_class_trend_hedge 3 / single_asset_trend 3 / cross_sectional_rank 2, and no graveyard.csv row in this lab has ever used real yield-curve data at all. Structural-conditions claim ONLY: I make no assertion about how any live strategy has recently performed, and no direction is forecast -- curve_carry's direction is mechanical (sign of the trailing slope change), not chosen by me. THE STRUCTURAL SETUP. The 2s10s slope is currently being moved almost entirely from the LONG END, not the front end. Front end: the FOMC has held the funds target at 3.50-3.75% at every 2026 meeting after three cuts in late 2025, and the June 16-17 minutes record a genuinely two-sided committee -- many participants judged the appropriate year-end rate to be within or slightly below the current range, many others above it. A split committee on hold pins the front end: 2y 4.21% on 2026-08-04 against a 3.50-3.75% target. Long end: 10y 4.63%, 30y 5.20%, 2s10s ~42bp -- un-inverted but far below the 100-150bp typical of a healthy expansion, with the 3m10y only just back below zero. What movement the slope has is coming from term premium: the NY Fed ACM 10y term premium was 0.79% on 2026-07-30, at or near its highest in a decade, after QT formally ended 2025-12-01 and with heavy coupon issuance still to be absorbed. WHY THAT FAVORS A TREND-FOLLOWING SLOPE SIGNAL, mechanically. The two channels that generate slope variance have different persistence. Front-end policy repricing is jumpy and event-driven -- it moves in discrete steps around eight scheduled FOMC meetings and single data prints, and partly reverses when a print is revised. Term premium is a stock, not an event: it is the compensation required to absorb a duration supply/demand imbalance, and it reprices through flows over quarters (balance-sheet runoff ending, the refunding calendar, the fiscal path) -- the preferred-habitat channel Vayanos-Vila formalize and the 2023 FEDS Note documents empirically, where a yield rise was driven by term premium from QT plus greater issuance plus outlook uncertainty rather than by the expected policy path. A slope whose variance is dominated by the term-premium channel should therefore be MORE autocorrelated -- more trend-like -- than one dominated by front-end repricing. That is a claim about the CONDITIONS for trend persistence in the slope, not about anything's track record, and it is exactly the condition a sign-of-trailing-slope-change signal needs. It is also why this belongs to the carry-generalization line rather than being a duration bet: DV01-neutral legs mean a parallel level shift roughly cancels and the position isolates curve SHAPE, which is the quantity the term-premium channel actually moves. LOOKBACK 126, ARGUED NOT TUNED. The persistent channel's clock is Treasury's quarterly refunding cycle (Feb/May/Aug/Nov) and the balance-sheet/supply process; the jumpy channel's clock is the ~6-week FOMC cadence, ~32 trading days. To be dominated by the first and not the second, the window must span at least one full refunding cycle and be a large multiple of the FOMC cadence: 126 trading days is ~6 months, ~two refundings, ~four FOMC meetings, ~4x the FOMC cadence. The ACM prints themselves argue for the long end of the pre-registered range rather than the short: 0.667% (May 2026) -> 0.513% (June) -> 0.79% (2026-07-30) is a lot of month-to-month movement, so a 20-60 day window would have its sign set by term-premium noise rather than by the supply/policy process the thesis is about. freq W because the signal's own clock is quarters: a weekly rebalance picks up a sign flip within days of it happening without paying daily two-leg turnover on a position that changes a handful of times a year; M could miss a flip by up to a month, D pays cost for a signal that rarely moves. WEAKNESSES, STATED BEFORE THE VERDICT, WORST FIRST. (1) This is still a trend follower, and every trend strategy this lab has tested is DEAD -- the tsmom and green-line books, family L's hourly trend, ~35 donchian_gen_* factory draws. Applying the same sign-of-trailing-change shape to curve data instead of price data changes the INPUT, not the shape, and the entire burden is on the input being different in kind. It may not be, and that is the single best reason to expect this to die. (2) The calibration window 2007-2017 is unusually favorable to slope trend-following in a way the 2018+ window is not: it contains one enormous bull steepening (2008 into ZIRP) and one long, near-monotonic flattening (2014-2017, taper to liftoff). DOCTRINE v1.9's prelim screen is calibration-only and deliberately lenient, so a PASS here could easily be regime-specific and should not be read as support for the thesis -- the OOS gate is the only thing that decides. (3) The DV01 weights use FROZEN durations (TLT 16.0 / IEF 7.5, verified from the 2026-08 range) applied back to 2007-2017, when TLT's effective duration ran materially longer in the ZIRP years; the hedge may be less neutral in calibration data than on paper. That is precisely what pipeline.curve_carry_hedge_is_effective()'s |corr(position returns, dDGS10)| <= 0.3 guard exists to catch, and if it rejects this candidate that is the guard working, not a bug. (4) With 2s10s at only ~42bp and the 3m10y just below zero, the slope has little room to flatten before re-inverting, so the near-term excursion distribution is truncated on one side -- this affects live behavior more than the 2018+ OOS test, but it is a real limit on the thesis as a forward claim.

Citation: Front-end/policy: Federal Reserve, FOMC statement 2026-07-29 (federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm) -- target range held at 3.50-3.75%; FOMC minutes, June 16-17 2026 (federalreserve.gov/monetarypolicy/fomcminutes20260617.htm) -- participants split on whether the appropriate year-end rate is below or above the current range. Curve levels: centralbank.watch/tools/yield-curve/us-yield-curve/ -- 2y 4.21% / 10y 4.63% / 30y 5.20% as of 2026-08-04, 2s10s ~42bp, below the 100-150bp typical-expansion range, 3m10y just below zero. Term premium level: NY Fed ACM 10-year Treasury term premium -- 0.667% (May 2026), 0.513% (June 2026), 0.79% as of 2026-07-30 (ceicdata.com/en/united-states/treasury-term-premia/acm-10-year-treasury-term-premium; FRED THREEFYTP10, fred.stlouisfed.org/series/THREEFYTP10); Capital Economics, 'Measuring Treasury term premia' -- the 10y term premium sits at roughly its highest level in a decade. Underlying decomposition: Adrian, Crump & Moench (2013), 'Pricing the Term Structure with Linear Regressions', Journal of Financial Economics 110(1). Term-premium/supply mechanism: Federal Reserve FEDS Note, 'The Treasury Tantrum of 2023' (federalreserve.gov/econres/notes/feds-notes/the-treasury-tantrum-of-2023-20240903.html) -- the yield rise was driven by term premium from QT, greater Treasury issuance and outlook uncertainty rather than the expected policy path; Vayanos & Vila, 'A Preferred-Habitat Model of the Term Structure of Interest Rates', Econometrica 89(1) (2021) -- duration supply/demand as the term-premium channel. QT end date: PIMCO Macro Signposts, 'Why the Fed Could Shrink Its Balance Sheet Again' and St. Louis Fed, 'The Declining Convenience Yield and Quantitative Tightening' (Feb 2026, stlouisfed.org/on-the-economy/2026/feb/declining-convenience-yield-quantitative-tightening) -- QT formally stopped 2025-12-01. Leg durations (frozen, not re-derived): iShares TLT ~15-16.5yr and IEF ~7-8yr effective duration, mid-2026 fund pages -- the pre-registered TLT_DURATION=16.0 / IEF_DURATION=7.5 in src/tradefabe/pipeline.py. In-repo pre-registration: STRATEGIES.md, 'Vocabulary expansion -- curve_carry added 2026-08-05', and docs/superpowers/specs/2026-08-04-carry-generalization-design.md (Phase 2). Prior-art caveat basis: graveyard.csv trend rows (tsmom_12m, green_line_200d, family L, donchian_gen_*), all DEAD.


### `rp_cross_sectional_rank_low_vol_63_3` (primitive `cross_sectional_rank`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: metric=low_vol, lookback=63, k=3. Rebalance freq: W.

Rationale: Cross-sectional low-volatility (the leverage-constraint / betting-against-beta mechanism: constrained investors bid up high-vol exposure, so the low-vol side of a cross-section is overcompensated per unit of risk) has a structural precondition -- the cross-section must actually have wide, persistent dispersion in realized vol for the ranking to separate anything. That precondition is unusually well met right now, and for asset-class-level structural reasons rather than one idiosyncratic event. The rates end of this universe is at its calmest in years: the MOVE index has been running in the low-60s-to-70s (lowest since 2021) with 3m expiry options on 10y swaps implying ~66bp annualised, because the policy path is priced even through the Fed's hawkish shift under Chair Warsh. The commodity end is at the opposite extreme: the Hormuz closure and naval blockade drove Brent up 13.5% in two days in July 2026 (~50% above pre-conflict in real terms by March), and precious metals set records for intraday dislocation on 2026-01-30 (silver ~-37%, gold ~-12% in a single session), with silver's YTD realized vol up 106% vs gold's 46%. A 15-ticker universe spanning IEF/LQD at one end and USO/SLV/DBC at the other therefore has a vol spread driven by two independent macro forces (an anchored policy path vs an energy supply shock), which is the regime where a vol ranking is most likely to be measuring something structural rather than noise. lookback=63 is the standard quarterly realized-vol estimate -- long enough for a stable daily-vol estimate, short enough that vol clustering (which decays over weeks to months) is still informative rather than averaged away. k=3 of 15 keeps each side a genuine tail of the ranking; k>=4 would tend to hold the entire rates bucket against the entire commodity bucket and collapse into a static asset-class bet rather than a vol ranking. freq=W matches the signal's own speed: a 63d vol ranking barely moves day to day, so daily rebalancing pays turnover for churn, while monthly lags regime shifts of the kind that occurred twice already this year. Chosen partly because low_vol is the one cross_sectional_rank metric never proposed here (0 of 19 prior proposals) and the primitive itself is under-used (2 of 19), so the vocabulary's breadth gets explored rather than re-parameterized. Prior expectation is still low: every predictive strategy in this lab is DEAD, and a defensive-anomaly family has already been killed once.

Citation: Rates vol at multi-year lows: Cboe, 'Rates Volatility Nears 1-Year Low Ahead of FOMC' (https://www.cboe.com/insights/posts/rates-volatility-nears-1-year-low-ahead-of-fomc/); Seeking Alpha, 'GOVT: Treasury Volatility Falls To Multi-Year Lows Ahead Of Fed Rate Cuts' (https://seekingalpha.com/article/4813761-govt-treasury-volatility-falls-to-multi-year-lows-ahead-of-fed-rate-cuts); MOVE level (https://convextrade.com/metrics/move-index). Commodity vol extremes: Chicago Fed, 'The Aftermath of the 2026 Oil Shock' (https://www.chicagofed.org/publications/chicago-fed-letter/2026/523); Vanguard, 'Oil shock complicates central bank outlooks' (https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/oil-shock-complicates-central-bank-outlooks.html); WisdomTree, 'Gold and Silvers' Most Volatile Day' (https://www.wisdomtree.com/us/insights/blog/gold-and-silvers-most-volatile-day); Bold Precious Metals, 'Gold & Silver Market Volatility February 2026 Deep Dive' (https://www.boldpreciousmetals.com/news/gold-silver-market-volatility-february-2026). Mechanism: Frazzini & Pedersen (2014), 'Betting Against Beta', J. Financial Economics 111(1); Blitz & van Vliet (2007), 'The Volatility Effect', J. Portfolio Management.


### `rp_asset_class_trend_hedge_VNQ_DBC_189_63` (primitive `asset_class_trend_hedge`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=VNQ, ticker_b=DBC, lookback_a=189, lookback_b=63. Rebalance freq: W.

Rationale: Structural configuration, not a track-record claim -- I assert nothing about how VNQ, DBC, real assets or any trend strategy has recently performed, and both legs are two-sided sign rules, so nothing here is a directional bet. THE MECHANISM I EXPECT TO MAKE THE TWO LEGS OFFSET, which is what this primitive requires me to name specifically. A nominal Treasury yield decomposes into a real yield and an inflation breakeven. VNQ and DBC are both real assets, but each is levered to a DIFFERENT term of that decomposition, and with opposite sign. Listed REITs are long-duration claims on lease-based cash flows, so their discount rate is the REAL yield: a rise in real yields re-rates them down more or less mechanically, independent of what inflation is doing. Broad commodities are the physical goods whose spot prices ARE a large part of the headline inflation the BREAKEVEN prices; DBC is an energy-heavy basket (WTI, Brent, heating oil, RBOB, natural gas, alongside metals and grains), so it trends with the inflation impulse itself. That gives two distinct, opposite-signed transmission channels rather than one inverse relationship: (a) a SUPPLY-driven inflation shock raises commodity prices directly (DBC leg trends up) while passing into headline inflation, raising nominal and then real policy-rate expectations, which is a headwind to the rate-sensitive real estate leg (VNQ trends down); (b) a DEMAND/growth slowdown does the reverse -- commodity demand and prices fall (DBC down) while real yields fall and REITs' stable, lease-based, largely domestic cash flows re-rate up (VNQ up). Because the two channels are different economic shocks rather than a single common factor with a sign flip, this is not a mechanical inverse pair, and its offsetting behaviour is conditional on which shock dominates. That distinction is the whole point: a mechanically anti-correlated pair would be one position wearing two tickers, whereas two channels that dominate in different regimes is what a hedge is supposed to look like -- and it is also why I expect this to clear the calibration-window decorrelation cap rather than fail it as a disguised single bet, since 2007-2017 contained both shock types (the 2008 demand collapse, the 2010-11 commodity boom, the 2014-15 oil-supply bust, and the whole disinflationary REIT re-rating) rather than one regime repeated. WHY THIS CONFIGURATION IS LIVE RIGHT NOW, which is what makes the two channels currently distinguishable rather than an abstraction. The market is presently pricing exactly channel (a), and pricing it as a term-structure phenomenon rather than a level one: the 10-year breakeven sits around 2.24-2.28% (July 2026), squarely inside the 2.0-2.6% band it has held since 2024, while the 5-year breakeven is roughly 18bp ABOVE the 10-year -- an inverted breakeven curve. That inversion is the precise signature of a near-term supply shock priced in with long-run anchoring intact, which is the state in which the two legs should diverge most. The supply shock is identified and dated: conflict-driven disruption of the Strait of Hormuz cut global supply sharply, lifting Brent about 65% (~$46/bbl) by end-March 2026 -- the largest monthly rise on record -- with further tanker attacks and strikes in early July 2026, and the EIA revising its 2026 Brent average from $58 to $79 in a single month. Meanwhile the 10-year TIPS real yield is around 2.3%, historically high, so the REIT leg's discount rate is under pressure at the same moment the commodity leg's driver is spiking. Sell-side framing of the same configuration is explicit that supply-driven inflation skews the risk toward DELAYED Fed easing, 'limiting support for rate-sensitive, cyclical sectors such as Financials and Real Estate', while noting REITs are relatively well positioned in lower-growth, higher-uncertainty states -- i.e. the same two channels, named by someone else. I am NOT proposing to trade that view: the candidate takes whatever sign each leg's own trailing return gives it. The current configuration matters only as evidence that the two channels are economically real and currently separable, which is the claim this primitive asks me to make and have checked. WEAKNESSES, STATED PLAINLY RATHER THAN APPENDED. (1) The dominant prior is against this: trend is the deadest family in this lab -- tsmom_*, tsmom_gen_*, donchian_*, green_line_200d are all DEAD against these same gates -- and combining two trend legs does not create edge that neither leg has. If both legs are individually unpredictable, pairing them produces a lower-variance nothing, which gate 1's DSR/CPCV test should and will reject. (2) The hedge argument is about RISK, not return; doctrine gate 2 asks whether a candidate earns its place, and a candidate whose only virtue is decorrelation is exactly the case the unapproved v1.1 diversifier clause would have been needed to rescue -- it is not approved, so this must clear the bar on its own. (3) DBC is a futures-basket ETF: its return embeds roll yield, so a leg that is long commodities much of the time collects or pays contango/backwardation independent of trend, and neither this primitive nor the gates separate the two. (4) VNQ's rate sensitivity is a well-known factor exposure, so the REIT leg may be a levered duration bet in disguise rather than a real-estate one. (5) The 2018-present OOS window contains the March 2020 shock, where both legs collapsed together and the claimed offset would have failed exactly when it mattered -- the single most likely way this dies for the right reason. PARAMETERS, DERIVED NOT SEARCHED. lookback_a=189 trading days (~9 months) for VNQ: cap-rate and discount-rate re-rating in listed real estate works through three quarterly reporting cycles and lags the rate move that causes it, so a window shorter than that reads noise and one at the 252 cap averages the re-rating away. lookback_b=63 (one quarter) for DBC: energy supply shocks pass into prices and into headline inflation within weeks, so the commodity leg's driver operates on a much faster clock than the real estate leg's -- the mismatch is the mechanism, not a fitted choice. freq=W is set by the FASTER leg: a 63-day sign can flip on any session, and a monthly clock would act up to ~21 trading days late on it (a third of that leg's own horizon), while weekly holds the lag under ~8%. Turnover cost is bounded regardless of cadence because a sign that does not flip generates no trade. DISTINCTNESS. No graveyard.csv row pairs real estate against commodities: the DEAD tsmom_*/ tsmom_gen_* families trend all 15 UNIVERSE tickers as a single ensemble in which VNQ and DBC are 1/15 each and net against thirteen others, so this two-leg structure has never been isolated. In this ledger the three prior asset_class_trend_hedge proposals are SPY/GLD, TLT/DBC and SPY/IEF -- every one of them anchors on an equity or rates leg, and none touches real_estate, which is the asset class with the fewest appearances here. The one prior VNQ proposal, rp_single_asset_trend_VNQ_126, is a different primitive at a different lookback, and rp_static_spread_carry_VNQ_IEF_a is a static always-on spread with no trend component; neither leg of this candidate duplicates an existing spec. Chosen partly for that breadth -- asset_class_trend_hedge is under-used (3 of 21 prior proposals against static_spread_carry's 6) -- but the mechanism above is the reason, not the tally.

Citation: PROVENANCE NOTE FIRST, since it is load-bearing: this session's fetcher received HTTP 403 from cohenandsteers.com, ssga.com, blogs.worldbank.org and fred.stlouisfed.org, so the figures below are what I read in indexed search results for those sources, not pages I retrieved in full. Flagged as the weakest link in this citation rather than presented as direct reads. BREAKEVEN AND REAL-YIELD LEVELS. 10-year breakeven inflation 2.24% (July 2026, Federal Reserve data) and 2.28% as of 2026-07-23: FRED series T10YIE (https://fred.stlouisfed.org/series/T10YIE), via Trading Economics' US 10-Year Breakeven Inflation Rate page (https://tradingeconomics.com/united-states/10-year-breakeven-inflation-rate-fed-data.html) and Convex, '10Y Breakeven Inflation: 2.28% (Jul 23, 2026)' (https://convextrade.com/metrics/t10yie). The 18bp inverted breakeven curve (5Y above 10Y), read as near-term supply-driven inflation priced in while long-run anchoring holds, and the 2.0-2.6% stability of the 10Y breakeven through 2024-2026: same Convex and Trading Economics coverage. 10-year TIPS real yield ~2.3% and 2-year ~2.1% as of July 2026: Saving to Invest, 'TIPS in 2026 -- Current Real Yields and Whether They Still Make Sense' (https://savingtoinvest.com/how-and-why-to-buy-treasury-inflation/) -- retail commentary, the weakest source here, cross-read against Macrotrends' 10-Year TIPS Yield series (https://www.macrotrends.net/5061/10-year-tips-yield). THE SUPPLY SHOCK ITSELF. Strait of Hormuz disruption as the largest oil-market supply shock on record, Brent up ~65% (~$46/bbl) by end-March 2026, its largest monthly rise ever: World Bank Blogs / Open Data, 'Strait of Hormuz disruption sends oil prices surging' (https://blogs.worldbank.org/en/opendata/strait-of-hormuz-disruption-sends-oil-prices-surging). EIA lifting its 2026 Brent average forecast from $58 to $79/bbl in one month: 'Oil Shock Lifts EIA Price Outlook as Hormuz Crisis Reshapes Forecast' (https://finance.yahoo.com/news/oil-shock-lifts-eia-price-173000464.html). Continuation into July 2026 (tanker attacks in the Strait, revoked Iran sale authorization, US strikes): CNBC, 'Oil prices rise after attacks on tankers in Strait of Hormuz' (https://www.cnbc.com/2026/07/07/oil-prices-iran-strait-hormuz.html) and Al Jazeera, 'Oil surges as US strikes Iran, reversing return to pre-war prices' (https://www.aljazeera.com/news/2026/7/8/oil-prices-surge-as-us-strikes-iran-reversing-fall-to-pre-war-levels). THE TWO-CHANNEL FRAMING, NAMED BY OTHERS. Supply-driven inflation skewing risk toward delayed Fed easing and thereby 'limiting support for rate-sensitive, cyclical sectors such as Financials and Real Estate', alongside energy shocks passing quickly into headline inflation and REITs being relatively well positioned in lower-growth, higher-uncertainty states on stable lease-based cash flows with limited trade exposure: State Street Global Advisors, 'Sector Market Perspectives: Q2 2026' (https://www.ssga.com/us/en/individual/insights/sector-market-perspectives-q2-2026) and 'Real assets insights: Q2 2026' (https://www.ssga.com/us/en/individual/insights/real-assets-insights). Falling real yields plus rising breakevens as the historically favourable state for real assets, with a 2026 year-end real-yield target of 1.75%, and the listed-REIT-versus-private-real-estate valuation gap being the longest since the early 2000s: Cohen & Steers, 'Real assets year-in-review & 2026 outlook' (https://www.cohenandsteers.com/insights/real-assets-year-in-review-2026-outlook-us/). INSTRUMENT CONSTRUCTION, which the mechanism depends on. DBC tracks the DBIQ Optimum Yield Diversified Commodity Index of 14 futures -- WTI crude, Brent crude, heating oil, RBOB gasoline, natural gas, gold, silver, aluminum, zinc, copper, corn, wheat, soybeans, sugar -- an energy-heavy basket held via futures, hence the roll-yield confound flagged in the rationale: Invesco DB Commodity Index Tracking Fund product page (https://www.invesco.com/us-rest/contentdetail?contentId=1fd207c649400410VgnVCM10000046f1bf0aRCRD&dnsName=us) and etf.com's DBC profile (https://www.etf.com/DBC). PRIORS CITED AGAINST THIS CANDIDATE. Cieslak & Pflueger, 'Inflation and Asset Returns', NBER Working Paper 30982 (https://www.nber.org/system/files/working_papers/w30982.pdf) -- the supply-versus-demand decomposition of inflation shocks is the source of the two-channel argument here, and the same paper is the reason to expect the two channels to co-move rather than offset during a common risk shock. 'Good' Inflation, 'Bad' Inflation: Implications for Risky Asset Returns, Federal Reserve FEDS 2025-002 (https://www.federalreserve.gov/econres/feds/files/2025002pap.pdf) -- same caution. Man Group, 'What Would Inflation Do to Risk Assets?' (https://www.man.com/insights/what-would-inflation-do-to-risk-assets) on real assets' inconsistent inflation hedging out of sample.


### `rp_cross_sectional_rank_momentum_252_4` (primitive `cross_sectional_rank`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: metric=momentum, lookback=252, k=4. Rebalance freq: M.

Rationale: Cross-sectional dispersion ACROSS asset-class blocks is structurally wide entering H2 2026, and the source is nameable rather than a performance observation. An energy supply shock (Strait of Hormuz closure, Brent ~$86/bbl late July 2026) has re-ignited headline inflation into a Fed that has stopped easing -- Warsh dismantled forward guidance and hikes are not ruled out, with long-bond yields ~5.275% -- so the same shock pushes the commodity block (DBC/USO) and the duration block (TLT/IEF/LQD) in OPPOSITE directions simultaneously. On top of that, commodities and gold have decoupled from both equities and bonds on supply-chain realignment, geopolitical hedging demand and central-bank buying, and non-US equity (EFA/EEM) has disconnected from US large caps on local growth cycles rather than shared beta. A long-top-K / short-bottom-K rank over the full 15-ETF UNIVERSE is the only primitive in the vocabulary that expresses 'harvest the gap between asset-class blocks' without naming the trade in advance -- if the mechanism is real the ranking should end up long commodities / short duration on its own, and if it is not, it should not. Parameters are set from the driver's horizon, not the recent tape: lookback=252 because every cited driver is multi-quarter and structural (supply deficits, a policy-regime change, central-bank gold demand), deliberately distinct from the 126d ranking already proposed 2026-08-05; k=4 of 15 so each leg spans a whole asset-class block rather than one ticker's idiosyncratic move, which is the granularity at which the cited decoupling actually operates; freq=M matches the same slow horizon and keeps turnover honest against the duty-cycle-matched null. Prior evidence in this lab is AGAINST this shape -- cross-sectional momentum is already DEAD in graveyard.csv -- so this is proposed as a different window and granularity under a regime whose dispersion source is identifiable, not as a re-run expecting a different answer. cross_sectional_rank is also the second-least-used primitive in pipeline_ideas.csv (3 of 24 rows before this one).

Citation: Vontobel AM, '2026: Multi Asset Reloaded -- Investors (Still) Need Diversification' (rising cross-asset dispersion; commodities and gold decoupled from equities and bonds on supply-chain realignment and hedging demand): https://am.vontobel.com/en/insights/2026-multi-asset-reloaded-investors-still-need-diversification | iShares 'Investment Directions 2026 Outlook' (greater performance dispersion as capital rotates; regional equities disconnected from US large caps): https://www.ishares.com/us/insights/inside-the-market/2026-market-outlook-investment-directions | State Street, 'Gold 2026 Midyear Outlook' and Goldman Sachs '2026 Commodities Outlook' (2026 oil supply shock, Brent ~$86, energy-driven inflation, gold vs real yields tension, industrial-metal supply deficits): https://www.ssga.com/us/en/intermediary/insights/gold-2026-midyear-outlook-a-tug-of-war-between-tactical-and-structural-momentum and https://www.goldmansachs.com/pdfs/insights/goldman-sachs-research/2026-outlooks/CommoditiesOutlook2026.pdf | centralbank.watch US yield curve (2026-08-04: 2y 4.21%, 10y 4.63%, 2s10s ~42bp, steepening off 27bp in late June): https://centralbank.watch/tools/yield-curve/us-yield-curve/


### `rp_curve_carry_252` (primitive `curve_carry`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: lookback=252. Rebalance freq: M.

Rationale: The 2s10s slope's current re-steepening is driven by two structurally distinct, slow-moving forces that push the same way and both run on a multi-quarter clock, not a meeting-to-meeting one. (a) The front end is being pulled down by a measured, multi-year easing cycle -- 175bp of cuts since Sep 2024 to a 3.50-3.75% target, with consensus for roughly 3.00-3.25% by end-2026 -- so DGS2 steps down slowly and predictably. (b) The long end is held up by a positive and rising term premium sourced from fiscal supply: $2T+ annual deficits plus balance-sheet runoff force private absorption of a growing share of long-dated paper against foreign official demand that has plateaued since 2014, so DGS10 does not follow the front end down. The result is a normalization that is explicitly mid-course rather than finished: 2s10s un-inverted in Sep 2024, only achieved a sustained positive slope across tenors in Q4 2025, and sat at roughly 42bp on 2026-08-04 (DGS2 4.21%, DGS10 4.63%) -- still well below the 100-150bp range typical of a normal expansion. curve_carry trend-follows this slope with a DV01-neutral TLT/IEF position, so the only real choice here is which timescale of slope change the signal measures. Both prior pipeline curve_carry proposals sample the short end of the pre-registered range (63d, 126d), which resolves the FOMC/CPI/auction repricing sitting ON TOP of the normalization rather than the normalization itself; 252d -- the top of the range -- measures slope change over a full year, matching the clock of the two drivers above. Monthly rebalance is the honest turnover match for a signal whose sign at a 252d lookback changes on a quarters-to-years cadence. Proposed as a structural hypothesis about a mechanism and its timescale, not from any claim about slope trades' recent results -- a year-scale slope trend this widely narrated may well already be priced, which is what the OOS gate is for.

Citation: https://centralbank.watch/tools/yield-curve/us-yield-curve/ (2s10s ~42bp on 2026-08-04; DGS2 4.21%, DGS10 4.63%); https://ferrantecapitaladvisers.com/insights/treasury-term-premium-regime-2026/ (term-premium regime: supply/demand/risk decomposition, deficits + QT runoff vs plateaued foreign demand); https://fractionalx.com/blog/what-the-yield-curve-is-actually-telling-us-in-2026 (un-inversion driven by term premium, not growth optimism; bear-steepener characteristics); https://markets.financialcontent.com/wral/article/marketminute-2025-12-25-the-great-normalization-what-the-reshaping-yield-curve-foretells-for-2026 (Sep 2024 un-inversion, sustained positive slope only from Q4 2025); https://www.ishares.com/us/insights/fed-outlook-2026-interest-rate-forecast (easing path to ~3.00-3.25% by end-2026)


### `rp_single_asset_trend_EEM_189` (primitive `single_asset_trend`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker=EEM, lookback=189. Rebalance freq: M.

Rationale: Structural composition, not a track-record claim -- I assert nothing about how EEM, trend-following, or any live strategy has recently performed, and a sign rule takes BOTH directions, so nothing here forecasts one. WHY THIS TICKER NOW. EEM is no longer economically the diversified ~1,298-holding emerging-market basket its label implies: as of July 2026 TSMC is 14.88%, Samsung Electronics 5.99% and SK hynix 4.52% of the fund (roughly a quarter of the portfolio in three semiconductor manufacturers), information technology is ~28-30% of the index, and the same three names' combined share of the MSCI EM index itself has crossed 30%. The ticker's dominant fundamental driver has therefore CHANGED -- from broad EM growth/commodity/currency beta to the capacity cycle of the AI semiconductor supply chain -- and that is a composition fact checkable from holdings data, not a view. MECHANISM. A trailing-sign rule monetizes something only when the asset's dominant driver is serially correlated. Contracted manufacturing capacity is serially correlated by industrial construction rather than by sentiment: DRAM capacity is reported effectively sold out through 2026 and into 2027, and TSMC lifted its 2026 capex plan to $60-64bn from $52-56bn. Commitments of that shape fix volume and pricing four to eight quarters forward and then arrive as a pre-scheduled sequence of quarterly guidance updates rather than as one surprise impounded at once. Underneath sits the textbook slow-adjusting capital stock -- a leading-edge fab takes roughly 2-3 years to build -- so the industry's capacity/price cycle over- and under-shoots on a multi-year clock. That persistence is symmetric: an over-capacity downswing is as slow as an upswing, which is why this is a persistence claim and not a bullish one. PARAMETERIZATION. lookback=189 trading days (~9 months) spans three consecutive quarterly capex/guidance updates -- the clock the driver actually runs on -- and is deliberately OFF the 252d/12-month momentum convention so this is not a single-asset restatement of tsmom_12m, which is already DEAD in graveyard.csv and holds EEM as one of its legs. Monthly rebalancing matches a quarterly-guidance-driven signal and keeps turnover low against v1.5's duty-cycle-matched null. single_asset_trend is tied for the least-used primitive in this ledger (4 rows against static_spread_carry's 7) and its four existing draws are GLD/SLV/VNQ/UUP at 63d or 126d; both EEM and the ~9-month window are untested here, and graveyard.csv contains no EEM row of any kind. WHAT CUTS AGAINST IT. The concentration that gives the driver its persistence also makes this a single-supply-chain bet wearing an EM label: a Taiwan/Korea geopolitical event, an export-control change, or one company's process failure would dominate the signal, and none of those are serially correlated at all -- the diversification the 'EM' label implies is largely gone, and that concentration is itself being flagged as an index-level risk. Prior probability stays low on this lab's own record: 139+ strategies tested, 0 ALIVE predictive, and four sibling single-asset trend rows already rest on a related slow-moving-driver argument.

Citation: EEM holdings and weights, July 2026 (TSMC 14.88%, Samsung Electronics 5.99%, SK hynix 4.52%, Tencent 3.29%, Alibaba 2.12%; ~1,298 holdings): https://stockanalysis.com/etf/eem/holdings/ . Combined TSMC+Samsung+SK hynix share of the MSCI EM index above 30%, with an explicit index-concentration warning (2026-07-13): https://www.digitaltoday.co.kr/en/view/80795/tsmc-samsung-electronics-sk-hynix-share-in-msci-emerging-markets-index-tops-30-percent-warning-on-semiconductor-concentration and https://www.cryptopolitan.com/tsmc-samsung-sk-hynix-now-control-30-of-em/ . Sector mix (~28-30% information technology, top-10 ~33% of assets) is from fund-profile summaries of the iShares EEM fact sheet dated 2026-06-30: https://www.ishares.com/us/literature/fact-sheet/eem-ishares-msci-emerging-markets-etf-fund-fact-sheet-en-us.pdf . SOURCING CAVEAT: that iShares PDF and stockanalysis.com both returned HTTP 403 to this run's direct fetch, so the weights above are as surfaced in search results, and sources disagree slightly (TSMC quoted between ~13% and ~15.05%, SK hynix between ~3% and ~7.6%); the claim used here needs only 'three semiconductor names are roughly a quarter to a third of the index', which every source agrees on. DRAM capacity effectively sold out through 2026 and into 2027, HBM-led memory cycle: https://news.skhynix.com/2026-market-outlook-focus-on-the-hbm-led-memory-supercycle/ . 2026 semiconductor market forecast $1.29T led by AI infrastructure and memory: https://www.idc.com/resource-center/blog/semiconductor-market-to-surge-past-the-trillion-dollar-threshold-ai-infrastructure-drives-market-growth/ . TSMC 2026 capex raised to $60-64bn from $52-56bn, and foundry/HBM/packaging capacity additions cascading across one constrained manufacturing ecosystem: https://techchannel.news/how-capex-chips-and-geopolitics-rewired-semiconductor-value-chain-in-2026/ and https://www.franklintempleton.com/articles/2026/clearbridge-investments/can-ai-capex-extend-the-semiconductor-cycle . Structural EM-allocation backdrop (EM at ~5.2% of global equity fund AUM against >11% MSCI ACWI weight), used only as context, not as a performance claim: https://www.ssga.com/us/en/individual/insights/emerging-market-equities-outlook-q1-2026 .


### `rp_cross_sectional_rank_momentum_63_3` (primitive `cross_sectional_rank`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: metric=momentum, lookback=63, k=3. Rebalance freq: M.

Rationale: Cross-asset return dispersion is at a genuine structural extreme in 2026, and it is wide across exactly the asset classes UNIVERSE spans rather than inside any single one. Concrete instances: the gold/oil ratio sits near 55 (early-2026 readings ~75:1 with gold ~$5,000/oz against oil ~$67/bbl) versus a since-1900 average near 20 and a modern average ~22 -- the far right tail of its whole historical distribution, matched only by April 2020 and the 1980s oil crises; 2026 asset-class performance spans roughly +94.5% (silver) to -20% (natural gas); and fixed income's own 2026 theme is explicitly dispersion 'across sectors, structures, and parts of the curve' rather than a uniform beta-driven opportunity set. Cboe's DSPX implied-dispersion index independently hit a 6-year high of 47% in the week of 2026-07-13, above its April 'Liberation Day' peak -- that one measures single-stock dispersion inside SPY, not cross-asset dispersion, so it is corroborating context here, not the load-bearing fact. Why this matters mechanically for THIS primitive and not as a performance claim: a cross-sectional long-short's gross payoff is the top-K minus bottom-K return spread, which scales directly with the dispersion of the cross-section it ranks. Wide dispersion does not make the ranking correct -- it raises the payoff per unit of ranking accuracy, and equally the loss per unit of ranking error. That is the structural condition; whether momentum ranking has any accuracy at all is precisely what the doctrine's gates are being asked to decide. Why momentum as the metric, and why 63 days: the same 2026 research describes elevated structural breaks across many cross-asset pairs simultaneously (gold rising alongside real yields, the gold/oil ratio at a multi-decade extreme) -- a regime in which each asset is driven by its own idiosyncratic, slow-moving macro driver (central-bank and ETF gold demand, Treasury term premium and supply, an oil supply shock followed by ceasefire reversal) rather than by a common factor. Persistent asset-specific drivers are the structural precondition for the rank ordering itself to persist, which is all cross-sectional momentum bets on. 63 days is the short end of the standard 3-12 month formation window, chosen because the drivers above are turning over fast in a regime transition -- deliberately distinct from the two momentum draws this pipeline has already proposed (126/k=2 on 2026-08-05, 252/k=4 on 2026-08-06); this is a different formation horizon pre-registered on its own reasoning, not a re-run of either. k=3 of 15 tickers keeps both sleeves diversified within an asset class rather than concentrating the whole position in whichever single commodity is at an extreme. Monthly rebalance because a 63-day formation does not justify paying weekly or daily turnover. Honest prior: this lab has already killed cross-sectional momentum (2 graveyard rows under xsec_momentum) and 52 low_vol_xsec rows besides, and no predictive strategy here has ever survived. Nothing above claims this one will; it claims the structural condition that would have to hold for the shape to have any chance currently does hold, which is the most a pre-registration is allowed to claim.

Citation: Cboe Insights, 'Week of 7/13/2026: DSPX Index Jumps to 6-Year High Ahead of Earnings' (cboe.com/insights/posts/week-of-7-13-2026-dspx-index-jumps-to-6-year-high-ahead-of-earnings) -- DSPX 47%, 6-year high, above the April 2026 peak. Gold/oil ratio ~55 vs a since-1900 average near 20 and 'far right tail of its entire historical distribution': cruxinvestor.com, 'Gold-to-Oil Ratio Hits 25-Year Extreme'; gerrardsbullion.com/invest/understanding-the-gold-oil-ratio-what-it-tells-investors-in-2026/; bitmex.com/blog/gold-vs-oil-trade. 2026 asset-class performance span (+94.5% silver to -20.14% natural gas): financialexpertclass.com/2026-etf-performance-winners-losers/. Fixed-income dispersion as 2026's structural theme ('not a uniform beta-driven opportunity set, but one marked by dispersion across sectors, structures, and parts of the curve'): VettaFi/etfdb, 'Beyond the Agg: Dispersion a 2026 Theme in Bond ETFs' (2026-05-06), also at advisorperspectives.com/commentaries/2026/05/07/agg-dispersion-2026-theme-bond-etfs. Simultaneous cross-asset correlation structural breaks (gold vs real yields, gold/oil extreme): ahasignals.com/cross-asset-correlation-dashboard/; PGIM Quantitative Solutions, 'Cross-Asset Correlations in Market Turbulence'.


### `rp_asset_class_trend_hedge_TLT_UUP_189_63` (primitive `asset_class_trend_hedge`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=TLT, ticker_b=UUP, lookback_a=189, lookback_b=63. Rebalance freq: M.

Rationale: A bear-steepening regime has structurally SPLIT the two ends of the US curve, and TLT and UUP are driven by opposite ends of that split -- so their trend legs are driven by different economic segments, not by one shared factor. Long end: the 30s2s spread went 81 -> 99bp in the five sessions to 2026-07-27, and yields past 15y are held above 5% by term premium, Treasury supply and long-run inflation expectations rather than by the expected policy path -- a multi-quarter repricing, hence lookback_a=189 on the rates leg. Front end: short-rate support for the dollar is fading on softening US data (Q2 2026 real GDP 1.5%, June payrolls +57k, core CPI 2.6% from a 4.2% May headline), the 2s10s has re-steepened to about +35bp with effective funds at 3.63%, and DXY sits near 99.5 at a seven-week low with a widened $77.6bn May trade deficit and reserve managers cutting USD holdings -- a repricing that has turned over roughly a quarter, hence lookback_b=63 on the currency leg. The named offsetting mechanism this primitive requires: TLT's trend is a LONG-end term-premium/supply process while UUP's trend is a SHORT-end relative-policy-rate process, and in a steepener those two segments move apart by construction -- the leg that is a duration bet is not implicitly a dollar bet. New to this pipeline on both counts: UUP has never appeared as a leg of asset_class_trend_hedge (prior legs: SPY/GLD, TLT/DBC, SPY/IEF, VNQ/DBC, TLT/GLD), and the primitive has never paired rates against currency. Monthly rebalance because both lookbacks are quarterly-to-multiquarter; under DOCTRINE v1.5b's duty-cycle-matched null a slow signal should not be traded faster than it actually changes.

Citation: HJ Sims Curve Commentary 2026-08-04 (hjsims.com/curve-commentary-august-4-2026/) -- 30s2s 81 -> 99bp in the week of 2026-07-27, long end above 5% past 15y on term premium and long-run inflation expectations; Schwab 2026 Corporate Credit Outlook / StreetStats (schwab.com/learn/story/corporate-bond-outlook, streetstats.finance/rates/corporates) -- effective fed funds 3.63%, 2s10s re-steepened to +35bp, MOVE 74.7; TradingEconomics and Cambridge Currencies DXY 6-month outlook (tradingeconomics.com/united-states/currency, cambridgecurrencies.com/us-dollar-index-dxy-forecast/) -- DXY 99.478 on 2026-08-07 at a seven-week low, US May 2026 trade deficit $77.6bn, Q2 2026 GDP 1.5%, June payrolls +57k, June core CPI 2.6%, Natixis/Morgan Stanley expecting depreciation as short-rate support fades; Continuum Economics DM Rates Outlook (continuumeconomics.com/a/7d576bd6/) -- Fed cuts the front end while long rates follow only grudgingly.


### `rp_single_asset_trend_USO_126` (primitive `single_asset_trend`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker=USO, lookback=126. Rebalance freq: M.

Rationale: Crude oil's forward curve is in a documented, persistent CONTANGO right now, and USO is the one UNIVERSE instrument whose returns are dominated by front-month WTI roll mechanics rather than by spot alone -- DBC is a broad, roll-optimised multi-commodity basket in which the oil curve is diluted, and no other UNIVERSE ticker touches the curve at all. Structural setup as of August 2026: WTI and Brent are in clear contango, dropping roughly $20/bbl between the August 2026 and early-2030s maturities; the IEA's July 2026 Oil Market Report projects a 3.7-4.0 mb/d oversupply and notes global inventories rose at their fastest pace since 2020; the EIA's July 2026 STEO forecasts inventory builds averaging 2.7 mb/d in 4Q26 and 5.0 mb/d through 2027; OPEC has flipped its Q3 call from deficit to surplus. The MECHANISM being tested is not 'trend works' -- this lab has killed every trend strategy it has run, and that prior is taken seriously. It is narrower and specific to this instrument in this regime: USO rolls near-dated WTI futures monthly, so a contango curve makes that roll structurally negative -- it sells the cheaper expiring contract and buys a costlier deferred one, and NAV decays against spot regardless of direction. A trailing-return sign signal is SHORT whenever that decay has already shown up in its window, so in a surplus regime the trend leg and the roll drag point the same way instead of fighting each other; in a balanced or backwardated market they fight, which is the honest reason trend on oil has no general edge. That asymmetry is the testable claim, and the OOS gate decides it, not this rationale. lookback=126 (~6 months) matches the regime's own timescale, which the EIA/IEA forecasts put in quarters-to-years, and is deliberately long enough not to whipsaw on the geopolitical spikes that repeatedly reversed within weeks during 2026 (June's wartime gains were fully erased as Gulf tanker traffic recovered) while still short enough to turn if the surplus resolves. Monthly rebalance for the same duty-cycle reason DOCTRINE v1.5b's matched null exists: a semiannual signal should not be traded faster than it actually changes. New to this pipeline: USO has never been proposed under single_asset_trend (prior legs GLD/SLV/VNQ/UUP/EEM), and its only prior appearances are as the a-leg of static_spread_carry USO/DBC and pair_zscore USO/DBC -- both relative-value against the same basket, neither a directional test of the roll drag itself. On vocabulary breadth: curve_carry is the least-used primitive (4 proposals) but its sole parameter is lookback and 21/63/126/252 are already taken, so a fifth would be near-duplicative; single_asset_trend is tied-lowest among the rest at 5.

Citation: IEA Oil Market Report, July 2026 (iea.org/reports/oil-market-report-july-2026) -- projected 3.7-4.0 mb/d oversupply, global inventories rising at the fastest pace since 2020, sizeable 2026 surplus as supply exceeds demand; EIA Short-Term Energy Outlook, July 2026 (eia.gov/outlooks/steo/report/global_oil.php, eia.gov/outlooks/steo/pdf/steo_full.pdf) -- inventory builds averaging 2.7 mb/d in 4Q26 and 5.0 mb/d in 2027, supply growing faster than consumption; CMB News crude oil market update, July 2026 (commodity-board.com/oil-forward-curve-flattens-as-geopolitics-clash-with-softening-demand, commodity-board.com/wti-curve-softens-as-opec-eases-cuts-and-demand-signals-cool) -- WTI and Brent in clear contango, roughly $20/bbl from August 2026 to early-2030s maturities, structure encouraging storage and capping spot upside despite geopolitical risk; Goldman Sachs 2026 revision via Intellectia crude oil forecast, July 2026 (intellectia.ai/blog/crude-oil-price-forecast-july-2026) -- WTI averaging $52 and Brent $56 on a persistent ~2 mb/d surplus; Discovery Alert oil market structure note (discoveryalert.com.au/oil-market-shift-2025-us-shale-contango/) -- OPEC's Q3 call reversed from supply deficit to supply surplus, backwardation extending only to February 2026 with the November-February spread narrowed to 70 cents.


### `rp_curve_carry_189` (primitive `curve_carry`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: lookback=189. Rebalance freq: M.

Rationale: The 2s10s spread has exited its 2022-2024 inversion but sat at only 0.45% on 2026-08-03 -- positive and well under the 100-150bp slope typical of an expansion -- while the 3m10y has flipped negative again in recent weeks. The two ends are being pushed by two different slow-moving forces rather than by one common level shock: the front end by an expected easing path (the 2y trades roughly 70bp below the policy rate, pricing about 100bp of cumulative cuts by mid-2028), the long end by a term premium rebuilding after five years near or below zero, with Treasury holding nominal coupon auction sizes steady for at least several more quarters even as borrowing needs climb and naming the size and composition of the SOMA portfolio as the swing variable it is positioned for. Both drivers update on a quarterly policy cadence -- refunding statements, SEP revisions, balance-sheet decisions -- and persist between updates, which is the condition a slope trend-follower needs: a slope that drifts rather than oscillates. A 189-day lookback spans roughly three of those quarterly cycles, long enough to average through announcement-day noise and short enough to stay inside the post-inversion regime. curve_carry is the least-used primitive in this ledger (4 of 35 proposals) and the only one reading real FRED curve data rather than ETF prices; nothing in graveyard.csv trades the rates-curve slope, so this is not a re-run of the price-trend space families A/B/D already swept. Distinct from the four curve_carry specs already proposed (21/63/126/252) only in horizon, which is the sole parameter this primitive has -- the quarterly-cadence argument is the reason for this specific value, fixed before any result is known.

Citation: US Treasury Quarterly Refunding Statement, August 2026 (home.treasury.gov/news/press-releases/sb0590): $125bn Aug 11-13 refunding, nominal coupon/FRN auction sizes held steady 'for at least the next several quarters' while borrowing needs climb, with SOMA size and composition named as the variable Treasury is positioned for. 2s10s 0.45% on 2026-08-03 and 3m10y negative again: centralbank.watch/tools/yield-curve/us-yield-curve/. Term-premium framing: Adrian, Crump & Moench (2013), 'Pricing the Term Structure with Linear Regressions', NY Fed ACM series. Mechanism: Moskowitz, Ooi & Pedersen (2012), 'Time Series Momentum', JFE 104(2), which documents trend persistence in fixed-income specifically.


### `rp_static_spread_carry_LQD_IEF_a` (primitive `static_spread_carry`)

**PRE-REGISTRATION — frozen 2026-08-08, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=LQD, ticker_b=IEF, long_leg=a. Rebalance freq: M.

Rationale: Structural, not a track-record claim -- I assert nothing about how LQD, IEF, corporate credit or any live strategy has recently performed, and no timing view is expressed: static_spread_carry holds a FIXED, always-on position, so the hypothesis under test is only whether a persistent risk premium exists, never whether now is a good entry. THE LAST MAJOR RISK PREMIUM IN THIS UNIVERSE NOT YET EXPRESSED BY THIS PRIMITIVE. The eight prior static_spread_carry proposals in this ledger cover the term premium (TLT/IEF), the credit QUALITY-TIER differential (HYG/LQD), the property/cap-rate premium (VNQ/IEF), size (IWM/SPY), EM (EEM/EFA), the commodity front-of-curve roll (USO/DBC), the industrial-vs-monetary metals split (SLV/GLD) and the official-sector reserve rotation (GLD/UUP). None of them is the investment-grade credit premium itself. HYG/LQD is a bet on the tier relationship, and current data says that relationship is the unremarkable part: the HY/IG OAS ratio is near its long-run ~3.5x, i.e. the richness in credit is MARKET-WIDE rather than a tier distortion. Long LQD / short IEF is the only pair this UNIVERSE can form that isolates the market-wide IG premium -- compensation for default, downgrade and illiquidity risk on investment-grade corporate paper, measured against Treasuries of the same maturity bucket. WHY THE PAIR IS DURATION-CLEAN, the load-bearing mechanical point. An IG credit spread is only a credit premium if the rate exposure cancels; otherwise it is a levered duration bet wearing a credit label. LQD's effective duration is 7.97yr against IEF's 7.2yr -- a residual under one year on a base of ~8 -- and engine.py's own sizing closes most of what remains, because it vol-targets EACH leg to TARGET_VOL=10% annualized on a 60-day trailing window rather than holding fixed notionals. Both legs' volatility is dominated by the same Treasury curve, so equal-vol sizing scales them to approximately equal DV01 automatically and the residual is close to a pure spread. No other pair here has that property: family N's pre-registered LQD/HYG carries credit on BOTH legs, and VNQ/IEF deliberately does not hedge duration at all. THE CURRENT STRUCTURAL CONDITION, stated as what makes the test informative rather than as a reason to expect a pass. The ICE BofA US Corporate OAS sits near 80bp -- roughly its tightest in 25 years, against a long-run average near 150bp -- with BBB near 100bp and AA near 50bp, while the broad IG index yield-to-worst has spent 2026 in a 5.0-5.4% range. The premium this candidate harvests is therefore priced at roughly HALF its own historical average. THE SINGLE BIGGEST WEAKNESS, FIRST RATHER THAN BURIED: that thinness is a reason to expect this to FAIL, and it is the honest prior going in. I propose it anyway because waiting for a wider spread would be timing, and this primitive cannot time -- a fixed always-on spread either earns an unconditional premium across the whole OOS window or it does not, and that is precisely the question worth one pre-registered test. Second weakness: the credit premium's payoff is negatively skewed and short-volatility -- long stretches of small spread accrual punctuated by sharp drawdowns -- the same shape as this lab's one surviving carry book, but WEAKER in kind, because crypto funding is a mechanically paid rate while IG spread income arrives net of realized defaults and downgrades that are small, lumpy and correlated with exactly the episodes that hurt the position. WHAT THE OOS WINDOW WILL ACTUALLY DECIDE. 2018-present contains the realizations that should punish this construction if the premium is not real: March 2020, when IG OAS blew out from roughly 100bp to ~370bp and LQD additionally traded at a discount to NAV until the Fed's corporate-credit facilities were announced -- the worst single realization available -- and 2022, when spreads widened while rates rose, so the partial duration residual and the credit leg lost together. If the average premium does not survive those drawdowns net of costs, this should and will die on gate 3 or on gate 2's Calmar test. PRIMITIVE-CHOICE HONESTY: static_spread_carry is the MOST-proposed primitive in this ledger (8 of 37 prior proposals), so this is deliberately not a breadth pick. The justification is that the mechanism is a fixed spread, not a trend, a cross-sectional rank or a curve slope, so no under-used primitive can express it; curve_carry, the least-used, is fixed to TLT/IEF and reads no credit data at all. DISTINCT FROM WHAT ALREADY EXISTS: no graveyard.csv row uses LQD/IEF, and family N's six pre-registered cointegration pairs (GLD/SLV, TLT/IEF, EFA/EEM, SPY/QQQ, USO/DBC, LQD/HYG) do not include it. rp_pair_zscore_LQD_IEF_120_2p0_4p0 touches the same two tickers but tests a different hypothesis about the series -- reversion around a stable mean versus a persistent premium in its drift -- under a different primitive, a different name and its own separate verdict, so neither borrows the other's evidence. freq=M because the position is fixed: the only turnover is the monthly rebalance back to vol-target weights, and monthly is the lowest-turnover clock this primitive offers, which matters directly because gate 1's null is duty-cycle-matched and pays the same trading costs the candidate does.

Citation: Credit levels: PineBridge Investments, '2026 Investment Grade Credit Outlook: At a Turning Point?' (pinebridge.com/en/insights/2026-investment-grade-credit-outlook) -- IG corporate OAS ~80bp, BBB ~100bp, AA ~50bp, near multi-decade tights; investmentgrade.com Investment Grade Bond Market Outlook 2026 -- ICE BofA US Corporate OAS near 80bp, tightest in roughly 25 years versus a long-run average near 150bp, index yield-to-worst in a 5.0-5.4% range through 2026. HY comparison: ICE BofA US High Yield OAS (FRED BAMLH0A0HYM2) 284bp on 2026-07-30 via convextrade.com/metrics/bamlh0a0hym2, putting the HY/IG ratio near its long-run ~3.5x. Underlying series: FRED BAMLC0A0CM (ICE BofA US Corporate OAS). Durations: iShares fund fact sheets -- LQD effective duration 7.97yr, IEF 7.2yr. Mechanism references: Elton, Gruber, Agrawal & Mann (2001), 'Explaining the Rate Spread on Corporate Bonds', Journal of Finance 56(1) -- expected default loss accounts for only a modest share of investment-grade spreads, the residual being a systematic risk premium (the credit spread puzzle); Asvanunt & Richardson (2017), 'The Credit Risk Premium', Journal of Fixed Income 26(3) -- duration-hedged corporate credit excess returns, which is exactly the construction this candidate expresses; Collin-Dufresne, Goldstein & Martin (2001), 'The Determinants of Credit Spread Changes', Journal of Finance 56(6) -- spread changes are driven largely by a common systematic factor rather than issuer fundamentals.


### `rp_single_asset_trend_TLT_126` (primitive `single_asset_trend`)

**PRE-REGISTRATION — frozen 2026-08-09, committed automatically before any OOS test ran (#179).** Parameters: ticker=TLT, lookback=126. Rebalance freq: M.

Rationale: Structural configuration of the long end, not a track-record claim -- I assert nothing about how TLT, duration, or any trend strategy has recently performed, and a sign rule takes BOTH directions, so nothing here is a directional call on rates. The pre-registered condition a single-ticker trailing-sign rule needs is that a KNOWN repricing arrives in installments rather than in one jump (Hong & Stein's gradual-information-diffusion condition), and the long end is currently the one place in this UNIVERSE where the price driver is explicitly a slow-moving quantity rather than an expectations jump. Two facts define that setup as of this proposal. (1) Long-maturity yields are being set by TERM PREMIUM -- fiscal deficits, net coupon issuance, SOMA runoff, foreign demand -- rather than by the expected policy path: the ACM term-premium estimate has swung ~118bp between 2020 and 2026, and with the funds rate being eased the 2y is anchored while the 10y/30y is free to drift on supply and absorption. Supply-absorption pressure is a stock that accumulates quarter by quarter as the private sector takes down a rising share of long-dated paper; it does not arrive as a single dated surprise the way a CPI print or an FOMC decision does. (2) The August 2026 quarterly refunding makes the installment cadence explicit and calendar-bound: Treasury is HOLDING nominal coupon and FRN auction sizes steady for at least the next several quarters while borrowing needs climb, financing the gap at the bill end and stating that current sizes leave it 'positioned to respond to possible changes in the fiscal outlook and in the size and composition of the SOMA portfolio.' Any future shift of marginal financing toward the long end is therefore a discrete, pre-announced, quarterly-cadence decision whose duration-supply consequences are absorbed over the following quarters -- a staircase, not a step. A 126-trading-day (~6-month, two refunding cycles) lookback with monthly rebalancing is chosen to match that cadence rather than to chase price noise. A secondary structural point for why the SIGN-CONDITIONED shape is the right one here rather than a static duration position: the stock-bond correlation is expected to sit in positive territory in this inflation regime, so duration is not currently a dependable portfolio hedge and a rule that will hold duration short as readily as long is the honest way to express it. Falsifiable in the usual way -- if long-end pricing is dominated by unforecastable auction-day and inflation-print surprises rather than by slow supply absorption, a trailing-sign rule on TLT captures nothing and this dies on gate 1 like every other trend candidate in this lab. Also fills a real gap in the pipeline's own coverage: single_asset_trend has been proposed six times, on commodity, real-estate, currency and EM-equity tickers, and never once on a rates ticker.

Citation: U.S. Treasury, Quarterly Refunding Statement of Deputy Assistant Secretary for Federal Finance (home.treasury.gov/news/press-releases/sb0590) and the August 2026 refunding tables -- $125bn auctioned 2026-08-11/12/13 ($58bn 3y, $42bn 10y, $25bn 30y), refunding ~$96.3bn of privately-held notes/bonds maturing 2026-08-15 and raising ~$28.7bn of new cash, with nominal coupon and FRN auction sizes held steady for at least the next several quarters. Term-premium regime: Ferrante Capital, 'Term Premium Is Back: Why the 10-Year Hasn't Rallied' (ferrantecapitaladvisers.com/insights/treasury-term-premium-regime-2026/) and Convex, '30Y Treasury Yield Forecast 2026' (convextrade.com/forecast/dgs30) -- ACM term-premium swing of ~118bp 2020-2026, $2T+ annual deficits plus Fed balance-sheet runoff shifting long-dated absorption to the private sector. Stock-bond correlation regime: Oxford Economics, 'Stock bond correlation will become positive again in 2026' (oxfordeconomics.com/resource/stock-bond-correlation-will-become-positive-again-in-2026/). Mechanism: Hong & Stein (1999), 'A Unified Theory of Underreaction, Momentum Trading and Overreaction in Asset Markets', Journal of Finance 54(6).


### `rp_asset_class_trend_hedge_VNQ_UUP_126_63` (primitive `asset_class_trend_hedge`)

**PRE-REGISTRATION — frozen 2026-08-09, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=VNQ, ticker_b=UUP, lookback_a=126, lookback_b=63. Rebalance freq: M.

Rationale: A rate-sensitivity offset claim about two legs on two different clocks, not a performance claim: I assert nothing about how REITs, the dollar, or any trend strategy has recently done, and both legs are bidirectional trailing-sign rules, so nothing here is a directional call on rates, VNQ or the dollar. The specific mechanism I expect to make the legs offset is that a single identifiable driver -- the US policy-rate path -- currently reaches these two tickers with OPPOSITE sign, through two structurally distinct channels. Channel A (VNQ, real_estate): listed REITs run debt/EBITDA of roughly 5-10x against under 3x for investment-grade industrials, so their equity is a levered claim on refinancing cost, and 2026 is the year that cost is actually being crystallised -- about $875bn of commercial and multifamily mortgage debt matures in 2026 (~17% of the ~$5tn outstanding, with another ~$652bn in 2027), and loans written 5 years ago at 3-4% are rolling into 6-7% money. Nareit's Q1 2026 implied cap rates (industrial 5.2%, self-storage 5.9%, retail 6.2%, residential 6.4%, office 7.7%) sit well above the 3.0-3.5% cap rates much 2019-21 paper was underwritten at, which is what makes the refi channel bind rather than being absorbed. A hawkish repricing therefore pushes VNQ's trailing return DOWN via coverage and cap rates. Channel B (UUP, currency): the dollar's dominant driver right now is explicitly the Fed path under Chair Warsh and the US-vs-G10 policy gap, with DXY near 99.9 at the start of August 2026, 10y around 4.68%, and officials signalling readiness to hike 25bp in September if the coming inflation prints run hot. The same hawkish repricing widens the differential and pushes UUP's trailing return UP. Opposite-signed responses to one shared driver is the checkable relationship the primitive asks for -- not an observation that the two happen to be uncorrelated. The two lookbacks are deliberately unequal because the two channels run on different clocks, which is the reason this primitive gives each leg its own: 126d for VNQ because the maturity wall arrives as quarterly cohorts across 2026-27, an installment repricing whose price impact accumulates over roughly two quarters rather than in one jump; 63d for UUP because the differential channel resolves on the FOMC-plus-CPI cadence, and ~1 quarter spans about two meetings and the inflation prints the September question hinges on. Monthly rebalancing matches both drivers -- neither a quarterly refi cohort nor a meeting cycle emits new information at daily frequency, so a finer freq would buy turnover, not signal. Under-used-primitive note: asset_class_trend_hedge has 6 prior proposals and this real_estate-vs-currency pairing is unused; it is distinguishable from the TLT/UUP proposal of 2026-08-07, which put the pure duration channel on both sides, whereas leg A here is a levered cap-rate/coverage claim rather than a duration one. Stated honestly as a hypothesis: the offset claim is exactly what the calibration-window (2007-2017) correlation cap is there to test, and a 2007-2017 sample containing both the 2008 dollar spike against collapsing REITs and the 2014-15 period when a strong dollar coincided with rising REITs may well reject it. If the guard rejects it, the guard is right and this proposal should die there.

Citation: CRE maturity wall: ReedSmith, 'The Debt Maturity Wall and 2026 Wave -- Challenges and Opportunities' (reedsmith.com/our-insights/blogs/real-estate-legal-update/102mijo/the-debt-maturity-wall-and-2026-wave-challenges-and-opportunities/) and MMG Real Estate Advisors, 'The 2026 CRE Refinancing Wall: Opportunities in Multifamily Distress' (mmgrea.com/2026-cre-refinancing-wall/) -- ~$875bn maturing in 2026, ~17% of ~$5tn outstanding, ~$652bn more in 2027, 3-4% originations refinancing at 6-7%. Cap rates: Nareit Q1 2026 REIT Industry Tracker implied cap rates as reported by Selborne Research, 'Commercial Real Estate Cap Rates by Property Type 2026' (selborneresearch.com/guides/reits/cap-rates-by-property-type/) -- industrial 5.2%, self-storage 5.9%, retail 6.2%, residential 6.4%, office 7.7%, against 3.0-3.5% underwriting in 2019-21. REIT leverage/rate-sensitivity mechanism: Simply Safe Dividends, 'How Higher Interest Rates Impact REITs' (simplysafedividends.com/world-of-dividends/posts/20-how-higher-interest-rates-impact-reits) -- REIT debt/EBITDA 5-10x vs under 3x for IG industrials; Crystal Funds, 'The Effects of Interest Rate Changes on REITs' (crystalfunds.com/insights/effects-of-interst-rates-on-real-estate-investment-trusts/). Policy path: CNBC, '2-year Treasury yield keeps going higher after spiking on hawkish start to Warsh's Fed' (cnbc.com/2026/06/18/treasury-yields-investors-warsh-fed-interest-rates.html); 10y ~4.68% and September 25bp hike pricing per Trading Economics, 'US 10 Year Treasury Note Yield' (tradingeconomics.com/united-states/government-bond-yield). Dollar driver and level: MTFX Group, 'US Dollar Forecast August 2026' (mtfxgroup.com/fx-monthly-us/) and Cambridge Currencies, 'US Dollar Index (DXY) Forecast 2026' (cambridgecurrencies.com/us-dollar-index-dxy-forecast/) -- DXY near 99.9 on 2026-08-01, Fed path under Warsh the dominant driver followed by the US-vs-G10 growth/policy gap, H2 range 92-100.


### `rp_cross_sectional_rank_low_vol_252_2` (primitive `cross_sectional_rank`)

**PRE-REGISTRATION — frozen 2026-08-09, committed automatically before any OOS test ran (#179).** Parameters: metric=low_vol, lookback=252, k=2. Rebalance freq: M.

Rationale: The long end is repricing term premium -- the 30y has broken out to ~5.275% while the Fed is expected to keep easing the front end, and the stock-bond correlation has turned positive -- so the realized volatility in this ETF universe now sits in long-duration rates, the leg a cross-asset book conventionally treats as its quiet one. A cross-sectional low_vol rank makes no assumption about which asset class is defensive: it ranks each ETF by its own trailing realized vol, so it structurally shorts whatever is actually carrying the risk right now (long duration, and precious metals in a central-bank-demand-driven bull cycle) and holds the genuinely quiet legs. lookback=252 so the rank reflects the year-long term-premium repricing rather than one month of headlines; k=2 keeps both sleeves at the true extremes; freq=M matches how slowly a 252-day vol rank can move, so turnover cost is not paid for noise.

Citation: Frazzini & Pedersen (2014), 'Betting Against Beta', Journal of Financial Economics 111(1) 1-25 -- the low-risk premium this metric expresses. Current structural context: ICE, 'A duration crisis for markets' (ice.com/insights/fixed-income-data/a-duration-crisis-for-markets) on rates volatility concentrating in the long end, and SSGA 'Gold 2026 Outlook' / World Gold Council 'Why gold in 2026? A cross-asset perspective' for the 30y ~5.275% breakout, the higher stock-bond correlation, and structural central-bank gold demand.


### `rp_static_spread_carry_SLV_USO_a` (primitive `static_spread_carry`)

**PRE-REGISTRATION — frozen 2026-08-12, committed automatically before any OOS test ran (#179).** Parameters: ticker_a=SLV, ticker_b=USO, long_leg=a. Rebalance freq: M.

Rationale: The two commodity sub-complexes inside UNIVERSE are, right now, under opposite physical-supply regimes, which is the structural condition a fixed always-on long-short is built to harvest. Silver is in its sixth consecutive year of structural deficit -- roughly 65-70 Moz short in 2026 on a cumulative 2021-2026 shortfall of ~1,050-1,100 Moz (more than a full year of mine production) drawn down from above-ground stocks, with industrial use ~60% of total demand and solar PV alone absorbing ~120-125 Moz against ~665 GW of 2026 installs; mine supply is rigid because ~70% of silver is a by-product of copper/lead/zinc/gold output and does not respond to the silver price. Crude is in the mirror-image position: OPEC+ added 188 kbpd in August 2026 as it unwinds cuts, Persian Gulf supply recovers to ~90% of pre-war volumes in August and near-full by November, the IEA puts the 2026 surplus at nearly 4 mb/d with the first monthly surplus (~1.2 mb/d) landing in August, and global inventories built 225 mb from January to a four-year-high 7.9 bn bbl. The WTI curve has consequently sat in contango for much of 2026, which matters mechanically for the short leg specifically: USO holds front-month WTI futures and pays that roll cost every month, whereas SLV holds allocated bullion with no roll at all -- so the spread earns the scarcity/roll differential without any directional forecast on either leg. This is a static structural risk-premium bet, not mean reversion: it is deliberately NOT the pair_zscore shape, because a persistent supply deficit on one side and a persistent glut on the other imply drift, not a spread that returns to its mean. The real risk being borne, stated plainly: silver's industrial demand is pro-cyclical, so a growth shock hits the long leg while a supply disruption (OPEC+ reversing, Gulf outage) hits the short leg -- both legs can lose together, and the 2026 glut is a policy choice OPEC+ can unmake. Distinct from the already-proposed rp_static_spread_carry_SLV_GLD_a (silver against a monetary metal, no energy leg) and rp_static_spread_carry_USO_DBC_a (crude against a broad diversified basket, no metals-scarcity claim); neither is this the sign-flip of any existing pipeline row. Chosen over a broad-basket commodity trend leg because the 2026 picture is explicitly divergent by sub-complex -- energy in glut, agriculture amply supplied, metals tight -- so the aggregate index averages the very dispersion this spread is trying to hold. Primitive tally note (2026-08-12): static_spread_carry is the most-proposed primitive at 9 uses against 7 for each of the other five; taken deliberately anyway, since an always-on relative physical-supply bet is the only shape in the current vocabulary that expresses this mechanism (asset_class_trend_hedge mechanically rejects two commodity legs, and pair_zscore asserts the opposite dynamics).

Citation: Silver deficit and industrial/solar demand: Silver Institute-sourced 2026 balance reporting (goldsilver.com/industry-news/goldsilver-news/silver-market-deficit-2026-six-years-and-getting-worse/; bunker-group.com/en/blog/silver-production-balance-a-structural-deficit-in-2026; mintedmetal.com/analysis/silver-industrial-demand-2026/) -- ~65-70 Moz 2026 deficit, ~1,050-1,100 Moz cumulative 2021-2026, ~680 Moz industrial use (~60% of demand), ~120-125 Moz solar against ~665 GW 2026 PV installs. Crude surplus and inventories: IEA Oil Market Report / 'As oil market surplus keeps rising, something's got to give' (iea.org/commentaries/as-oil-market-surplus-keeps-rising-something-s-got-to-give) -- ~4 mb/d 2026 surplus, first monthly surplus ~1.2 mb/d in August 2026, Gulf supply ~90% of pre-war in August to near-full in November, global stocks +225 mb Jan-Aug to a four-year-high 7.9 bn bbl; OPEC+ August 2026 quota increase of 188 kbpd (ebc.com/forex/oil-price-opec-august-2026-inventory-test). WTI term structure in contango for much of 2026: CME Group economic research, 'Implications of WTI Oil Futures In Backwardation Amid the Supply Crunch' (cmegroup.com/insights/economic-research/2026/implications-of-wti-oil-futures-in-backwardation-amid-the-supply-crunch.html); USO's front-month roll mechanics per USCF Investments (uscfinvestments.substack.com/p/understanding-contango-and-backwardation). Divergence by sub-complex: World Bank Commodity Markets Outlook (blogs.worldbank.org/en/developmenttalk/the-commodity-markets-outlook-in-eight-charts3) -- ample grain supply, elevated metals index on tight base-metal markets.

## Rules of the roster
1. A strategy's spec (signal, universe, freq) is frozen **before** its OOS verdict.
2. One verdict per spec. Tweaks = a NEW row and a NEW graveyard entry.
3. Families are chosen to be **mutually uncorrelated bets** — trend vs reversal vs calendar
   vs defensive vs carry. Correlation matrix in the dashboard is the check.
4. DEAD standalone ≠ useless: low-corr sleeves may still earn a place as piggyback
   diversifiers on the 60/40 core (see research/combine.py / dashboard Piggyback Lab).

## Key evidence (gathered in research sessions)
- TSMOM: Moskowitz–Ooi–Pedersen 2012, ~1.0 Sharpe across 58 futures pre-costs (AQR/Quantpedia).
- Turn-of-month: documented since Lakonishok & Smidt 1988; still debated post-1990s (Quantpedia, QuantSeeker).
- Short-term reversal / RSI(2): Connors; SPY 1993– ~9%/yr while invested 28% of time (QuantifiedStrategies).
- Low-vol / BAB: Frazzini–Pedersen 2014, Sharpe ~0.78, ~2x US market (NBER).
- Funding carry: 8–20% APY documented in calm regimes, delta-neutral (multiple 2025–26 sources).
- Retail overfitting: backtest Sharpe explains <3% of live results; more tweaking widens the gap.
