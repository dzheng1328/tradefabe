"""
harness.py — the reusable evaluation harness that enforces DOCTRINE.md.

Plug in a strategy (a function `prices -> signal matrix` plus a rebalance frequency)
and the harness judges it out-of-sample against:
  1. a DATA-DERIVED noise floor (random strategies through the SAME machinery at the
     SAME rebalance frequency, so fast strategies face a luck bar that pays fast costs),
  2. a fair 60/40 benchmark, and
  3. the pre-registered kill rule.
Every verdict — alive or dead — is appended to graveyard.csv, and render-ready
artifacts are written to artifacts/ for the dashboard (app.py).

Engine core (data, sizing, returns, stats) and signal functions now live in the
installed package (tradefabe.engine / tradefabe.signals); this file keeps only the
doctrine: the noise floor, the fair benchmark, and the three-gate verdict.
"""
from __future__ import annotations
import os
import json
import datetime
from itertools import combinations
from statistics import NormalDist
import numpy as np
import pandas as pd
from tradefabe.engine import (load_prices, stats, ANN, VOL_WINDOW, TARGET_VOL,
                              MAX_LEG, MAX_GROSS, COST_BPS, LOOKBACK, BASE, BENCH_W,
                              realized_vol, _reb_mask, size_and_rebalance,
                              net_returns, calmar)
from tradefabe.signals import (sig_tsmom_12m as sig_tsmom, sig_tsmom_ensemble,
                               sig_xsec_momentum, sig_green_line_200d as sig_green_line,
                               sig_str_reversal, sig_low_vol,
                               sig_turn_of_month_research as sig_turn_of_month, sig_random)

# ---- frozen doctrine parameters (see DOCTRINE.md) ----
OOS_START   = pd.Timestamp("2018-01-01")
CALIB_START = pd.Timestamp("2007-01-01")   # DOCTRINE's design/calibration window (v1.0's
CALIB_END   = pd.Timestamp("2017-12-31")   # "Data split") -- prelim_screen() below is the
                                            # only thing in this file allowed to look here;
                                            # everything else in harness.py is OOS-only.
NULL_TRIALS = 500
NULL_PCTILE = 95        # vestigial, not a threshold (comment fixed under #116): v1.0's
                         # original decision bar, superseded by bonferroni_bar() (v1.3),
                         # itself superseded as the ACTIVE decision by dsr_gate1() (v1.4).
                         # Kept only for main()'s meta.json artifact and continuity with
                         # rows logged before either supersession; decides nothing today.
BONFERRONI_ALPHA = 0.05  # family-wise false-positive rate target across EVERY strategy ever tested
CORR_DIV    = 0.30
DD_MULT     = 1.5
GRAVEYARD   = os.path.join(BASE, "graveyard.csv")
ART         = os.path.join(BASE, "artifacts")


# ---------- multiple-testing correction (DOCTRINE v1.3) ----------
def graveyard_strategy_names():
    if not os.path.exists(GRAVEYARD):
        return set()
    return set(pd.read_csv(GRAVEYARD)["strategy"].unique())


GENERATED_LEDGER = os.path.join(BASE, "generated_templates.csv")


def _factory_ledger_names() -> set[str]:
    """Names recorded as factory-origin in a ledger written at GENERATION time.

    `factory.TEMPLATES` is source code reviewed once; `generated_templates.csv` is
    append-only and written when a candidate is DRAWN, before its verdict is known. Both
    predate any result, which is what stops origin from being assigned after the fact to
    flatter one."""
    out: set[str] = set()
    try:
        from tradefabe import factory
        out |= set(factory.TEMPLATES)
    except Exception:                                    # noqa: BLE001
        pass
    if os.path.exists(GENERATED_LEDGER):
        try:
            gt = pd.read_csv(GENERATED_LEDGER)
            for col in ("name", "strategy"):
                if col in gt.columns:
                    out |= set(gt[col].dropna().astype(str))
                    break
        except Exception:                                # noqa: BLE001
            pass
    return out


def is_factory_origin(name: str) -> bool:
    """Whether `name` came out of the automated search (DOCTRINE v1.5, #112).

    A PREDICATE on the name, deliberately -- not a lookup restricted to rows already in
    graveyard.csv. Classification happens at EVALUATION time, when a brand-new candidate
    has no row yet, so a ledger-only test silently misfiled every first-time candidate
    into the hand-picked family. `factory_combo_*` was the case that caught it.

    Naming conventions (`_gen_`, `combo`) are fixed in `factory.py` before any candidate is
    drawn, so they carry the same before-the-result guarantee the ledgers do.
    """
    return ("_gen_" in name or "combo" in name.lower()
            or name in _factory_ledger_names())


def factory_origin_names() -> set[str]:
    """Every known factory-origin name: the generation-time ledgers, plus any graveyard row
    matching the naming conventions."""
    return _factory_ledger_names() | {n for n in graveyard_strategy_names()
                                      if is_factory_origin(n)}


