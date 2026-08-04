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

## Current state — read this first (as of v1.12, 2026-08-04)

The sections below this one (Data split through Ledger) are v1.0's ORIGINAL, frozen text —
kept verbatim as the pre-registration record, per rule 1 above. Eight amendments have since
changed what's actually decided. Rather than make every reader re-derive "what's true today"
by tracing all eight, here is that answer in one place. Each line names the amendment that
introduced it, so a question about *why* still has one place to go — the **Amendment
history** section below.

- **Data split.** Design/calibration 2007-01→2017-12; evaluation 2018-01→present —
  unchanged from v1.0, **except family M**, whose OOS start is Kronos's own pretraining
  cutoff (2025-06-05) instead of 2018 (`kronos_backtest.py`'s module-level override, needed
  because `evaluate()` and `noise_floor()` must share one window). Both the candidate and
  the benchmark are sliced at `max(OOS_START, the candidate's own first observation)` — v1.0
  used a flat `OOS_START` for both; v1.7 fixed the candidate/benchmark window mismatch that
  produced whenever the candidate's own data starts later than `OOS_START`.
- **Benchmark.** Still 60/40 SPY/IEF by default, but not universal — carry-type studies
  benchmark against always-on carry instead, pre-registered per study rather than chosen
  after seeing results. The printed/logged label now says which one it is (`bench_label`,
  #122 — cosmetic, not a doctrine amendment, since the comparison itself was always right).
- **Noise floor.** 500 random strategies, but **duty-cycle-matched to the candidate's own
  signal by default** (rotated, not redrawn every bar) since v1.5b — a per-bar random null
  was measured to be systematically lenient (it paid less turnover cost than a real trend
  signal). Per-strategy, not merely per-frequency (v1.0.1 was the frequency-only version).
- **Gate 1 ("beats luck").** Decided by the **Deflated Sharpe Ratio** (`dsr_gate1()`, v1.4)
  against an extreme-value-corrected "best of `n_tested` draws" bar, using a
  **CPCV-resampled** OOS Sharpe rather than the single fixed-window point estimate, **and**
  requiring the candidate's own OOS Sharpe be positive (v1.8 — DSR alone has no such floor
  and can saturate near 1.0 beside a losing candidate). `n_tested` is segregated by origin
  into **three** buckets — factory-search draws correct against factory-origin rows only,
  research-pipeline draws against pipeline-origin rows only (v1.10), hand-picked
  candidates against hand-picked + promoted rows from either automated origin (v1.5a).
  **`bonferroni_bar()` and `NULL_PCTILE=95`
  are still computed and logged on every run (the `null_p95`/`bar_method`/`bar_pctile`
  graveyard.csv columns) but have decided nothing since v1.4** — kept so pre-v1.4 and
  post-v1.4 rows stay comparable on the same columns, not because they're still load-bearing.
- **Gate 2 ("earns its place") and gate 3 ("not more painful").** Unchanged from v1.0 —
  Calmar/diversification and the 1.5x drawdown bound, respectively.
- **Paper-testing retirement.** Manual-only; the v1.2 kill criteria are advisory findings,
  never automatic actions (v1.6). See "Paper-testing verdicts" below, which is already
  written in current-state form and needs no translation.
- **Prelim screen (research-pipeline candidates only, v1.9).** `harness.prelim_screen()`
  is a cheap, lenient, CALIBRATION-ONLY (2007-2017) check a freshly proposed idea must
  clear before a real, pre-registered OOS test is worth running on it. It decides nothing
  about ALIVE/DEAD, touches no 2018+ data, costs no `family_n_tested()` draw, and never
  writes `graveyard.csv` — only its own `artifacts/prelim_log.csv`. Not part of the three
  gates above; a firewall upstream of them.
- **Pre-registration checkpoint (research-pipeline candidates only, v1.11) is FULLY
  AUTOMATIC.** A candidate that clears the prelim screen is committed to
  `STRATEGIES.md` the same run, no human review — Dave's explicit call. Every upstream
  safety property (calibration-only screening, segregated `n_tested`, the full OOS gate,
  v1.12) is unchanged; only this one checkpoint's human pause was removed.
