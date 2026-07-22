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

## What the doctrine deliberately does NOT reward
- High raw returns from leverage — Sharpe is scale-invariant; leverage can't create edge.
- In-sample beauty — only out-of-sample counts.
- Beating SPY in a bull market — not the job of a diversified book.