# ---------- research-pipeline origin (DOCTRINE v1.10, #176) ----------
# A THIRD n_tested bucket, alongside factory-origin above and hand-picked (the residual
# below) -- for #174's daily automated research pipeline, which proposes genuinely NEW
# strategy families (the way pairs/cointegration or VRP were proposed by hand this
# session), not parameter sweeps of families that already exist. Same rationale as v1.5's
# factory bucket: a pipeline draw nobody acted on is search, not a hypothesis anyone would
# trade, so it must not inflate the bar for hand-picked candidates -- but it must also not
# get folded into the FACTORY bucket, since it is a different search over a different
# space and correcting it against factory draws (or vice versa) would be just as arbitrary
# as correcting it against nothing at all.
#
# Fixed here, before #177 (idea generation) exists to draw on it -- same before-the-result
# guarantee PIPELINE_NAME_PREFIX and PIPELINE_LEDGER give is_factory_origin()'s own
# conventions. #177 MUST prefix every name it proposes with PIPELINE_NAME_PREFIX and log
# it to PIPELINE_LEDGER at proposal time, before prelim_screen() (#175) even runs.
PIPELINE_NAME_PREFIX = "rp_"
PIPELINE_LEDGER = os.path.join(BASE, "pipeline_ideas.csv")


def _pipeline_ledger_names() -> set[str]:
    """Mirrors _factory_ledger_names(): an append-only ledger written at PROPOSAL time,
    before any prelim screen or verdict. Returns empty until #177 exists to write it --
    same as GENERATED_LEDGER returned empty before the factory existed."""
    out: set[str] = set()
    if os.path.exists(PIPELINE_LEDGER):
        try:
            pl = pd.read_csv(PIPELINE_LEDGER)
            for col in ("name", "strategy"):
                if col in pl.columns:
                    out |= set(pl[col].dropna().astype(str))
                    break
        except Exception:                                # noqa: BLE001
            pass
    return out


def is_pipeline_origin(name: str) -> bool:
    """Whether `name` came from the research pipeline (#174), not the factory or a
    hand-picked idea. A PREDICATE, for the same reason is_factory_origin() is one: a
    brand-new candidate has no graveyard row or ledger entry yet at classification time.

    PIPELINE_NAME_PREFIX is fixed and disjoint from the factory's own conventions
    (`_gen_`, `combo`) by construction -- see test_a_pipeline_name_is_never_also_factory_
    origin. If #177 ever needs a name that could collide with either, the prefix -- not
    this check -- is what has to change, and it must change before the first name using
    it is proposed, not after."""
    return name.startswith(PIPELINE_NAME_PREFIX) or name in _pipeline_ledger_names()


def pipeline_origin_names() -> set[str]:
    """Every known pipeline-origin name: the proposal-time ledger, plus any graveyard row
    matching the naming convention."""
    return _pipeline_ledger_names() | {n for n in graveyard_strategy_names()
                                       if is_pipeline_origin(n)}


def promoted_names() -> set[str]:
    """Candidates from ANY automated origin (factory or pipeline) PROMOTED to a live
    paper book.

    These rejoin the hand-picked family regardless of which search found them: promotion
    IS selection-on-result, which is exactly the thing a multiple-testing correction
    exists to price. A draw nobody acted on is search; the one that got a book is a
    hypothesis. #180 added the pipeline's own promotion registry (tradefabe.pipeline.
    load_promoted_pipeline()) below, the same way the factory's three already were --
    this function's whole contract is every promotion registry that exists, not the
    factory's specifically."""
    out: set[str] = set()
    try:
        from tradefabe import factory, pipeline
        loaders = [(factory, "load_promoted"), (factory, "load_promoted_generated"),
                  (factory, "load_promoted_combos"), (pipeline, "load_promoted_pipeline")]
        for module, loader in loaders:
            fn = getattr(module, loader, None)
            if fn is None:
                continue
            for item in (fn() or []):
                name = item.get("name") if isinstance(item, dict) else item
                if isinstance(name, str):
                    out.add(name)
    except Exception:                                    # noqa: BLE001
        pass
    return out


def family_n_tested(candidate_names):
    """Size of the multiple-testing family, SEGREGATED BY ORIGIN (DOCTRINE v1.5, #112;
    extended to a third bucket by v1.10, #176).

    Family-wise correction assumes you would have ACCEPTED any hypothesis you tested. An
    automated search's draws fail that premise -- they are steps in a search, not
    candidates anyone would trade, and nobody Bonferroni-corrects gradient descent for
    every step it visited. Counting the factory's draws against hand-picked candidates
    took the required Sharpe from 1.58 (12 tested) to 2.52 (136) and was heading for 3.63,
    pricing out every real strategy -- the same failure mode a second, unsegregated search
    would reintroduce if it shared either existing bucket.

    So:
      * a FACTORY candidate is corrected against factory-origin rows only;
      * a PIPELINE candidate is corrected against pipeline-origin rows only;
      * a HAND-PICKED candidate against hand-picked rows plus PROMOTED rows from either
        automated origin;
      * a set spanning more than one origin gets the union of whichever buckets are
        represented -- the conservative reading rather than a convenient one.

    Pre-v1.5 this was `len(graveyard ∪ candidates)` -- the all-time union. Rows scored
    before v1.5 keep that number and are NOT comparable to rows scored after; the change is
    forward-only and no historical verdict is ever re-scored under it. Same forward-only
    rule for v1.10's third bucket: no row scored before it existed is reclassified.
    """
    gy = graveyard_strategy_names()
    factory_rows = factory_origin_names()
    pipeline_rows = pipeline_origin_names()
    promoted = promoted_names()
    cands = set(candidate_names)

    fam_factory = (gy & factory_rows) - promoted - pipeline_rows
    fam_pipeline = (gy & pipeline_rows) - promoted - factory_rows
    fam_hand = (gy - factory_rows - pipeline_rows) | (gy & promoted)

    # Classify each candidate by PREDICATE, not by graveyard membership -- a first-time
    # candidate has no row yet, and a lookup would misfile every one of them. A promoted
    # candidate is hand-picked regardless of which search found it (see promoted_names()).
    def _origin(c):
        if c in promoted:
            return "hand"
        if is_pipeline_origin(c):
            return "pipeline"
        if is_factory_origin(c):
            return "factory"
        return "hand"

    origins = {_origin(c) for c in cands}
    family = set()
    if "factory" in origins:
        family |= fam_factory
    if "pipeline" in origins:
        family |= fam_pipeline
    if "hand" in origins:
        family |= fam_hand
    return len(family | cands)