- **OOS test + promotion cap for pre-registered pipeline candidates (v1.12).** Once
  pre-registered (v1.11), a candidate runs the SAME `evaluate()`/`noise_floor()` gate
  every other family goes through, against its own segregated `n_tested` bucket — no
  lighter bar for arriving via an automatic checkpoint. ALIVE promotes to a live paper
  book, capped at its OWN pool (`tradefabe.pipeline.MAX_PIPELINE_PROMOTED = 10`, Dave's
  explicit call, separate from `MAX_FACTORY_PROMOTED`). DEAD is terminal: one
  `graveyard.csv` row and nothing more, never promoted "anyway" the way the factory's
  original #98 mistake did.

**Forward-only, same as every amendment below states individually: nothing here re-scores
`graveyard.csv`.** This section is a reading aid, not a new rule — it changes no threshold,
adds no gate, and decides nothing that the amendments below didn't already decide.

## Data split

> **v1.0's original text, frozen verbatim below through "Ledger."** Eight amendments have
> since changed what several of these sections actually decide — see **"Current state"**
> above for what's active today, and **Amendment history** below for why. Kept unedited
> here because that's the pre-registration record rule 1 requires; it is not a description
> of current behavior on its own.

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

## Amendment history

The full derivation, in order, of everything summarized in "Current state" above — read
this for *why*, not to find out what's currently active.

