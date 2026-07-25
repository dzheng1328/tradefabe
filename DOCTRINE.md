# Evaluation Doctrine — v1.0 (frozen 2026-07-21)

The doctrine is the constitution of this project. It decides — *before any strategy is
run* — what counts as a real edge and what gets killed. Its whole job: let genuinely
profitable strategies through while killing the lucky, overfit, and failing ones, and draw
that line with **statistics, not preference**.

## The fine line, and how we walk it

The danger in "use our data to design the doctrine" is meta-level p-hacking: tune the
thresholds to the results you've already seen and the doctrine simply passes whatever you
like. We avoid that with four locked rules:

1. **Pre-registration.** This file is frozen and timestamped. Thresholds are set *before* the
   strategy zoo is run. Changing them means a new doctrine version and re-running everything.
2. **Out-of-sample only.** Design/calibration uses 2007–2017. Every verdict is rendered on
   2018–present, which the design never touched.
3. **Judge against luck, not an arbitrary number.** The pass bar is calibrated *from the
   data*: run hundreds of RANDOM strategies through the identical machinery and measure the
   distribution of their out-of-sample Sharpe. A candidate must beat the 95th percentile of
   that noise floor. This is the honest way to "use the data to make the doctrine" — we use it
   to measure what luck looks like, never to pick winners.
4. **Fair benchmark.** A diversified strategy is compared to a diversified passive portfolio
   (60/40), not to the single best-performing asset in hindsight.

## Data split
- **Design / calibration:** 2007-01 → 2017-12
- **Evaluation (out-of-sample):** 2018-01 → present

## Benchmark
Passive **60% SPY / 40% IEF**, monthly rebalanced, charged the same costs. (SPY reported
separately for context only.)

## Metrics (all out-of-sample, net of pessimistic costs)
- **Sharpe**, **Sortino**
- **Calmar** = CAGR / |max drawdown| — return per unit of pain
- **Correlation to the benchmark** — diversification value
- **Max drawdown**

## The noise floor
`N = 500` random long/short strategies, same universe / sizing / rebalance / costs, evaluated
on the OOS window. `null_p95` = the 95th percentile of their OOS Sharpe. This bar rises
implicitly with how many real strategies we try (multiple-testing awareness); the count is
logged so it can be tightened (Bonferroni-style) later.

## Kill rule — a strategy is ALIVE only if ALL three hold, else DEAD
1. **Beats luck:** OOS Sharpe > `null_p95`.
2. **Earns its place:** OOS Calmar > benchmark Calmar **OR** it genuinely diversifies
   (|corr to benchmark| < 0.30 **AND** OOS Sharpe ≥ benchmark Sharpe).
3. **Not more painful:** OOS max drawdown no worse than 1.5× the benchmark's.

**ALIVE** → promote to forward paper-testing (the real, slow gate).
**DEAD** → logged to the graveyard. No knob-tuning to resurrect it.

## Ledger
Every evaluated strategy — alive or dead — is appended to `graveyard.csv` with its metrics,
the null bar, and the verdict. The graveyard *is* the multiple-testing record.

## Amendments
- **v1.0.1 (2026-07-21).** The noise floor is computed **per rebalance frequency** (D/W/M):
  a strategy is judged against random strategies rebalanced at the SAME frequency, so fast
  strategies face a luck bar that pays the same fast trading costs. Engineering fix, not a
  gate change. A strategy's rebalance frequency is part of its pre-registered spec.
  (Gate 2's diversifier clause is under review per combine.py results; any change will be
  v1.1, decided on principle and re-applied to every strategy in the graveyard.)
- **v1.2 (2026-07-23).** Defines the promote/kill criteria for paper-testing (Stage 2 —
  the "real, slow gate" the kill rule above promotes ALIVE strategies to, previously
  undefined). See "Paper-testing verdicts" below. Does not touch gates 1-3.