def last_verdict(name):
    """The most recent logged verdict ("ALIVE"/"DEAD") for `name`, or None if it's never
    been evaluated. For callers that need to react to a JUST-WRITTEN evaluate() row
    (e.g. the strategy factory deciding whether to promote a candidate, #29) without
    evaluate() itself needing to change its return contract."""
    if not os.path.exists(GRAVEYARD):
        return None
    rows = pd.read_csv(GRAVEYARD)
    rows = rows[rows["strategy"] == name]
    return rows.iloc[-1]["verdict"] if len(rows) else None


def rows_for(names):
    """The most recent logged graveyard row for each of `names`, as a DataFrame (one row
    per name, indexed 0..n-1) -- for callers that need to RANK several just-evaluated
    candidates against each other at once (e.g. the strategy factory picking a cycle's
    best-ranked performer regardless of verdict, #28b/#145) without one file read per name.
    Empty DataFrame if graveyard.csv doesn't exist or none of `names` are in it."""
    if not os.path.exists(GRAVEYARD):
        return pd.DataFrame()
    gy = pd.read_csv(GRAVEYARD)
    gy = gy[gy["strategy"].isin(names)]
    return gy.drop_duplicates("strategy", keep="last").reset_index(drop=True)


def bonferroni_bar(null, n_tested, alpha=BONFERRONI_ALPHA):
    """The kill rule's luck bar, corrected for how many strategies have been tested
    (graveyard.csv's own count -- DOCTRINE.md v1.0.1 logged this as a future tightening;
    v1.3 makes it the active bar). Standard Bonferroni: per-test significance alpha /
    n_tested. `null`'s own empirical distribution can only resolve percentiles down to
    roughly 1-in-len(null) trials; once the corrected percentile needs finer resolution
    than that, falls back to a normal approximation fit to the null's own mean/std
    (stdlib statistics.NormalDist's exact inverse-CDF -- no new dependency). Returns
    (bar, method, pctile_used) so the verdict can log exactly which regime applied.
    Superseded as the active gate-1 decision by `deflated_sharpe_ratio()` under DOCTRINE
    v1.4 -- kept and still logged for continuity/comparison, same as v1.0's flat p95
    stayed visible in the ledger after v1.3 stopped using it to decide."""
    n_tested = max(int(n_tested), 1)
    pctile = 100 * (1 - alpha / n_tested)
    finest = 100 * (1 - 1 / len(null))
    if pctile <= finest:
        return float(np.percentile(null, pctile)), "empirical", pctile
    mu, sigma = float(np.mean(null)), float(np.std(null, ddof=1))
    z = NormalDist().inv_cdf(1 - alpha / n_tested)
    return mu + z * sigma, "normal-approx", pctile


# ---------- DOCTRINE v1.4: Deflated Sharpe Ratio + Combinatorial Purged CV ----------
# Replaces Bonferroni as the active gate-1 decision (bonferroni_bar() above stays, logged
# for continuity). Motivation (issue #27): Bonferroni's flat alpha/n_tested division gets
# crushingly strict and mathematically crude at the trial counts a high-volume automated
# strategy search implies, and a single fixed 2018+ OOS window is one draw from history --
# some candidates will beat that one slice by chance alone as search volume grows. Both
# fixed by the same paper lineage (Bailey & Lopez de Prado) already implicit in this
# project's empirical-then-normal-approx bar.
EULER_MASCHERONI = 0.5772156649015329