- **v1.0.1 (2026-07-21).** The noise floor is computed **per rebalance frequency** (D/W/M):
  a strategy is judged against random strategies rebalanced at the SAME frequency, so fast
  strategies face a luck bar that pays the same fast trading costs. Engineering fix, not a
  gate change. A strategy's rebalance frequency is part of its pre-registered spec.
  (Gate 2's diversifier clause is under review per research/combine.py results; any change will be
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

- **v1.5 — CURRENT, IN FORCE since 2026-07-29 (#112, implemented in #120).** Pre-registered
  2026-07-28, one day before the implementation landed and *after* the last verdict scored
  under v1.4 (family M, #111) was recorded — deliberately, so v1.5 could not be the thing
  that decided a verdict. Family M's segregated `n_tested` would have been **23** against the
  v1.4 union of **139**; it would not have changed any of its three verdicts (gate 2 fails on
  all three and has no `n_tested` term), but that was established after the fact, not relied
  on beforehand.
  Two changes to gate 1's calibration, shipped **together** because they move the bar in
  opposite directions and settling only one leaves it knowingly mis-calibrated.

  **(a) The multiple-testing family is SEGREGATED by origin.** `family_n_tested()` previously
  returned `len(graveyard_names ∪ candidates)` — the all-time union, measured at **139** at
  pre-registration, of which **121 were factory-origin**. Every automated draw therefore raises the bar
  for every future hand-picked candidate, permanently. The #98 council resolved this and the
  resolution was never implemented:

  > a draw you would never act on is search; the promoted winner is a hypothesis

  Family-wise correction assumes you would have *accepted* any hypothesis you tested. The
  factory's draws fail that premise — they are steps in a search, not candidates anyone
  would trade. Nobody Bonferroni-corrects gradient descent for every step it visited. So:

  - a **factory** candidate is corrected against factory-origin rows only;
  - a **hand-picked** candidate is corrected against hand-picked rows only;
  - a **promoted** factory candidate joins the hand-picked family, because promotion *is*
    selection-on-result and that is exactly what the correction exists to price.

  Origin is determined by `factory.TEMPLATES` membership, a `_gen_` name, presence in
  `generated_templates.csv`, or combo status — all four are recorded at generation time,
  **before** any verdict, so origin can never be assigned to flatter a result. Measured
  split: 121 factory-origin, 15 hand-picked, 5 promoted-generated joining the main family.

  **(b) The duty-cycle-matched null is the DEFAULT, not opt-in.** v1.0.1 matched the
  null's *clock*; #101 showed matching the clock is not enough. Re-drawing a random signal
  every bar makes the null trade 3.7× more than a real monthly signal and 19.9× more daily,
  so it pays a turnover cost the candidate never does and gate 1 is systematically
  **lenient**. `noise_floor(..., like=)` has existed since #101 but defaults to `None`, and
  as of this pre-registration exactly one study passes it. Corrected, the monthly bar moves
  from p95 0.293 to **1.532**, and `tsmom_12m` (Sharpe 0.499) flips from clearing gate 1 to
  failing it.

  **Direction, stated honestly.** (a) makes ALIVE easier; (b) makes it harder. That is the
  point — the two errors were compounding, and correcting one alone would have replaced a
  known bias with a different known bias. Neither was chosen to produce a particular verdict:
  (a) was decided by the #98 council before family M existed, and (b) was measured in #101
  and left un-shipped.

  **Forward-only, and never re-scored.** Existing `graveyard.csv` rows keep the numbers they
  were given, exactly as v1.4 was not applied retroactively. Recomputing historical verdicts
  under v1.5 is legitimate **only as a diagnostic** — to learn whether the bar inflation was
  theoretical or buried something real — and its output is a finding to discuss, never a
  silent re-verdict. Adjusting the bar and then re-scoring is precisely the failure this lab
  exists to prevent.

  **Rows evaluated under v1.5 record `n_tested` under the segregated count and are not
  comparable to earlier rows' `n_tested` column.** That discontinuity is the cost of the fix
  and is stated here rather than left for a reader to discover.

- **v1.6 (2026-07-29, #113). Retirement is manual-only. The kill criteria are ADVISORY.**
  Resolves the tension #113 raised and refused to paper over: v1.2 defines four kill
  criteria for a paper book, but a monitor-only book exists to accumulate forward evidence,
  so acting on them automatically would destroy exactly what the book was opened to collect.

  Dave's call, and now the rule: **a paper book is retired only by explicit human
  instruction (`tradefabe retire <book> --reason "..."`), for every book, at any age, no
  exceptions.** No performance trigger, no drawdown threshold, no age rule, and no code path
  in the engine that sets the flag on its own.

  The v1.2 kill criteria are **unchanged in content and demoted in force**: they fire as
  *findings* — reported, discussed, recorded — never as actions. That keeps their real value,
  which was mostly diagnostic anyway. Criterion 1 (divergence) detects an implementation bug
  and is worth acting on the *code*; criteria 2 and 3 say "this book is losing", which for a
  monitor-only book is the observation, not a fault.

  **Why automatic retirement would have been a doctrine violation, not merely a bad
  default.** Auto-retiring the losers filters the forward record on results. The paper
  ledgers are the one dataset in this lab with no survivorship bias in them — no backfill, no
  selection, every book that was ever opened still reporting. Killing the bad ones would
  manufacture the bias this entire file exists to prevent, in the only place currently free
  of it, and would do it invisibly: the surviving books would look better as a group with no
  record of what was removed. A backtest curated that way would be rejected instantly here.

  **Retired means frozen, not deleted.** No further rebalances, no further marks; the history
  is preserved exactly, the book still appears in `summary.csv`, in `status`, and on the
  dashboard flagged `retired` with its reason and timestamp. `tradefabe unretire` reverses it
  and the gap stays visible on the equity chart rather than being filled in.

  **The accepted cost:** book count grows monotonically until Dave prunes it, and cycle time
  and ledger size grow with it (#113 measured 16 → ~46/month → ~381/year before the factory
  pause). That is a real operational cost, accepted deliberately in exchange for an unfiltered
  forward record. If it becomes binding the answer is to slow *promotion*, not to start
  culling — the factory pause (#98) is already that lever.

- **v1.7 (2026-07-29, #115). The benchmark window is aligned to the candidate's own OOS
  start, not just the flat `OOS_START`.** `evaluate()` sliced both series at the doctrine-wide
  `OOS_START` (2018-01-01) — which bounds how early either series' window may *start*, but
  does nothing for a candidate whose own data already starts later. That candidate's slice is
  a no-op (there's nothing earlier to exclude), while the benchmark still runs from whatever
  its own history allows, so the two end up scored over windows of different length covering
  different market regimes. Measured: `crypto_reversal_1h` (real data 2024-07+) was scored
  against a 60/40 measured from 2023-08 (Sharpe 1.189 vs 0.959 over its actual window) —
  immaterial to that DEAD verdict, but exactly the kind of gap that would decide a marginal
  one (RUNDOWN.md).

  **Fix:** both `r_oos` and `b_oos` are now sliced at `max(OOS_START, candidate's own first
  non-null observation)`, so the benchmark can never cover more calendar time than the
  candidate it's being compared to. This only ever narrows the benchmark window — a
  candidate's own OOS slice is unchanged, since `r_full[r_full.index >= OOS_START]` was
  already a no-op whenever the candidate's true start is later than `OOS_START`.

  **Orthogonal to family M's `OOS_START` override** (`kronos_backtest.py`'s
  `_use_kronos_window()`), which exists to keep the candidate, benchmark, AND the *null*
  (`noise_floor()`, computed separately from `evaluate()`) on Kronos's pretraining-cutoff
  window. This amendment only touches what `evaluate()` itself does with the benchmark;
  the override is still required and unchanged.

  **Forward-only, same as every prior amendment: no historical `graveyard.csv` row is
  re-scored.** The realignment changes gate 2 (Calmar/correlation) and gate 3 (drawdown
  limit) inputs, never gate 1 (DSR, which only ever depended on the candidate's own
  `r_oos` — unaffected, see above) — so only future gate-2/3 comparisons are affected.

- **v1.8 (2026-07-29, #114). Gate 1 requires the candidate's own Sharpe be positive, not
  just that it beats the null.** DSR compares the candidate's Sharpe to the expected best of
  `n_tested` draws from the noise floor; it has no floor requiring the candidate itself be
  profitable. When both the candidate and the null are negative and the null is the *more*
  negative of the two, DSR saturates at 1.0 — "beats luck" reads as a pass beside a strategy
  that is losing money. `.claude/agents/doctrine-auditor.md` already named this pathology;
  reproduced 2026-07-29: `carry_kronos_vol` scored Sharpe **−3.41** against a null with
  SR\* **−11.09** — DSR 1.000, `beats_luck` True. Gates 2 and 3 killed it correctly (no wrong
  verdict was ever issued), but gate 1 carried zero information on that row while reading as
  a pass. `graveyard.csv` has 75 rows with negative `oos_sharpe`; several already show
  `dsr=1.000` under the same pathology (the `donchian_gen_*` factory draws,
  `crypto_reversal_1h`, `equity_tsmom_1h`) — all correctly DEAD via gates 2/3.

  **Fix:** `dsr_gate1()`'s `beats_luck` is now `dsr > 0.95 AND oos_sharpe > 0`.

  **Direction: strictly tightens gate 1** — can only turn a previous True into False, never
  the reverse (`dsr > 0.95` is still required either way). **Checked against the full
  ledger: 0 of 75 negative-`oos_sharpe` rows are ALIVE**, so this closes an informational gap
  (a misleading "pass" on an already-DEAD row), not a decision gap — no historical verdict
  would flip under it. Forward-only, per every prior amendment: no `graveyard.csv` row is
  re-scored.

- **v1.9 (2026-08-01, #175). The calibration-only prelim firewall, for the daily
  automated research pipeline (#174).** Not a change to gates 1-3 — a new, separate
  mechanism upstream of them, added because the pipeline this amendment serves has a
  failure mode nothing above already guards against: filtering a freshly-proposed idea by
  whether a cheap look "seems promising" is itself selection-on-results (data-snooping)
  unless that look is firewalled from the OOS window every real verdict is rendered on.
  Pre-registered here, before #174's pipeline exists to run it against anything, per rule
  1 — the same reason DOCTRINE.md itself predates the strategy zoo it judges.

  **Mechanism.** `harness.prelim_screen(candidate_spec) -> bool`. Loads prices and
  truncates to `CALIB_START`-`CALIB_END` (2007-2017, identical to v1.0's own "Data split")
  *before* building the signal, the returns, or the null — the firewall is which rows are
  missing from memory, not a downstream filter with a bug surface. Passes if the
  candidate's own calibration Sharpe is positive AND beats a calibration-window noise
  floor's **median** (p50, not the p95/DSR bar gate 1 uses) — deliberately far short of
  the real bar. This screen has exactly one job: don't kill a real idea before OOS ever
  sees it. A false PASS here costs one wasted OOS test later (cheap, recoverable); a false
  FAIL discards a genuine edge permanently with no record it was ever proposed. A lenient
  bar buys a low false-negative rate at the cost of a higher false-positive one, on
  purpose.

  **What this explicitly does NOT do.** Decide ALIVE/DEAD (only gates 1-3, on OOS data,
  do that). Touch `graveyard.csv` (every call, pass or fail, logs only to its own
  `artifacts/prelim_log.csv` — a separate, dedicated, audit-only ledger). Cost a
  `family_n_tested()` draw (that function reads `graveyard.csv` and
  `generated_templates.csv` only; `prelim_log.csv` is deliberately invisible to it, the
  same way a factory candidate that's never drawn costs nothing). Read anything dated
  after `CALIB_END` — confirmed by `tests/test_prelim_screen.py`'s calibration-blindness
  test, which mutates the post-`CALIB_END` portion of synthetic price data and asserts
  the verdict doesn't move, the same discipline `pairs_backtest.py`'s own
  `fit_pair()` test used for #172.

  **Scope.** Applies only to candidates entering through the research pipeline (#174).
  Every existing path — hand-picked strategies, the factory (#28/#163) — is unaffected;
  neither has ever needed a pre-OOS screen because neither proposes genuinely new
  strategy families the way this pipeline will. Nothing here changes what counts as
  ALIVE or DEAD for any candidate already in `graveyard.csv`, or how one gets there.

- **v1.10 (2026-08-01, #176). A third `n_tested` bucket: research-pipeline origin,**
  extending v1.5's segregation-by-origin pattern rather than replacing it. Pre-registered
  before #174's pipeline has a candidate to propose — same reason v1.9 was pre-registered
  before that pipeline could run anything through it, and unlike v1.5 itself, which was a
  reactive fix (#101/#112) to a problem already running.

  **Why a third bucket, not reuse of the factory's.** v1.5 exists because a search's draws
  are steps in a search, not candidates anyone would trade, and correcting hand-picked
  candidates against them prices out every real strategy. That argument applies to the
  research pipeline exactly as it applies to the factory — but the two are DIFFERENT
  searches over DIFFERENT spaces (parameter variants of known families vs. genuinely new
  strategy families, per #174's own scope). Folding pipeline draws into the factory's
  bucket, or vice versa, would correct one search against a search it has nothing to do
  with — arbitrary in exactly the way v1.5 called out family-wise correction assuming
  "you would have accepted any hypothesis you tested."

  **Mechanism.** `harness.is_pipeline_origin()` / `pipeline_origin_names()`, mirroring
  `is_factory_origin()` / `factory_origin_names()` exactly: a fixed naming convention
  (`PIPELINE_NAME_PREFIX = "rp_"`) plus a proposal-time ledger (`PIPELINE_LEDGER`,
  `pipeline_ideas.csv` at repo root, tracked in git like `generated_templates.csv`)
  that #177 (idea generation, not yet built) must write
  BEFORE `prelim_screen()` (#175) even runs on a name — the same before-the-result
  guarantee every existing origin marker already carries. `family_n_tested()` now
  classifies each candidate into exactly one of three families (factory / pipeline /
  hand-picked, with a promoted candidate from EITHER automated origin joining hand-picked
  per v1.5's own logic) and unions whichever bucket(s) a candidate set touches — the same
  conservative-union rule v1.5 used for a mixed factory/hand-picked set, extended to three.

  **Confirms the design question #176 raised explicitly:** yes, a candidate that PASSES
  the prelim screen but fails the real OOS test still counts as a research-pipeline draw
  — it reached `graveyard.csv`, exactly like a factory draw that clears its own screening
  step but dies OOS. The prelim screen filters what's worth an OOS test; it does not
  change which bucket the OOS test itself is corrected against.

  **`PIPELINE_LEDGER` returns empty, and `is_pipeline_origin()` only matches by naming
  convention, until #177 exists to write it** — the same bootstrap state
  `GENERATED_LEDGER` was in before the factory existed. This bucket is inert (never
  selected, since nothing is named `rp_*` or logged yet) until the pipeline's first real
  candidate.

  **Forward-only, same as v1.5: no `graveyard.csv` row scored before this amendment is
  reclassified.** A row's `n_tested` reflects the bucket definition in force when it was
  written; comparing `n_tested` across amendments was never valid and remains not so.

- **v1.11 (2026-08-01, #179). The pre-registration checkpoint is FULLY AUTOMATIC.** A
  candidate that clears #175's prelim screen is frozen to `STRATEGIES.md` and a durable
  ledger (`pipeline_preregistered.csv`) the same run, no PR, no human review, before the
  full OOS test (#180) fires. Dave's explicit call, stated honestly
  rather than glossed over: #179's own design question leaned the other way ("pre-
  registration is supposed to be a real commitment made with judgment, not a rubber
  stamp a script clears on its way to the next step"), and that argument is not wrong —
  it is simply outweighed here by the pipeline's actual point, a genuinely hands-off
  daily cycle. A human bottleneck at this specific checkpoint would make the pipeline
  "propose + screen automatically, human approves the expensive step," not the thing
  #174 set out to build.

  **What "automatic" does NOT weaken.** Every upstream safety property this pipeline
  already has stays exactly as strict: the candidate still had to clear #175's
  calibration-only firewall (never touching OOS data to get here), it is still
  segregated into its own `n_tested` bucket (v1.10) so it cannot inflate the bar for
  hand-picked or factory candidates, and #180's own OOS test — once built — is the SAME
  DSR/CPCV gate every strategy in this lab goes through, no lighter bar for having
  arrived via an automatic checkpoint. What's removed is only the pause between
  "cheaply screened as promising" and "worth the expensive test" — the ONE step in the
  whole pipeline where a human's judgment was optional rather than load-bearing to a
  safety property.

  **Mechanism.** `research/pipeline_register.py`'s `preregister_candidate()` renders the
  validated proposal (#177's full spec — primitive, params, freq, rationale, citation)
  as programmatically-generated STRATEGIES.md prose — the same information every
  hand-tested family's pre-registration carries, minus a human writing it — and stamps
  `pipeline_preregistered.csv` (append-only, mirroring every other ledger in this repo)
  so #180 has a machine-readable way to find "pre-registered, not yet OOS-tested"
  candidates without parsing markdown. Idempotent by name, same as `factory.promote()`.

  **Reversible if it goes wrong.** Nothing here is a one-way door: #181's kill switch
  (not yet built) can pause the whole daily cycle, and — worst case — a bad automatic
  pre-registration is a `STRATEGIES.md` edit and a graveyard row like any other, not
  real capital or an unrecoverable action. If automatic pre-registration produces a
  pattern of regrettable commits, the fix is switching this one checkpoint back to
  human-in-the-loop, not redesigning the pipeline.

- **v1.12 (2026-08-04, #180). The OOS test runner + promotion cap for pre-registered
  pipeline candidates.** `research/pipeline_verdict.py`'s `run_pending_oos_tests()`
  finds every candidate pre-registered (v1.11) with no `graveyard.csv` row yet
  (`pipeline_preregistered.csv` minus `harness.graveyard_strategy_names()`), rebuilds
  its signal from the spec `research/pipeline_ideas.py` logged at proposal time
  (`PIPELINE_LEDGER`), and runs it through the exact same `evaluate()`/`noise_floor()`
  gate every family in this lab goes through — DSR/CPCV, the same three kill gates, no
  lighter bar for having arrived via an automatic pre-registration checkpoint. `n_tested`
  is the pipeline's own segregated bucket (v1.10): a pipeline candidate's `rp_` prefix
  classifies it automatically, so it is corrected against pipeline-origin draws only,
  never inflating the bar for hand-picked or factory candidates.

  **Promotion is capped, and the cap is its OWN pool.** #180's own issue text raised
  this explicitly as an open design question — share `MAX_FACTORY_PROMOTED` (#147), or
  get a separate one? Dave's explicit call (2026-08-04): separate.
  `tradefabe.pipeline.MAX_PIPELINE_PROMOTED = 10`, not the factory's 20 — appropriate
  given the pipeline proposes at most ONE candidate/day (#177's rate limit) against the
  factory's ~20/cycle, so this pool was always going to fill far slower regardless of
  the exact number. At/over the cap, a candidate is still evaluated and logged; it just
  doesn't promote until a slot is freed by `tradefabe retire`, mirroring #147's own
  "not a retirement path" property exactly.

  **DEAD is terminal — explicitly, not by omission.** A DEAD verdict gets its one
  `graveyard.csv` row and nothing else happens: no promotion "anyway," no exception.
  This is the factory's own original mistake (#98) named directly in #180's issue text
  as the failure mode to not repeat — the factory's "best of cycle, regardless of
  verdict" rule exists only because it always promotes exactly one candidate per cycle
  to preserve research value even on a day nothing is a real edge; the pipeline has no
  such per-cycle quota; a DEAD pipeline candidate is simply DEAD.

  **Mechanism for a promoted book.** `tradefabe.pipeline.promote_pipeline()` is a new
  registry (`promoted_pipeline.json`), same shape as `factory.promote_generated()` —
  idempotent by name, carries primitive+params so a fresh process can rebuild the exact
  signal. Wired into `harness.promoted_names()` (so a promoted pipeline candidate
  rejoins the hand-picked family for `n_tested`, same as a promoted factory candidate
  already does) and into `runner.py`'s `PIPELINE_BOOKS`/`ALL_BOOKS` (so `tradefabe run`
  actually rebalances it). The primitive vocabulary and `build_signal()` moved from
  `research/pipeline_ideas.py` to `src/tradefabe/pipeline.py` for this — `runner.py` is
  part of the INSTALLED package and needs to reconstruct a promoted candidate's signal
  with no `research/`-relative `PYTHONPATH`, the same reason `factory.rebuild_signal()`
  already lives in the package rather than in `research/factory_run.py`.

## Paper-testing verdicts (v1.2, retirement clause amended by v1.6)

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

This is the exact rule the strategy factory's best-of-cycle promotion (#28b) falls
under, not a new exception: `factory_run.py` promotes the single best-ranked candidate
each research cycle (by CPCV-resampled OOS Sharpe, not raw DSR — #145) to a live paper
book regardless of verdict, so a promoted DEAD candidate is monitor-only under this
same clause — more live-tracked data by design (Dave's explicit call), never a route to
`paper-confirmed` on its own.

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

### Kill criteria (can fire any time after month 3) — ADVISORY ONLY since v1.6
**These are findings, not actions.** A book that meets a criterion below is flagged,
reported, and discussed; it is **not** retired, and nothing in the engine retires it. Only
`tradefabe retire <book> --reason "..."`, run by Dave, stops a book. See v1.6 above for why:
auto-killing the losers would filter the forward record on results, which is the one place in
this lab currently free of survivorship bias.

Criterion 1 is the one that should usually provoke *action*, and the action is on the code —
a divergence means a live bug, and fixing the bug is not the same as retiring the book.
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