- **v1.3 (2026-07-24).** Makes the Bonferroni correction v1.0's noise-floor section
  already logged as a future obligation ("the count is logged so it can be tightened
  later") the ACTIVE bar for gate 1, instead of a flat `p95`. Per-test significance is
  `alpha=0.05` divided by `n_tested` (every distinct strategy ever logged to
  `graveyard.csv`, unioned with whatever's being evaluated right now —
  `harness.family_n_tested()`). The empirical null sample can only resolve percentiles to
  roughly `1 - 1/len(null)`; once the corrected percentile needs finer resolution than
  that, the bar falls back to a normal approximation fit to the null's own mean/std
  (`harness.bonferroni_bar()`, stdlib `statistics.NormalDist`, no new dependency).
  Every graveyard row now logs `n_tested`, `bar_method`, `bar_pctile` alongside the bar
  value itself (still called `null_p95` in the CSV for backward compatibility, though
  past `n_tested≈12` it is no longer literally the 95th percentile).

  **Triggered by, and immediately validated against, a real result:** re-running the 4
  piggyback constructions (family H) under this bar at their actual `n_tested` (9-12)
  flips `piggyback_2a`, `_3`, `_4` from ALIVE to **DEAD** — none of the three were
  formula artifacts of too few null trials (checked: the matched-null distributions have
  skew < 0.25, a normal fit is reasonable) but a structural consequence of the
  construction itself: every piggyback already holds 70% of the benchmark by build, so
  its random-sleeve null Sharpe clusters tightly around the benchmark's own 0.85
  (std ≈ 0.03) — there's very little room between "random sleeve" and "real sleeve" for
  THIS construction shape to clear a corrected bar, no matter how the sleeve is chosen.
  This is exactly what v1.0's "no knob-tuning to resurrect" rule 1 anticipates: the
  correction was already owed, applying it retroactively is not moving the goalposts on
  these 3 specifically, it's finishing gate 1 the way it was always specified to work.
- **v1.4 (2026-07-25).** Replaces Bonferroni as gate 1's ACTIVE decision with the
  **Deflated Sharpe Ratio** (Bailey & López de Prado, 2014, *"The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality,"* SSRN 2460551),
  combined with **Combinatorial Purged Cross-Validation** (López de Prado, 2017) —
  motivated by scaling strategy testing from a few dozen hand-picked candidates over
  weeks to a continuously-running automated search generating many candidates/day
  (issue #28). At that volume, Bonferroni's flat `alpha/n_tested` division gets
  crushingly strict *and* mathematically crude — it ignores how correlated/dispersed the
  null actually is, and a single fixed 2018+ OOS window is one draw from history that
  some candidates will beat by chance alone as search volume grows.

  **DSR** (`harness.deflated_sharpe_ratio()`) tests a candidate's Sharpe against the
  *expected maximum* Sharpe you'd see by pure luck as the best of `n_tested` random
  draws from this project's own empirical noise floor (`harness.expected_max_sharpe()`,
  an extreme-value approximation using the null's own mean/std — the SAME `null` and
  `n_tested` Bonferroni already used) — correcting for the null's actual spread, not
  just its count, and for the candidate's own return skew/kurtosis
  (`harness.probabilistic_sharpe_ratio()`, the underlying PSR test). **CPCV**
  (`harness.cpcv_splits()` / `cpcv_oos_sharpes()`) replaces the single fixed-window OOS
  Sharpe with the mean of several purged, embargoed, resampled test paths drawn from the
  same OOS history — a candidate has to hold up across multiple slices, not just the one
  the doctrine happens to use. A candidate clears gate 1 when `dsr > 0.95` (same p95
  convention v1.0 started with). `bonferroni_bar()` stays in the code and the ledger,
  logged only, same as v1.0's flat p95 stayed visible after v1.3 stopped deciding with
  it. No new dependency — both are closed-form/resampling, computed via stdlib
  `statistics.NormalDist`, exactly like `bonferroni_bar()` already was.

  Applies graveyard-wide, to every evaluation going forward (bare strategies via
  `harness.evaluate()`, constructions via `piggyback_backtest.py`'s `evaluate()` — both
  now call the same shared `harness.dsr_gate1()`, which previously would have meant two
  copies of this logic silently drifting apart) — one standard, not two tiers of rigor
  in one ledger, same principle v1.3 applied retroactively. `graveyard.csv` gained 5
  columns (`dsr`, `dsr_sr_star`, `cpcv_n_paths`, `cpcv_sharpe_mean`, `cpcv_sharpe_std`);
  existing rows were migrated with these blank, not backfilled — v1.4 wasn't applied
  retroactively to historical verdicts, only from this point forward.

  **Validated against a real result:** re-running the full roster (7 bare strategies +
  4 piggyback constructions) under v1.4 changes no verdicts — everything that was DEAD
  stays DEAD (piggybacks' DSR ≈ 0.52-0.53, well below the 0.95 bar, consistent with
  v1.3's structural explanation above: there's little room between "random sleeve" and
  "real sleeve" for this construction shape under ANY properly corrected bar), and
  `turn_of_month` (the one bare strategy whose raw Sharpe already cleared the old
  Bonferroni bar) still clears gate 1 under DSR too, still dies on gate 2 (Calmar/
  diversification) exactly as before — no regression in either direction.

## Paper-testing verdicts (v1.2)

Pre-registered the day after the paper engine launched (oldest book: 2026-07-22), before
any book had accumulated enough history to tempt reading a verdict into it. This is gate
1-3's "no knob-tuning to resurrect" ethos applied to the second gate.

### Scope — who this gate applies to
Paper-testing is a promotion path for strategies that already passed the backtest kill
rule (ALIVE). Books currently paper-traded that were backtest-**DEAD**
(`tsmom_12m`, `tsmom_ensemble`, `green_line_200d`, `turn_of_month` — see
`graveyard.csv`) are monitored for research/dashboard value (does live match the
backtest-implied dead-ness; that's what the backtest/live splice chart checks) but are
**not eligible for a `paper-confirmed` verdict under any circumstance.** A DEAD backtest
that happens to look good in early paper data is exactly the lucky noise the noise floor
exists to filter — re-running it through the real backtest gate on a longer or different
sample is the only legitimate route back to ALIVE. Paper data is not a side door around
gates 1-3.

### Why this takes years, not weeks
For an iid daily-return process, the standard error of an *annualized* Sharpe estimate
built from T years of data is approximately:

    SE(SR_annual) ≈ sqrt(1 / T)

(this drops a `SR_daily²/2` term that's negligible whenever daily Sharpe << 1, true of
every strategy on this roster). To distinguish a book with a true annual Sharpe of 1.0
from a Sharpe of 0 at a t-stat of ~2 — an order-of-magnitude "this isn't noise" bar, not
a precise p-value:

    SR / SE(T) ≥ 2  ⟹  sqrt(T) ≥ 2  ⟹  T ≥ 4 years

A weaker true edge takes proportionally longer: for a book's backtest OOS Sharpe
`SR_bt`, **T_required = max(2 years, (2 / SR_bt)² years)**. This is a rough argument
(assumes iid returns, ignores the skew/kurtosis/autocorrelation corrections a formal
Sharpe-ratio test would apply) — precise enough to set expectations, not precise enough
to substitute for the interval-based rules below.

**Formula-validity caveat (found by stress-testing this amendment against real data
before merge, not a hypothetical):** the iid assumption breaks badly for a return stream
that isn't noisy sampling around a stable mean. `carry_btc_eth`'s own backtest equity
curve (`artifacts/carry_hl_curve.csv`) gives a *daily* Sharpe of **10.85** — funding
accrues smoothly with almost no day-to-day noise, so the naive formula would compute
`T_required ≈ 12 days`, which is absurd: it would let the confirm gate fire before the
book had even survived one funding-regime cycle, exactly contradicting `STRATEGIES.md`'s
own caveat that carry's backtest "CANNOT see the fat tail." The floor above
(`max(2 years, ...)`) exists specifically to stop a low-noise, regime-driven return
stream from formula-gaming its way to an early confirm. For carry-type books, `T_required`
in practice IS the 2-year floor, not the formula — treat the formula as binding only for
strategies whose apparent Sharpe is in the normal 0.3-1.5 range (trend/reversal/calendar),
where it was actually checked against a Monte Carlo simulation (empirical SE within 3% of
`sqrt(1/T)` at T = 1/2/4/8 years, SR=1).

### Time-gated verdict tiers
| paper-testing age | what's in scope |
|---|---|
| 0-3 months | **Plumbing only.** No performance verdict, confirm or kill. Check: did it run without crashing, do fills/costs/ledger math check out, does the position actually taken match what the signal should have produced against that day's data. Failures here are bugs — logged and fixed, not doctrine verdicts. |
| 3-24 months | **Kill-eligible, confirm-ineligible.** The kill criteria below can fire. Nothing here can promote a book to `paper-confirmed` — 24 months is the hard floor below which no book, however low-noise its returns look, gets a confirm verdict of any kind (see the formula-validity caveat above). |
| 24 months - T_required | **Kill-eligible; provisional-confirm only** (only reachable by books whose formula `T_required` exceeds the 2-year floor, i.e. `SR_bt` < 1.0). "Behaving as expected, nothing's wrong" is a valid status (`provisional`) but is explicitly not `paper-confirmed` — a good 18 months doesn't get read as proof. |
| ≥ T_required (book-specific, see formula) | **Statistical window.** The earliest point a genuine `paper-confirmed` verdict is legitimate. |

### Kill criteria (can fire any time after month 3)
1. **Divergence kill** — cumulative live-paper return minus backtest-implied return
   (the backtest strategy re-run on the *same realized market dates*, exactly what the
   dashboard's splice chart already plots) over the trailing 2 months exceeds
   `2 * sigma_m * sqrt(2)`, where `sigma_m` is that book's own frozen OOS-backtest
   monthly-return standard deviation, recorded at time of promotion (same source data as
   `T_required` above — e.g. `tsmom_12m` sigma_m=0.0134, `turn_of_month` sigma_m=0.0100,
   `carry_btc_eth` sigma_m=0.0136, computed from each book's actual OOS return series).
   A 2-sigma bound on a 2-month cumulative difference under the null "live matches
   backtest," not a round-number guess. If the gap isn't explained by a logged, known
   difference (real fill timing vs backtest assumption, live cost slippage, etc), it
   signals a live implementation bug or an edge that doesn't survive contact with real
   execution — either way, kill and re-diagnose before any re-paper-test.
2. **Statistical kill** (valid only once >= 12 months in) — the paper Sharpe's
   one-sided 95% upper bound (`SR + 1.645*SE(T)`) is <= 0. Requires the *entire*
   confidence interval to exclude any edge, not just a negative point estimate — with
   limited months noise dominates a point estimate, and a point-estimate-only kill would
   be trigger-happy.
3. **Drawdown kill** — live drawdown breaches the same 1.5x-benchmark bound as backtest
   gate 3, realized in actual dollars. Immediate, no waiting period — a risk control, not
   a statistical judgment.
4. **Tail-risk kill** (carry-type books only) — an unresolved `high_risk_alert` from
   `carry_risk.py`'s live monitor (funding-flip or liquidation-distance breach, #6)
   sustained for more than 30 days without the operator posture being reduced. The
   Sharpe-based rules above are blind to exactly the tail risk carry's backtest can't
   see; this rule makes the existing risk monitor part of the verdict, not a side panel.

### Confirm criteria
A book is **paper-confirmed** only when ALL of:
- paper-testing age >= `T_required` (formula above, floored at 2 years), using the
  frozen backtest OOS Sharpe recorded in `graveyard.csv` / `STRATEGIES.md` at time of
  promotion — not a re-fit, **and**
- the realized paper Sharpe's one-sided 95% lower bound (`SR - 1.645*SE(T)`) is > 0,
  **and**
- the realized paper Sharpe is statistically compatible with the backtest OOS Sharpe
  (within +/- 2*SE(T) of it) — paper trading has to confirm the *same* edge the backtest
  found, not merely land on some other positive number, **and**
- for carry-type books: no unresolved `carry_risk.py` `high_risk_alert` at the moment of
  the verdict (a confirm is a point-in-time claim; it can't be issued mid-alert).

Confirmed books stay on the roster as live strategies exactly as before; this gate only
governs what claim can honestly be made about them.

### What a period short of T_required CAN and CANNOT tell us
The concrete answer to "what does N months of paper data actually buy us," since that's
the question this amendment exists to pre-empt from being answered after the fact:

**CAN, from month 1:**
- Plumbing correctness — the live position matches what the signal says it should be.
- Qualitative sign correctness — is the book long or short what the backtest logic implies.
- Cost realism — do live fill costs resemble the backtest's cost assumption, or is the
  real venue eating more than modeled.
- Early divergence red flags (kill rule 1) — a live bug or a backtest that doesn't
  survive real execution shows up fast; it doesn't take years to see a wheel fall off.
- Book-specific risk events (e.g. the carry book's funding-flip and liquidation
  monitors, #6) — these are risk signals, not edge signals, and are live from day one.

**CANNOT, before T_required:**
- Confirm the edge is real. A good Sharpe over a few months is statistically
  indistinguishable from a lucky draw off the same noise floor the backtest gate exists
  to filter.
- Rule the edge out on a point estimate alone. A bad Sharpe over a few months is equally
  indistinguishable from an unlucky draw — only the kill rules above (divergence,
  drawdown, or a full-CI statistical exclusion) are strong enough evidence to act on early.

## What the doctrine deliberately does NOT reward
- High raw returns from leverage — Sharpe is scale-invariant; leverage can't create edge.
- In-sample beauty — only out-of-sample counts.
- Beating SPY in a bull market — not the job of a diversified book.