def _moments(r):
    """Population skewness/kurtosis of a return series, in the convention the PSR formula
    below expects: kurtosis == 3 for a Normal distribution (NOT excess/Fisher kurtosis,
    where Normal == 0). Computed directly from central moments -- no scipy dependency.
    Falls back to Normal moments (0, 3) if there's too little data or zero variance to
    estimate higher moments meaningfully."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return 0.0, 3.0
    mu, sigma = r.mean(), r.std(ddof=0)
    if sigma == 0:
        return 0.0, 3.0
    z = (r - mu) / sigma
    return float(np.mean(z ** 3)), float(np.mean(z ** 4))


def probabilistic_sharpe_ratio(sr_observed, sr_benchmark, n_obs, skew=0.0, kurtosis=3.0):
    """PSR(SR*) -- Bailey & Lopez de Prado (2012), "The Sharpe Ratio Efficient Frontier."
    Probability the TRUE Sharpe ratio exceeds `sr_benchmark`, given an estimate
    `sr_observed` from `n_obs` observations, correcting for non-Normal skew/kurtosis in
    the return series the Sharpe was estimated from. `sr_observed` and `sr_benchmark` must
    be on the SAME scale as each other and as whatever periodicity `n_obs` counts (e.g.
    both daily-scale Sharpes with n_obs = number of daily returns) -- this project's
    `stats()` reports ANNUALIZED Sharpe; callers must divide by sqrt(ANN) before calling
    this (annualized/sqrt(ANN) recovers the exact native-frequency Sharpe, since that's
    precisely how `stats()` built it in the first place -- not an approximation).
    Returns a probability in [0, 1]; n_obs < 2 returns 0.5 (no information either way)."""
    if n_obs < 2:
        return 0.5
    denom = max(1 - skew * sr_observed + (kurtosis - 1) / 4 * sr_observed ** 2, 1e-12)
    z = (sr_observed - sr_benchmark) * np.sqrt(n_obs - 1) / np.sqrt(denom)
    return NormalDist().cdf(z)


def expected_max_sharpe(trial_mean, trial_std, n_trials):
    """E[max(SR_hat_n)] under n_trials independent draws from a Normal(trial_mean,
    trial_std) null -- Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio,"
    extreme-value approximation. `trial_mean`/`trial_std` here are the mean/std of this
    project's own data-derived noise floor (`null` -- the SAME input `bonferroni_bar()`
    already uses), `n_trials` is `family_n_tested()` -- the SAME N Bonferroni corrects for.
    This is the "what's the best Sharpe you'd see by pure luck, drawing n_trials random
    strategies from this exact noise floor" bar a real candidate has to beat. Requires
    n_trials >= 2 (there's no "expected max" of one draw); below that, returns
    `trial_mean` unadjusted -- no multiple-testing correction to apply yet, same
    convention as `bonferroni_bar`'s n_tested<1 clamp."""
    if n_trials < 2:
        return float(trial_mean)
    nd = NormalDist()
    term1 = nd.inv_cdf(1 - 1.0 / n_trials)
    term2 = nd.inv_cdf(1 - 1.0 / (n_trials * np.e))
    return float(trial_mean + trial_std * ((1 - EULER_MASCHERONI) * term1 + EULER_MASCHERONI * term2))


def deflated_sharpe_ratio(sr_observed, null, n_tested, n_obs, skew=0.0, kurtosis=3.0):
    """DOCTRINE v1.4's active gate-1 test. Deflates `sr_observed` (this candidate's own
    OOS Sharpe -- see `cpcv_oos_sharpes()` for a resampled, more robust estimate of it)
    against the Sharpe you'd expect to see by PURE LUCK as the BEST of `n_tested` random
    draws from this project's own empirical noise floor (`null`) -- replacing
    Bonferroni's flat per-test-alpha division with an extreme-value correction that
    accounts for the null's actual spread, not just its count. All Sharpe-scale inputs
    (`sr_observed`, `null`) must be native-frequency (not annualized) -- see
    `probabilistic_sharpe_ratio`'s docstring. Returns (dsr, sr_star): dsr is the
    probability [0, 1] the candidate's true Sharpe exceeds sr_star; a candidate clears
    gate 1 when dsr > 0.95 (same p95 convention DOCTRINE v1.0 started with)."""
    null = np.asarray(null, dtype=float)
    sr_star = expected_max_sharpe(float(np.mean(null)), float(np.std(null, ddof=1)), n_tested)
    dsr = probabilistic_sharpe_ratio(sr_observed, sr_star, n_obs, skew, kurtosis)
    return dsr, sr_star


def cpcv_splits(n_obs, n_groups=6, n_test_groups=2, embargo=5):
    """Combinatorial Purged CV split indices -- Lopez de Prado (2017). Splits `n_obs`
    sequential observations into `n_groups` contiguous blocks and enumerates every
    combination of `n_test_groups` blocks held out as one test path (C(n_groups,
    n_test_groups) combinations total) -- a resampled distribution of OOS windows drawn
    from the SAME history, instead of trusting the one fixed 2018+ window. EMBARGOES
    `embargo` observations at the start of every test block that immediately follows a
    train block, dropping them from the test path: a lookback-window signal (this
    project's strategies use trailing windows up to 252 days) computed near a train/test
    boundary can leak train-period information into the first few test observations
    otherwise. Returns a list of 1-D numpy index arrays (test indices only -- every
    strategy in this project is a frozen, pre-registered formula with nothing to fit on a
    train fold, so only the test path is needed for a resampled OOS Sharpe; the train
    fold exists in the split boundaries here for future callers that DO fit parameters,
    e.g. the strategy factory, #28)."""
    groups = np.array_split(np.arange(n_obs), n_groups)
    paths = []
    for test_ids in combinations(range(n_groups), n_test_groups):
        test_ids = set(test_ids)
        idx = []
        for i, g in enumerate(groups):
            if i not in test_ids:
                continue
            if (i - 1) not in test_ids and i > 0:
                g = g[embargo:]
            idx.append(g)
        if idx:
            concatenated = np.concatenate(idx)
            if len(concatenated):
                paths.append(concatenated)
    return paths


def cpcv_oos_sharpes(r, n_groups=6, n_test_groups=2, embargo=5):
    """Apply cpcv_splits() to a return series and compute the NATIVE-FREQUENCY (not
    annualized) Sharpe of each resampled test path -- a real empirical distribution of
    "how sensitive is this candidate's apparent edge to which slice of history we
    happened to look at," rather than the single point estimate `evaluate()` used to
    rely on alone. Returns a numpy array, one Sharpe per combinatorial path (skips paths
    with too few observations or zero variance rather than filling them with a fake 0)."""
    r = pd.Series(r).dropna().reset_index(drop=True)
    n = len(r)
    if n < n_groups * 2:
        return np.array([])
    out = []
    for idx in cpcv_splits(n, n_groups, n_test_groups, embargo):
        path = r.iloc[idx]
        if len(path) < 30 or path.std() == 0:
            continue
        out.append(float(path.mean() / path.std()))
    return np.array(out)


# name -> (signal_fn, rebalance freq). Freq is part of the strategy spec, pre-registered.
# turn_of_month uses the research (trading-day) variant; the live paper book uses the
# calendar variant — see tradefabe.signals for why they differ.
STRATEGIES = {
    "tsmom_12m":       (sig_tsmom,          "M"),
    "tsmom_ensemble":  (sig_tsmom_ensemble, "M"),
    "xsec_momentum":   (sig_xsec_momentum,  "M"),
    "green_line_200d": (sig_green_line,     "M"),
    "str_reversal_5d": (sig_str_reversal,   "W"),
    "low_vol_xsec":    (sig_low_vol,        "M"),
    "turn_of_month":   (sig_turn_of_month,  "D"),
}


# ---------- fair benchmark (60/40) ----------
def benchmark_returns(prices):
    cols = [c for c in BENCH_W if c in prices.columns]
    tot  = sum(BENCH_W[c] for c in cols)
    w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    for c in cols:
        w[c] = BENCH_W[c] / tot
    m = _reb_mask(prices.index, "M")
    mask = pd.DataFrame(np.tile(m.values.reshape(-1, 1), (1, w.shape[1])),
                        index=w.index, columns=w.columns)
    w = w.where(mask).ffill().fillna(0.0)
    return net_returns(prices, w)


# ---------- the data-derived noise floor (per rebalance frequency) ----------
_NULL_CACHE: dict = {}


def _prices_fingerprint(prices):
    """Content hash, so a mutated frame misses the cache rather than reusing a stale null."""
    return (prices.shape, tuple(prices.columns),
            int(pd.util.hash_pandas_object(prices, index=True).sum()))


def sig_rotated(signal, rng):
    """A random circular time-shift of `signal`.

    This is the duty-cycle-matched null. `sig_random()` re-draws every bar, so a random
    strategy flips sign at nearly every rebalance while a real trend signal mostly holds
    its position -- measured 3.7x the turnover of `tsmom_12m` monthly and 19.9x daily.
    Since cost scales with turnover, that hands the null a penalty the candidate never
    pays and makes gate 1 systematically LENIENT.

    A rotation preserves the signal's turnover and persistence EXACTLY (same sequence,
    different offset) while destroying any alignment with future returns -- which is
    precisely the null hypothesis gate 1 is supposed to test: "could a strategy that
    trades like this one produce this Sharpe with no predictive content?" """
    k = int(rng.integers(1, len(signal)))
    return pd.DataFrame(np.roll(signal.values, k, axis=0),
                        index=signal.index, columns=signal.columns)


def noise_floor(prices, freq, trials=NULL_TRIALS, rv=None, like=None):
    """Sharpe distribution of `trials` random strategies at this rebalance frequency.

    `like`: the candidate's own signal frame. When given, nulls are random rotations of it
    (duty-cycle matched -- see sig_rotated). When None, the historical per-bar random
    signal is used; that path is retained because every verdict in graveyard.csv was
    scored against it and changing it silently would make old and new rows incomparable.

    MEMOIZED per (prices, freq, trials). The internal rng is seeded to 0 and consumed
    sequentially, so the result is a pure function of those three -- recomputing it is
    identical work every time. That mattered: `factory_run.run_cycle()` rebuilds the floor
    per call, and this in-process memoization is only half the fix -- it doesn't help
    across xdist WORKERS (separate processes, separate cache), so `test_factory_run.py`'s
    ~16 tests were still ~83% of the suite's serial runtime on CI's 4 workers. The other
    half: those tests run at a much smaller `trials` (they test promotion/ranking
    plumbing, not statistical precision) -- see `tests/test_factory_run.py`'s
    `scratch_graveyard` fixture.

    Keyed on a CONTENT fingerprint, not object identity, so a caller that mutates its price
    frame gets a fresh floor instead of a silently stale one."""
    like_fp = None if like is None else _prices_fingerprint(like)
    key = (_prices_fingerprint(prices), freq, trials, like_fp)
    hit = _NULL_CACHE.get(key)
    if hit is not None:
        return hit
    if rv is None:
        rv = realized_vol(prices)
    rng = np.random.default_rng(0)
    out = []
    for _ in range(trials):
        sig = sig_random(prices, rng) if like is None else sig_rotated(like, rng)
        r = net_returns(prices, size_and_rebalance(prices, sig, freq, rv))
        v = stats(r[r.index >= OOS_START])["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    arr = np.array(out)
    _NULL_CACHE[key] = arr
    return arr


# ---------- doctrine verdict ----------
def dsr_gate1(r_oos, null, n_tested):
    """DOCTRINE v1.4's gate-1 decision -- shared by harness.evaluate() (bare strategies)
    and piggyback_backtest.py's evaluate() (constructions), so the two verdict paths
    can't silently drift apart the way Bonferroni's decision logic ended up duplicated
    across both files before this. `r_oos` is the candidate's own OOS return series
    (native frequency, e.g. daily); `null` is the matching noise-floor Sharpe sample
    (whatever `stats()`-annualized distribution the caller already has -- a bare
    strategy's per-frequency noise floor, or a piggyback's depth-matched construction
    null); `n_tested` is the multiple-testing family size (`family_n_tested()`).

    Returns a dict: beats_luck (bool), dsr, sr_star (annualized, for display),
    cpcv_n_paths, cpcv_sharpe_mean/std (annualized), skew, kurtosis -- everything a
    caller needs both to decide gate 1 and to log a full graveyard.csv row.

    DOCTRINE v1.8 (#114): beats_luck also requires the candidate's OWN Sharpe be
    positive. DSR alone has no such floor -- it compares the candidate to the expected
    BEST of n_tested draws from the null, so when both are negative and the null is the
    MORE negative of the two, DSR saturates at 1.0 beside a strategy that is losing
    money. Gate 1 must never read as a pass for that."""
    r_oos = pd.Series(r_oos).dropna()
    s = stats(r_oos)
    cpcv_paths = cpcv_oos_sharpes(r_oos)
    sr_native = float(cpcv_paths.mean()) if len(cpcv_paths) else s["Sharpe"] / np.sqrt(ANN)
    null_native = np.asarray(null, dtype=float) / np.sqrt(ANN)
    skew, kurt = _moments(r_oos.values)
    dsr, sr_star_native = deflated_sharpe_ratio(sr_native, null_native, n_tested, len(r_oos), skew, kurt)
    return {
        "beats_luck": bool(dsr > 0.95 and s["Sharpe"] > 0), "dsr": dsr, "sr_star": sr_star_native * np.sqrt(ANN),
        "cpcv_n_paths": len(cpcv_paths),
        "cpcv_sharpe_mean": float(cpcv_paths.mean() * np.sqrt(ANN)) if len(cpcv_paths) else None,
        "cpcv_sharpe_std": float(cpcv_paths.std(ddof=1) * np.sqrt(ANN)) if len(cpcv_paths) > 1 else None,
        "skew": skew, "kurtosis": kurt,
    }


def evaluate(name, r_full, bench_full, null, freq, n_tested=None, bench_label="60/40"):
    """n_tested: size of the multiple-testing family for the Bonferroni correction
    (DOCTRINE v1.3). Defaults to family_n_tested([name]) -- graveyard's count unioned
    with just this one candidate -- for callers evaluating one strategy at a time.

    bench_label: what to print next to the benchmark stats. `bench_full` is not always
    the 60/40 passive benchmark -- e.g. carry studies pass always-on carry -- and the
    print used to say "(60/40)" regardless, reading as a data bug (#122). Cosmetic
    only; the comparison itself was always against whatever `bench_full` is.

    Gate 1 ("beats luck") is decided by the Deflated Sharpe Ratio (DOCTRINE v1.4,
    `dsr_gate1()`), not the Bonferroni bar -- `bonferroni_bar()` is still computed and
    logged to graveyard.csv for continuity/comparison, same as v1.0's flat p95 stayed
    visible after v1.3 stopped deciding with it.

    DOCTRINE v1.7 (#115): both series are sliced at max(OOS_START, the candidate's own
    first non-null observation), not just OOS_START. A candidate whose own data starts
    later than OOS_START (every hourly/crypto family so far) made that slice a no-op for
    r_full while the benchmark still ran from OOS_START -- a longer, different window.
    This only ever narrows b_oos; r_oos is unaffected, since r_full[index >= OOS_START]
    was already a no-op whenever the candidate's true start postdates OOS_START."""
    if n_tested is None:
        n_tested = family_n_tested([name])
    r_dropna = r_full.dropna()
    oos_start = max(OOS_START, r_dropna.index.min()) if len(r_dropna) else OOS_START
    r_oos = r_full[r_full.index >= oos_start]
    b_oos = bench_full[bench_full.index >= oos_start]
    s, b  = stats(r_oos), stats(b_oos)
    both  = pd.concat([r_oos, b_oos], axis=1).dropna()
    corr  = both.iloc[:, 0].corr(both.iloc[:, 1])
    null_bar, bar_method, bar_pctile = bonferroni_bar(null, n_tested)
    v14 = dsr_gate1(r_oos, null, n_tested)

    beats_luck = v14["beats_luck"]
    earns      = (calmar(s) > calmar(b)) or (abs(corr) < CORR_DIV and s["Sharpe"] >= b["Sharpe"])
    dd_ok      = s["MaxDD"] >= DD_MULT * b["MaxDD"]        # both negative
    alive      = bool(beats_luck and earns and dd_ok)

    print(f"\n=== DOCTRINE verdict: {name} (reb {freq}) ===")
    print(f"  strategy  Sharpe {s['Sharpe']:.2f} | Sortino {s['Sortino']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%} | corr->bench {corr:.2f}")
    print(f"  benchmark Sharpe {b['Sharpe']:.2f} | Calmar {calmar(b):.2f} | MaxDD {b['MaxDD']:.1%}   ({bench_label})")
    print(f"  noise floor ({freq}-rebalanced random, n_tested={n_tested}): Bonferroni {bar_method} p{bar_pctile:.2f} = {null_bar:.2f} (logged only)")
    print(f"  DSR (v1.4): {v14['dsr']:.3f} vs SR* {v14['sr_star']:.2f} annualized "
          f"({v14['cpcv_n_paths']} CPCV paths, skew {v14['skew']:.2f}, kurt {v14['kurtosis']:.2f})")
    print(f"  gate 1  beats luck  : {beats_luck}   (DSR {v14['dsr']:.3f} > 0.95)")
    print(f"  gate 2  earns place : {earns}   (Calmar {calmar(s):.2f} vs {calmar(b):.2f}; |corr| {abs(corr):.2f})")
    print(f"  gate 3  not painful : {dd_ok}   (MaxDD {s['MaxDD']:.1%} vs limit {DD_MULT * b['MaxDD']:.1%})")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if alive else 'DEAD -> graveyard, no rescue'}")

    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "strategy": name, "freq": freq, "oos_sharpe": round(s["Sharpe"], 3),
           "oos_sortino": round(s["Sortino"], 3), "oos_calmar": round(calmar(s), 3),
           "oos_maxdd": round(s["MaxDD"], 3), "corr_bench": round(corr, 3),
           "null_p95": round(null_bar, 3), "bench_sharpe": round(b["Sharpe"], 3),
           "bench_calmar": round(calmar(b), 3), "verdict": "ALIVE" if alive else "DEAD",
           "n_tested": n_tested, "bar_method": bar_method, "bar_pctile": round(bar_pctile, 3),
           "dsr": round(v14["dsr"], 4), "dsr_sr_star": round(v14["sr_star"], 3),
           "cpcv_n_paths": v14["cpcv_n_paths"],
           "cpcv_sharpe_mean": round(v14["cpcv_sharpe_mean"], 3) if v14["cpcv_sharpe_mean"] is not None else "",
           "cpcv_sharpe_std": round(v14["cpcv_sharpe_std"], 3) if v14["cpcv_sharpe_std"] is not None else ""}
    pd.DataFrame([row]).to_csv(GRAVEYARD, mode="a", header=not os.path.exists(GRAVEYARD), index=False)
    return s


