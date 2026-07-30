# Project rundown — 2026-07-27 (#98)

An audit of whether the machinery still serves the lab's purpose. Every number below was
measured against the repo, not recalled.

> ## Resolution as of 2026-07-29 — read this first
>
> **Every number below is as-measured on 2026-07-27 and is deliberately NOT updated.** This is
> a dated audit, not a live document; rewriting its measurements would destroy the record of
> what was known when the decision was made. Current counts: `gh issue list`, `graveyard.csv`.
>
> | this document's open item | outcome |
> |---|---|
> | Options 1–4 on the correction — "this needs a decision" | **Option 3, segregate.** Pre-registered as DOCTRINE **v1.5** (#112), implemented (#120), **in force 2026-07-29** |
> | Fix the lenient null (#101) | **Shipped in the same v1.5**, deliberately together — the two findings pointed opposite ways |
> | Pause the factory | **Done 2026-07-27.** Cron commented out, `workflow_dispatch` intact |
> | No retirement criterion; books grow without bound | **DOCTRINE v1.6** (#113) — and it **inverts this document's framing**, see below |
> | Benchmark windows not candidate-aligned | still open, **#115** |
> | Doctrine vestigial layers | still open, **#116** |
> | `state/` ownership conventional, not structural | still true; a hook now *asks* before staging `state/` |
> | "Unbounded growth is an accepted cost, lever is the pause" (below) | **Partially superseded 2026-07-30, #147:** `MAX_FACTORY_PROMOTED` caps the factory-owned pool directly (skip promotion at cap, keep evaluating/logging), independent of whether the cron ever resumes. A read-only "up for review" dashboard list surfaces old factory-owned books for Dave to look at — still no automatic retirement, v1.6 unchanged |
>
> **On retirement, the resolution contradicts what this document implies.** It reads as though
> the lab needs a stopping rule. The decision was that an *automatic* one would be actively
> harmful: auto-retiring losing books filters the forward record on results, manufacturing
> survivorship bias in the one dataset here that has none. Retirement is manual-only, at any
> age, with no performance trigger. Unbounded growth **was** treated as an accepted cost with
> promotion-pause as the only lever (see below) — #147 added a second, more direct one: a hard
> cap on the factory-owned pool, so growth stops even if the cron resumes, with a human-in-
> the-loop review list rather than any performance-based trigger.
>
> **Two things this audit did not find**, both since discovered: gate 1 can be **vacuous**
> (DSR 1.000 against a negative `SR*`, so any positive Sharpe clears it — #114, first real
> instance in family M), and `evaluate()` mislabels a non-60/40 benchmark in its own output
> (#122). Neither changes a verdict.
>
> **A third, related consequence of the same vacuous-DSR mechanism surfaced 2026-07-30
> (#145):** every daily-rebalanced factory candidate (families C/turn_of_month,
> I/donchian) saturates to DSR 1.000 the same way #114 found, and the factory's
> PROMOTION ranking (unlike the graveyard verdict) had no guard against it — so every
> promoted generated candidate to date was `turn_of_month_gen_*`, decided by candidate
> list order rather than real quality. Fixed by ranking promotion on CPCV-resampled OOS
> Sharpe instead of raw DSR; doesn't change any graveyard verdict, same as #114/#122.
>
> **The council's own closing question is still unanswered:** would a factory ALIVE have been
> *pleasing* or *alarming*? That, not the statistics, decides whether the factory's purpose was
> discovery or calibration.

## The one finding that matters

**The strategy factory is consuming the lab's entire statistical budget and has produced
nothing.**

| | |
|---|---|
| unique strategies in `graveyard.csv` | 136 |
| ALIVE | **0** |
| factory-origin | **124 (91%)** |
| ALIVE among factory-origin | **0** |

`harness.family_n_tested()` is `len(graveyard_names ∪ candidates)`, and it feeds the
multiple-testing correction. So every factory row raises the bar for **every future
candidate, including hand-picked ones**. The factory adds ~20/day, permanently:

| `n_tested` | required DSR Sharpe (ann.) | |
|---|---|---|
| 12 | 1.58 | before the factory |
| 136 | **2.52** | today |
| 500 | 2.92 | ~3 weeks |
| 2,000 | 3.31 | ~3 months |
| 7,300 | **3.63** | one year at current rate |

For scale: a genuinely good equity strategy runs Sharpe 0.5–1.5. **The lab has already
priced those out**, and is on a trajectory where nothing but an anomaly like the funding
carry (Sharpe ~12 on daily-aggregated returns, because funding is a smooth drip) can ever
clear gate 1 again.

This is not a bug in the factory. The factory is doing exactly what it was designed to do,
and the pre-registration logging is genuinely rigorous. **The design itself is
self-defeating**: an unbounded automated search inside a family-wise error correction
spends the budget it needs.

### Options

1. **Cap the family.** Correct against a rolling or per-family window rather than the
   all-time union. Defensible: the factory's draws are not the same hypothesis family as a
   hand-picked candidate.
2. **Stop the factory**, or run it in bursts with the budget priced in beforehand.
3. **Segregate the ledgers.** Factory rows count against factory candidates only; the
   hand-picked roster keeps its own smaller `n_tested`.
4. Accept it, and treat the lab as closed to anything short of an anomaly.

This needs a decision. Option 1 or 3 seems right, but it is a DOCTRINE change and must be
pre-registered like any other.

## Gate 1 is doing real work, but was calibrated wrong

It is not decorative — **88 of 136 (65%)** DEAD strategies failed gate 1. But it has been
systematically **lenient** (#101): the noise floor re-drew a random signal every bar, so
the null traded 3.7× more than a real monthly signal and 19.9× more daily. Cost scales
with turnover, so the null paid a penalty the candidate never did.

Corrected, the monthly bar moves from p95 0.293 to **1.532**. `tsmom_12m` (Sharpe 0.499)
clears the old bar and fails the new one.

**These two findings point in opposite directions and must be settled together.** Fixing
the null makes gate 1 much stricter; the factory has *already* made it much stricter via
`n_tested`. Applying both without re-deciding the family-size question would close the lab.

## Secondary findings

**Benchmark windows are not candidate-aligned.** `harness.evaluate()` slices both series at
`OOS_START` (2018) rather than at the candidate's first observation. `crypto_reversal_1h`
spans 2024-07+ but was scored against 60/40 measured from 2023-08 (Sharpe 1.189 vs 0.959
over its actual window). Immaterial there; it would decide a marginal case.

**Live books grow without bound.** One promotion per cycle, forever, by design: 16 today →
~46 in a month → ~381 in a year. Each is marked every cycle, so cycle time and ledger size
grow linearly. Two family L books are losing 70%/yr and 14%/yr with no stopping rule. There
is no retirement criterion anywhere in the engine.

**Doctrine has accumulated vestigial layers.** `bonferroni_bar()` is computed and logged on
every run but has decided nothing since v1.4. `NULL_PCTILE = 95` survives two supersessions.
Both are deliberate (logged for continuity) and both are now things a reader must be told to
ignore — the file has 14 version references. Worth a consolidation pass.

**`state/` sole-ownership is conventional, not structural.** The Action owns it, but nothing
prevents a local write; that caused a merge conflict and a closed PR today. Now guarded by a
hook that *asks*, which is the right severity, but the underlying design still relies on
discipline.

## What is genuinely healthy

- **Pre-registration works.** `doctrine-auditor` verified the family L spec commit is
  strictly older than its results, with the caveats already written, and reproduced every
  logged number bit-for-bit from committed snapshots.
- **The engine is honest about data.** NaN marks refused, partial bars trimmed, marks that
  would travel backwards in time rejected, rolling-window sources snapshotted.
- **The graveyard is a real record**, tracked in git, never rewritten to flatter a result.

The lab's *epistemics* are in good shape. What is broken is a **resource-allocation
decision**: an unbounded search inside a fixed error budget.

---

## Council verdict (2026-07-27)

Run via the `council` skill on the question *"what should be done, and is the factory worth
keeping at all?"*. Five adversarial voices, cross-examined, then resolved.

**Verdict: pause the factory, segregate the ledgers, keep the machinery.**

The trajectory concern is real but the diagnosis was wrong. `n_tested` is being **misapplied
to a search procedure**: family-wise correction assumes you would have accepted any tested
hypothesis, but the factory's draws are not hypotheses anyone would trade — they are steps
in a search. Nobody Bonferroni-corrects gradient descent for every step it visited.

The line that survived cross-examination: **a draw you would never act on is search; the
promoted winner is a hypothesis.** So factory draws count against factory candidates only,
the hand-picked roster keeps its own smaller `n_tested`, and the promoted winner joins the
main family — because promotion *is* selection-on-result.

### The observation that decided it

The factory auto-promotes its best-DSR candidate **regardless of verdict** to a
monitor-only book, and DOCTRINE v1.2 means such a book can never become `paper-confirmed`.

**So the factory's success case and its failure case produce the identical outcome: another
monitor-only book.** That is not a search. It is a loop with no exit condition — which is
the actual reason to pause it, independent of any statistics.

### What was rejected

*"The factory's real output is the empirical distribution of what doesn't work."* Appealing,
but the lab **already** builds a proper noise floor from 500 random strategies per frequency,
deliberately and more rigorously. The factory duplicates that at higher cost and worse
control.

### What would flip the verdict

If the factory's purpose was always **calibration rather than discovery**, then 0/124 is a
success and the correction question is moot. The honest test: would a factory ALIVE have
been *pleasing* or *alarming*?

### Guardrail — unanimous

**Any change to the correction is pre-registered BEFORE any verdict is recomputed under it.**
Adjusting the bar and then re-scoring is precisely the failure this lab exists to prevent.
Fix the rule, then run forward. Never re-score backward to rescue a result.

Recomputing old verdicts under segregated `n_tested` is legitimate as a **diagnostic** — to
learn whether the bar inflation was theoretical or buried something real — but its output is
a finding to discuss, never a silent re-verdict.

### Caveat

All five council voices are one model in a single pass. That reduces mirroring; it is not
independent judgment. The real test is external — a live book, a market, a genuinely
out-of-sample year.