# ---------- calibration-only prelim firewall (DOCTRINE v1.9, #175) ----------
# For the daily automated research pipeline (#174): a cheap, LENIENT screen a freshly
# proposed idea must clear on CALIBRATION data (2007-2017) alone before it's worth
# spending a real, pre-registered OOS test on. The firewall property this exists for:
# an idea that fails here must be IMPOSSIBLE to distinguish, after the fact, from one that
# was never proposed at all -- it never touches 2018+ data, never costs a
# family_n_tested() draw, and never becomes a graveyard.csv row. Selecting ideas by a look
# at OOS results (even an informal one) is exactly the data-snooping DOCTRINE.md's own
# rule 2 exists to prevent; this is that rule extended to a step upstream of evaluate().
PRELIM_TRIALS = 100      # cheap relative to NULL_TRIALS=500 -- this is a screen, not gate 1
PRELIM_NULL_PCTILE = 50  # the median, deliberately far short of the real p95/DSR bar. This
                          # screen's one job is to not kill a real idea before OOS ever
                          # sees it -- a false PASS here just costs one wasted OOS test
                          # (cheap, recoverable), while a false FAIL discards an edge
                          # permanently with no record it ever existed. A lenient bar
                          # trades a higher false-positive rate for a near-zero
                          # false-negative rate on purpose.
PRELIM_LOG = os.path.join(ART, "prelim_log.csv")


def _calib_slice(df):
    """Truncates a price/signal frame to the calibration window BEFORE any computation
    touches it. The firewall is the missing rows, not a downstream filter that could have
    a bug -- nothing dated after CALIB_END is ever held in memory by a prelim screen for a
    later step to accidentally read. See test_prelim_screen.py's calibration-blindness
    test, which mutates the OOS portion of synthetic data and asserts the verdict doesn't
    move -- the same discipline pairs_backtest.py's fit_pair() test used for #172."""
    return df.loc[(df.index >= CALIB_START) & (df.index <= CALIB_END)]


def _prelim_noise_floor(calib_prices, freq, rv, trials=PRELIM_TRIALS):
    """Sharpe distribution of `trials` random strategies, scored over the FULL frame
    passed in with no OOS_START-relative slicing -- unlike noise_floor() above, which
    unconditionally scores at `r.index >= OOS_START` and so cannot be reused here without
    silently producing an empty (all-NaN-filtered) sample from calibration-only prices.
    Callers MUST pass an already `_calib_slice()`-d frame; this function trusts its input
    rather than re-deriving the window, so the truncation only ever happens in one place."""
    rng = np.random.default_rng(0)
    out = []
    for _ in range(trials):
        sig = sig_random(calib_prices, rng)
        r = net_returns(calib_prices, size_and_rebalance(calib_prices, sig, freq, rv))
        v = stats(r.dropna())["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


def _log_prelim(name, freq, sharpe, bar, passed):
    """artifacts/prelim_log.csv -- a SEPARATE, dedicated ledger for every prelim screen
    ever run, pass or fail. Never graveyard.csv, and never read by family_n_tested(): the
    whole point of this firewall is that a screened idea leaves a paper trail without ever
    entering the multiple-testing record that governs real verdicts."""
    os.makedirs(ART, exist_ok=True)
    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "strategy": name, "freq": freq,
           "calib_sharpe": round(sharpe, 3) if np.isfinite(sharpe) else "",
           "calib_null_p50": round(bar, 3) if np.isfinite(bar) else "",
           "passed": passed}
    pd.DataFrame([row]).to_csv(PRELIM_LOG, mode="a", header=not os.path.exists(PRELIM_LOG), index=False)


def prelim_screen(candidate_spec: dict) -> bool:
    """DOCTRINE v1.9 (#175): the calibration-only prelim firewall. `candidate_spec` is
    {"name": str, "sig_fn": callable (prices -> signal DataFrame), "freq": "D"|"W"|"M"} --
    the same shape factory_run.py's own candidate dicts already use.

    Loads prices, truncates to the calibration window FIRST (`_calib_slice()`), and only
    then builds the signal, the returns, and a calibration-window noise floor -- nothing
    past CALIB_END is ever touched, let alone decided on. Passes if the candidate's own
    calibration Sharpe is positive AND beats the calibration null's median
    (PRELIM_NULL_PCTILE=50, deliberately lenient -- see its own comment above).

    Every call is logged to artifacts/prelim_log.csv regardless of outcome. Returns a
    plain bool -- pipeline stages downstream (#177/#178) branch on this, not on a richer
    object, so a passing idea's next stop is real pre-registration, not a second look at
    these numbers."""
    name, sig_fn, freq = candidate_spec["name"], candidate_spec["sig_fn"], candidate_spec["freq"]

    prices, _ = load_prices()
    calib_prices = _calib_slice(prices)
    rv = realized_vol(calib_prices)
    calib_signal = _calib_slice(sig_fn(calib_prices))

    r = net_returns(calib_prices, size_and_rebalance(calib_prices, calib_signal, freq, rv))
    sharpe = stats(r.dropna())["Sharpe"]

    null = _prelim_noise_floor(calib_prices, freq, rv)
    bar = float(np.percentile(null, PRELIM_NULL_PCTILE)) if len(null) else float("nan")
    passed = bool(np.isfinite(sharpe) and np.isfinite(bar) and sharpe > 0 and sharpe > bar)

    _log_prelim(name, freq, sharpe, bar, passed)
    return passed


def main():
    prices, source = load_prices()
    print(f"data: {source} | {prices.index.min().date()} -> {prices.index.max().date()} | {prices.shape[1]} assets")
    rv    = realized_vol(prices)
    bench = benchmark_returns(prices)

    # DOCTRINE v1.5 (#112): the null is DUTY-CYCLE matched, so it is per-STRATEGY rather
    # than per-frequency. v1.0.1 matched the null's clock; #101 measured that this is not
    # enough -- a per-bar random signal flips at nearly every rebalance while a real trend
    # signal holds, so the null traded 3.7x more monthly and 19.9x more daily and paid a
    # turnover cost the candidate never did. Gate 1 was systematically LENIENT. Rotating
    # the candidate's OWN signal preserves its turnover exactly while destroying any
    # alignment with future returns, which is the hypothesis gate 1 is supposed to test.
    #
    # Cost: one floor per strategy instead of one per frequency. noise_floor() is memoized
    # on a content fingerprint of (prices, freq, trials, like), so a re-run is free, but a
    # cold run does len(STRATEGIES) x NULL_TRIALS instead of len(freqs) x NULL_TRIALS.
    n_tested = family_n_tested(STRATEGIES.keys())
    returns_full, nulls = {}, {}
    for name, (fn, freq) in STRATEGIES.items():
        sig = fn(prices)
        r = net_returns(prices, size_and_rebalance(prices, sig, freq, rv))
        returns_full[name] = r
        print(f"computing duty-cycle-matched noise floor for {name} "
              f"({NULL_TRIALS} rotations, {freq}-rebalanced)...")
        nulls[name] = noise_floor(prices, freq, NULL_TRIALS, rv, like=sig)
        evaluate(name, r, bench, nulls[name], freq, n_tested)

    # ---- artifacts for the dashboard ----
    os.makedirs(ART, exist_ok=True)
    full = pd.DataFrame(returns_full)
    full["bench_6040"] = bench
    full["spy"] = prices["SPY"].pct_change()
    full = full.dropna(how="all")
    full.to_csv(os.path.join(ART, "full_returns.csv"))
    np.savez(os.path.join(ART, "nulls.npz"), **nulls)
    meta = {"source": source,
            "start": str(prices.index.min().date()), "end": str(prices.index.max().date()),
            "n_assets": int(prices.shape[1]), "universe": list(prices.columns),
            "oos_start": str(OOS_START.date()),
            # v1.5: keyed by STRATEGY, not frequency -- each candidate now has its own
            # duty-cycle-matched floor. app.py detects which style a saved npz uses so an
            # older artifact still renders.
            "null_kind": "duty_cycle",
            "null_bars": {k: round(float(np.percentile(v, NULL_PCTILE)), 3) for k, v in nulls.items()},
            "strategy_freq": {k: v[1] for k, v in STRATEGIES.items()},
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(ART, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"\nwrote artifacts/ (full_returns.csv, nulls.npz, meta.json) and appended to graveyard.csv")


if __name__ == "__main__":
    main()
