# curve_carry Primitive (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `curve_carry`, a new research-pipeline primitive: a DV01-neutral TLT/IEF
position whose direction trend-follows the real FRED curve slope — the first primitive in
`PRIMITIVES` gated by external data rather than price action alone, and the first genuinely
new mechanism class (structural carry) since launch.

**Architecture:** One new primitive in `src/tradefabe/pipeline.py` (signal builder + a
calibration-only hedge-effectiveness guard), one new guard-check block in
`research/pipeline_daily.py`'s `screen_pending_backlog()` mirroring `asset_class_trend_hedge`'s
existing block exactly in shape, and one new vocabulary entry in `STRATEGIES.md`. Depends on
`src/tradefabe/rates.py` (Phase 1, branch `rates-yield-curve-infra`, which this branch is
built on top of).

**Tech Stack:** pandas, numpy — no new dependencies. Reuses `rates.load_yield_curve()` /
`rates.align_to_trading_days()` from Phase 1.

## Global Constraints

- **Fixed to TLT/IEF only** — no free ticker choice, unlike every other primitive. Real
  duration data is only pre-registered for this pair.
- **Duration constants, pre-registered, not tuned:** `TLT_DURATION = 16.0`,
  `IEF_DURATION = 7.5` — frozen point estimates from the verified 2026-08 range
  (TLT ~15–16.5yr, IEF ~7–8yr; see the design spec). Never re-derived from data, never
  fetched live.
- **Guard reuses `CALIB_CORR_CAP = 0.3`** (already defined in `pipeline.py` for
  `asset_class_trend_hedge`) — do not invent a new threshold.
- **Single free parameter:** `lookback` ∈ `(20, 252)`, the exact same range
  `single_asset_trend` already uses.
- **Calibration-only firewall**, same discipline as `legs_pass_calibration_corr_cap()`:
  the guard function takes pre-sliced calibration-window data as pure arguments — it must
  never fetch data itself, and the caller is responsible for truncating to
  `harness.CALIB_START`–`harness.CALIB_END` before calling it.
- **No live network calls in any test** — every test injects synthetic prices/curves,
  matching `tests/test_rates.py` and `tests/test_pipeline_daily.py`'s existing patterns.
- **SCOPE BOUNDARY — do not cross it:** this plan builds the primitive machinery and its
  tests ONLY. Do not run `harness.py`, do not produce a `graveyard.csv` verdict, do not
  propose a specific `rp_curve_carry_*` candidate. Per `.claude/skills/new-strategy/SKILL.md`,
  a spec must be frozen and MERGED before any result exists — running an evaluation before
  this PR merges would violate that ordering. That's Dave's call, later.
- **Never commit to `main` directly** — this plan continues on branch `curve-carry-primitive`
  (already created, based on `rates-yield-curve-infra`).
- **Do not push, open a PR, or merge.** Branch/PR/CI-wait/merge/verify/cleanup goes through
  Dave's user-invoked `/ship` or `/new-strategy` skill — this plan's last task ends at "code
  complete, tests green locally, committed," with a handoff note.
- **Before this PR can merge, the `doctrine-auditor` subagent must run** — a CLAUDE.md rule
  added after a prior primitive (#195) merged once without it. This is a reviewer/Dave step
  after shipping, not part of this plan's tasks, but flag it in the final handoff.
- Stage code explicitly (`git add src/ research/ tests/ STRATEGIES.md`), never `git add -A`.

---

## File Structure

- **Modify `src/tradefabe/pipeline.py`** — add `TLT_DURATION`/`IEF_DURATION` constants,
  `_sig_curve_carry()` builder (registered in `_BUILDERS`), `curve_carry` entry in
  `PRIMITIVES`, and `curve_carry_hedge_is_effective()` guard function.
- **Modify `research/pipeline_daily.py`** — add a `curve_carry` guard-check block in
  `screen_pending_backlog()`, mirroring the existing `asset_class_trend_hedge` block.
- **Modify `STRATEGIES.md`** — new vocabulary table row + "Vocabulary expansion" prose
  section, same shape as `asset_class_trend_hedge`'s.
- **Create `tests/test_curve_carry.py`** — signal + guard unit tests.
- **Modify `tests/test_pipeline_daily.py`** — integration tests for the new guard block,
  same shape as the existing `asset_class_trend_hedge` guard tests.

---

## Task 1: `_sig_curve_carry()` — the signal builder

**Files:**
- Modify: `src/tradefabe/pipeline.py`
- Test: `tests/test_curve_carry.py` (new file)

**Interfaces:**
- Produces: `TLT_DURATION: float = 16.0`, `IEF_DURATION: float = 7.5`
- Produces: `_sig_curve_carry(params: dict) -> Callable[[pd.DataFrame], pd.DataFrame]` —
  `params = {"lookback": int}`. Returned `sig(prices)` reads `prices.index` and
  `prices[["TLT", "IEF"]]`'s presence only for column alignment (weights don't depend on
  price levels, only on the date index), fetches yield-curve data internally via
  `rates.load_yield_curve()`, truncates it to `prices.index.max()`, and returns a
  `pd.DataFrame` indexed like `prices` with `TLT`/`IEF` columns DV01-weighted by
  curve-slope-trend direction.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curve_carry.py`:

```python
"""Tests for curve_carry (Phase 2, docs/superpowers/specs/2026-08-04-carry-generalization-
design.md) -- a DV01-neutral TLT/IEF position whose direction trend-follows the real FRED
curve slope. No live network calls anywhere -- every rates.load_yield_curve() call is
mocked, matching tests/test_rates.py's pattern."""
import numpy as np
import pandas as pd
import pytest

import tradefabe.pipeline as pipeline
import tradefabe.rates as rates


def _synthetic_prices(n=400, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.005, n)))
         for t in ["TLT", "IEF", "SPY"]}, index=idx)


def _synthetic_curve(idx, slope_path, seed=1):
    """A yield curve whose DGS10-DGS2 slope follows slope_path exactly, so direction is
    fully controlled rather than left to chance."""
    rng = np.random.default_rng(seed)
    dgs2 = 3.0 + rng.normal(0, 0.001, len(idx)).cumsum() * 0
    dgs10 = dgs2 + pd.Series(slope_path, index=idx)
    return pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)


def test_sig_curve_carry_is_dv01_neutral_by_construction(monkeypatch):
    prices = _synthetic_prices()
    steepening = np.linspace(0.5, 2.0, len(prices))   # monotonically steepening
    curve = _synthetic_curve(prices.index, steepening)
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    nonzero = weights[(weights["TLT"] != 0) | (weights["IEF"] != 0)]
    assert len(nonzero) > 0
    ratios = (nonzero["TLT"].abs() * pipeline.TLT_DURATION) / \
             (nonzero["IEF"].abs() * pipeline.IEF_DURATION)
    assert np.allclose(ratios, 1.0, atol=1e-9)   # DV01s offset exactly, by construction


def test_sig_curve_carry_shorts_tlt_on_a_steepening_trend(monkeypatch):
    prices = _synthetic_prices()
    steepening = np.linspace(0.5, 2.0, len(prices))
    curve = _synthetic_curve(prices.index, steepening)
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    last = weights.iloc[-1]
    assert last["TLT"] < 0   # steepening -> short TLT
    assert last["IEF"] > 0   # steepening -> long IEF


def test_sig_curve_carry_longs_tlt_on_a_flattening_trend(monkeypatch):
    prices = _synthetic_prices()
    flattening = np.linspace(2.0, 0.5, len(prices))
    curve = _synthetic_curve(prices.index, flattening)
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    last = weights.iloc[-1]
    assert last["TLT"] > 0   # flattening -> long TLT
    assert last["IEF"] < 0   # flattening -> short IEF


def test_sig_curve_carry_is_flat_before_enough_lookback_history(monkeypatch):
    prices = _synthetic_prices()
    curve = _synthetic_curve(prices.index, np.linspace(0.5, 2.0, len(prices)))
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)

    assert (weights.iloc[0]["TLT"] == 0.0) and (weights.iloc[0]["IEF"] == 0.0)


def test_sig_curve_carry_never_touches_curve_data_past_the_prices_window(monkeypatch):
    """The calibration-firewall-respecting truncation: sig(prices) must restrict the
    fetched curve to prices.index.max(), even though load_yield_curve() itself returns
    full history -- a caller passing calibration-window-only prices must get a
    calibration-window-only signal."""
    prices = _synthetic_prices(n=200)
    full_idx = pd.bdate_range("2020-01-02", periods=400)   # curve has MORE history than prices
    curve = _synthetic_curve(full_idx, np.linspace(0.5, 3.0, len(full_idx)))
    monkeypatch.setattr(rates, "load_yield_curve", lambda: (curve, "test"))

    sig_fn = pipeline._sig_curve_carry({"lookback": 60})
    weights = sig_fn(prices)   # must not raise, must not silently use future curve rows

    assert list(weights.index) == list(prices.index)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_curve_carry.py -v`
Expected: FAIL — `AttributeError: module 'tradefabe.pipeline' has no attribute '_sig_curve_carry'`

- [ ] **Step 3: Write the implementation**

In `src/tradefabe/pipeline.py`, add near `CALIB_CORR_CAP` (after the existing
`legs_pass_calibration_corr_cap()` function):

```python
# ---------- curve_carry (Phase 2, docs/superpowers/specs/2026-08-04-carry-generalization-
# design.md) -- the first primitive gated by external data, not price action alone.
# Fixed to TLT/IEF only: real duration data is only pre-registered for this pair.
TLT_DURATION = 16.0   # effective duration, years -- frozen point estimate from the
IEF_DURATION = 7.5    # verified 2026-08 range (TLT ~15-16.5yr, IEF ~7-8yr). Reviewed
                       # once, same discipline as ASSET_CLASS -- never fetched live or
                       # re-derived from data.


def _sig_curve_carry(params):
    lookback = params["lookback"]

    def sig(prices):
        curve, _ = rates.load_yield_curve()
        curve = curve.loc[curve.index <= prices.index.max()]
        aligned = rates.align_to_trading_days(curve, prices.index)
        slope = aligned["DGS10"] - aligned["DGS2"]
        direction = np.sign(slope - slope.shift(lookback)).fillna(0.0)
        k_tlt = IEF_DURATION / (TLT_DURATION + IEF_DURATION)
        k_ief = TLT_DURATION / (TLT_DURATION + IEF_DURATION)
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out["TLT"] = -direction * k_tlt
        out["IEF"] = direction * k_ief
        return out
    return sig
```

Add the import at the top of `src/tradefabe/pipeline.py` (alongside the existing
`from .engine import UNIVERSE`):

```python
from . import rates
```

Register in `_BUILDERS` (find the existing dict and add one line):

```python
_BUILDERS = {
    "pair_zscore": _sig_pair_zscore,
    "cross_sectional_rank": _sig_cross_sectional_rank,
    "single_asset_trend": _sig_single_asset_trend,
    "static_spread_carry": _sig_static_spread_carry,
    "asset_class_trend_hedge": _sig_asset_class_trend_hedge,
    "curve_carry": _sig_curve_carry,
}
```

Add to `PRIMITIVES` (find the existing dict, add after `asset_class_trend_hedge`'s entry):

```python
    "curve_carry": {
        "description": ("A DV01-neutral TLT/IEF position whose direction trend-follows "
                        "the real FRED curve slope (DGS10 - DGS2): steepening -> short "
                        "TLT / long IEF, flattening -> long TLT / short IEF, sized so "
                        "the two legs' duration exposure roughly offsets. Fixed to "
                        "TLT/IEF only -- no ticker_a/ticker_b choice like other "
                        "primitives -- since real duration data is only pre-registered "
                        "for this pair. This is checked mechanically after you propose "
                        "(the calibration-window hedge-effectiveness guard), so a "
                        "claimed duration-neutral setup that doesn't actually hold up "
                        "gets rejected regardless of how the citation reads."),
        "params": {"lookback": (20, 252)},
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_curve_carry.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/pipeline.py tests/test_curve_carry.py
git commit -m "pipeline.py: add curve_carry primitive -- DV01-neutral, curve-slope-gated"
```

---

## Task 2: `curve_carry_hedge_is_effective()` — the calibration-only guard

**Files:**
- Modify: `src/tradefabe/pipeline.py`
- Test: `tests/test_curve_carry.py`

**Interfaces:**
- Consumes: `TLT_DURATION`, `IEF_DURATION`, `CALIB_CORR_CAP` from Task 1 / existing code.
- Produces: `curve_carry_hedge_is_effective(params: dict, calib_prices: pd.DataFrame, calib_curve: pd.DataFrame) -> bool`
  — pure function, no fetching, caller must have already truncated both arguments to the
  calibration window.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_curve_carry.py`:

```python
def test_hedge_is_effective_passes_when_position_decorrelates_from_rate_moves():
    idx = pd.bdate_range("2007-01-02", periods=1000)
    rng = np.random.default_rng(5)
    # TLT and IEF move together (duration-driven), so a DV01-neutral position's return
    # should genuinely decorrelate from raw rate-level moves -- the hedge working as
    # designed.
    common = rng.normal(0.0001, 0.006, 1000)
    tlt = 100 * np.exp(np.cumsum(common * 2.0 + rng.normal(0, 0.002, 1000)))
    ief = 100 * np.exp(np.cumsum(common * 1.0 + rng.normal(0, 0.001, 1000)))
    calib_prices = pd.DataFrame({"TLT": tlt, "IEF": ief}, index=idx)
    dgs2 = 3.0 + rng.normal(0, 0.01, 1000).cumsum() * 0.01
    dgs10 = dgs2 + np.linspace(0.5, 2.5, 1000) + rng.normal(0, 0.02, 1000)
    calib_curve = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)

    assert pipeline.curve_carry_hedge_is_effective(
        {"lookback": 60}, calib_prices, calib_curve) is True


def test_hedge_is_effective_fails_for_a_naked_unhedged_duration_bet():
    """A regression guard: if the DV01 weighting were ever dropped (e.g. a future edit
    sets IEF's weight to 0, leaving a naked long/short TLT bet), the position's return
    should correlate STRONGLY with rate-level moves, and the guard must catch that."""
    idx = pd.bdate_range("2007-01-02", periods=1000)
    rng = np.random.default_rng(9)
    dgs2 = 3.0 + rng.normal(0, 0.001, 1000).cumsum() * 0
    dgs10 = dgs2 + np.linspace(0.5, 2.5, 1000)
    calib_curve = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)
    # TLT return driven almost entirely by the same rate move the position bets on;
    # IEF held flat, so nothing hedges the level exposure -- this must fail the guard.
    rate_move = pd.Series(dgs10).diff().fillna(0.0).to_numpy()
    tlt = 100 * np.exp(np.cumsum(-rate_move * 15 + rng.normal(0, 0.0005, 1000)))
    ief = np.full(1000, 100.0)
    calib_prices = pd.DataFrame({"TLT": tlt, "IEF": ief}, index=idx)

    assert pipeline.curve_carry_hedge_is_effective(
        {"lookback": 60}, calib_prices, calib_curve) is False


def test_hedge_is_effective_returns_false_on_too_little_overlapping_data():
    idx = pd.bdate_range("2007-01-02", periods=10)
    calib_prices = pd.DataFrame({"TLT": [100.0] * 10, "IEF": [100.0] * 10}, index=idx)
    calib_curve = pd.DataFrame({"DGS2": [3.0] * 10, "DGS10": [3.5] * 10}, index=idx)
    assert pipeline.curve_carry_hedge_is_effective(
        {"lookback": 60}, calib_prices, calib_curve) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_curve_carry.py -v`
Expected: FAIL — `AttributeError: module 'tradefabe.pipeline' has no attribute 'curve_carry_hedge_is_effective'`

- [ ] **Step 3: Write the implementation**

Add to `src/tradefabe/pipeline.py`, directly after `_sig_curve_carry`:

```python
def curve_carry_hedge_is_effective(params: dict, calib_prices, calib_curve) -> bool:
    """True iff curve_carry's own daily returns, computed on calib_prices/calib_curve
    ALONE, decorrelate below CALIB_CORR_CAP from DGS10's own daily change -- confirms the
    DV01 hedge actually cancelled level risk in calibration data, not just on paper.
    Caller's responsibility to have already truncated BOTH arguments to the calibration
    window (harness.CALIB_START/CALIB_END) before this ever runs -- same firewall
    discipline as legs_pass_calibration_corr_cap(), and for the same reason this
    reimplements the signal math directly rather than calling _sig_curve_carry(): that
    closure fetches live data internally, which a calibration-only guard must never do."""
    lookback = params["lookback"]
    aligned = rates.align_to_trading_days(calib_curve, calib_prices.index)
    slope = aligned["DGS10"] - aligned["DGS2"]
    direction = np.sign(slope - slope.shift(lookback)).fillna(0.0)
    k_tlt = IEF_DURATION / (TLT_DURATION + IEF_DURATION)
    k_ief = TLT_DURATION / (TLT_DURATION + IEF_DURATION)
    tlt_w = (-direction * k_tlt).shift(1)   # shift(1): no lookahead, same convention
    ief_w = (direction * k_ief).shift(1)    # engine.py's w_exec already applies elsewhere
    rets = calib_prices[["TLT", "IEF"]].pct_change()
    position_rets = tlt_w * rets["TLT"] + ief_w * rets["IEF"]
    rate_move = aligned["DGS10"].diff()
    both = pd.concat([position_rets.rename("pos"), rate_move.rename("rate")],
                     axis=1).dropna()
    if len(both) < 30:
        return False
    corr = both["pos"].corr(both["rate"])
    return bool(np.isfinite(corr) and abs(corr) <= CALIB_CORR_CAP)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_curve_carry.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/pipeline.py tests/test_curve_carry.py
git commit -m "pipeline.py: curve_carry_hedge_is_effective(), the calibration-only guard"
```

---

## Task 3: Wire the guard into `pipeline_daily.py`'s `screen_pending_backlog()`

**Files:**
- Modify: `research/pipeline_daily.py`
- Test: `tests/test_pipeline_daily.py`

**Interfaces:**
- Consumes: `pipeline.curve_carry_hedge_is_effective()` from Task 2.
- Produces: no new public names — extends `screen_pending_backlog()`'s existing behavior.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline_daily.py`, after the existing `# ---- compositional-leg guards
(#194)` section (reuse the `_calib_prices` helper already defined there):

```python
# ---------------------------------------------------------------- curve_carry guard (Phase 2)
def _calib_curve(seed, n=2000):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(harness.CALIB_START, periods=n)
    dgs2 = 3.0 + rng.normal(0, 0.001, n).cumsum() * 0
    dgs10 = dgs2 + np.linspace(0.5, 2.5, n)
    return pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)


def test_screen_pending_backlog_rejects_an_ineffective_curve_carry_hedge(scratch, monkeypatch):
    idx = pd.bdate_range(harness.CALIB_START, periods=1000)
    rng = np.random.default_rng(9)
    dgs2 = 3.0 + rng.normal(0, 0.001, 1000).cumsum() * 0
    dgs10 = dgs2 + np.linspace(0.5, 2.5, 1000)
    calib_curve = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)
    rate_move = pd.Series(dgs10).diff().fillna(0.0).to_numpy()
    tlt = 100 * np.exp(np.cumsum(-rate_move * 15 + rng.normal(0, 0.0005, 1000)))
    ief = np.full(1000, 100.0)
    calib_prices = pd.DataFrame({"TLT": tlt, "IEF": ief}, index=idx)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))
    monkeypatch.setattr(pkg_rates, "load_yield_curve", lambda: (calib_curve, "test"))

    _write_ledger_row("rp_curve_carry_60", primitive="curve_carry", params={"lookback": 60})

    def fake_preregister(spec):
        raise AssertionError("a guard-rejected candidate must never reach pre-registration")

    results = pd_.screen_pending_backlog(preregister_fn=fake_preregister)
    assert results == [{"name": "rp_curve_carry_60", "passed": False, "preregistered": False}]


def test_a_curve_carry_guard_rejection_does_not_resurface_on_the_next_cycle(scratch, monkeypatch):
    idx = pd.bdate_range(harness.CALIB_START, periods=1000)
    rng = np.random.default_rng(9)
    dgs2 = 3.0 + rng.normal(0, 0.001, 1000).cumsum() * 0
    dgs10 = dgs2 + np.linspace(0.5, 2.5, 1000)
    calib_curve = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10}, index=idx)
    rate_move = pd.Series(dgs10).diff().fillna(0.0).to_numpy()
    tlt = 100 * np.exp(np.cumsum(-rate_move * 15 + rng.normal(0, 0.0005, 1000)))
    ief = np.full(1000, 100.0)
    calib_prices = pd.DataFrame({"TLT": tlt, "IEF": ief}, index=idx)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))
    monkeypatch.setattr(pkg_rates, "load_yield_curve", lambda: (calib_curve, "test"))

    _write_ledger_row("rp_curve_carry_60", primitive="curve_carry", params={"lookback": 60})
    pd_.screen_pending_backlog(preregister_fn=lambda spec: True)
    assert pd_.pending_screens() == []


def test_screen_pending_backlog_still_screens_a_valid_curve_carry_candidate(scratch, monkeypatch):
    calib_prices = _calib_prices(3, ["TLT", "IEF"])
    calib_curve = _calib_curve(3)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))
    monkeypatch.setattr(pkg_rates, "load_yield_curve", lambda: (calib_curve, "test"))

    _write_ledger_row("rp_curve_carry_60", primitive="curve_carry", params={"lookback": 60})

    results = pd_.screen_pending_backlog(screen_fn=lambda c: True,
                                         preregister_fn=lambda spec: True)
    assert results == [{"name": "rp_curve_carry_60", "passed": True, "preregistered": True}]
```

Add the new import at the top of `tests/test_pipeline_daily.py` (alongside the existing
`import pipeline_daily as pd_`):

```python
from tradefabe import rates as pkg_rates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline_daily.py -v -k curve_carry`
Expected: FAIL — `curve_carry` isn't special-cased yet, so these candidates fall through
to the real `prelim_screen()` (which will error or behave unexpectedly against synthetic
calibration-only data) instead of being guard-checked first.

- [ ] **Step 3: Wire the guard**

In `research/pipeline_daily.py`, add the import (alongside the existing
`from tradefabe import pipeline as pkg_pipeline`):

```python
from tradefabe import rates as pkg_rates
```

In `screen_pending_backlog()`, after the existing `if spec["primitive"] ==
"asset_class_trend_hedge":` block (which ends with its own `continue`), add:

```python
        if spec["primitive"] == "curve_carry":
            if calib_prices is None:
                prices, _ = harness.load_prices()
                calib_prices = prices.loc[(prices.index >= harness.CALIB_START) &
                                          (prices.index <= harness.CALIB_END)]
            curve, _ = pkg_rates.load_yield_curve()
            calib_curve = curve.loc[(curve.index >= harness.CALIB_START) &
                                    (curve.index <= harness.CALIB_END)]
            if not pkg_pipeline.curve_carry_hedge_is_effective(
                    spec["params"], calib_prices, calib_curve):
                print(f"[pipeline_daily] {name} (backlog) FAILED the curve_carry "
                      f"hedge-effectiveness guard -- skipping prelim screen")
                harness._log_prelim(name, spec["freq"], float("nan"), float("nan"), False)
                results.append({"name": name, "passed": False, "preregistered": False})
                continue
```

This reuses the same lazily-loaded `calib_prices` local the `asset_class_trend_hedge`
block already established earlier in the loop — do not re-declare it.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline_daily.py -v -k curve_carry`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full pipeline_daily test file**

Run: `.venv/bin/pytest tests/test_pipeline_daily.py -v`
Expected: all pass (no regression on the existing `asset_class_trend_hedge` guard tests).

- [ ] **Step 6: Commit**

```bash
git add research/pipeline_daily.py tests/test_pipeline_daily.py
git commit -m "pipeline_daily.py: wire curve_carry's hedge-effectiveness guard into screening"
```

---

## Task 4: `STRATEGIES.md` — vocabulary documentation

**Files:**
- Modify: `STRATEGIES.md`

**Interfaces:**
- Consumes: nothing code-level — this task is documentation only, matching the existing
  `asset_class_trend_hedge` vocabulary-expansion entry's shape and level of detail.

- [ ] **Step 1: Add the vocabulary table row**

In `STRATEGIES.md`, find the "Research pipeline — primitive vocabulary" table (the row
for `asset_class_trend_hedge` is the last one). Add a new row immediately after it:

```markdown
| `curve_carry` | A DV01-neutral TLT/IEF position whose direction trend-follows the real FRED curve slope (`DGS10 - DGS2`): steepening → short TLT / long IEF, flattening → long TLT / short IEF, sized so the two legs' duration exposure roughly offsets. Fixed to TLT/IEF only — no `ticker_a`/`ticker_b` choice like other primitives, since real duration data is only pre-registered for this pair | `lookback` 20–252 |
```

- [ ] **Step 2: Add the "Vocabulary expansion" prose section**

Immediately after the existing `asset_class_trend_hedge` vocabulary-expansion paragraph
(ends with "...necessary because the scheduled research routine... so the offline check
alone can't be relied on for a routine-written proposal."), add:

```markdown
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
```

- [ ] **Step 3: Add the module reference**

Find the closing sentence of the "Research pipeline" section (`research/pipeline_ideas.py,
research/pipeline_daily.py, ...` file list). Add `tests/test_curve_carry.py` to that list.

- [ ] **Step 4: Verify the CLAUDE.md byte-budget test still passes**

Run: `.venv/bin/pytest tests/test_claude_md_budget.py -v`
Expected: PASS — this test only checks `CLAUDE.md`, which this task doesn't touch, but
confirm nothing else regressed.

- [ ] **Step 5: Commit**

```bash
git add STRATEGIES.md
git commit -m "STRATEGIES.md: document curve_carry -- mechanism, duration constants, guard"
```

---

## Task 5: Full-suite verification

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all tests pass, including `tests/test_curve_carry.py` (8 tests) and the 3 new
`tests/test_pipeline_daily.py` curve_carry tests, on top of whatever baseline this branch
started from (Phase 1's `rates-yield-curve-infra` branch, already verified green).

- [ ] **Step 2: Confirm no evaluation was accidentally run**

Run: `git status --porcelain` and confirm `graveyard.csv`, `pipeline_ideas.csv`,
`artifacts/prelim_log.csv` show no changes — this plan must not have produced a verdict
or a proposal. If any of these changed, STOP and investigate before committing further;
that would violate the spec's scope boundary and `/new-strategy`'s commit-ordering rule.

- [ ] **Step 3: Hand off — do not push, PR, or merge**

Phase 2 is code-complete and tested on the local `curve-carry-primitive` branch (based on
`rates-yield-curve-infra`). Report status and stop here. Remind Dave of two things this
plan deliberately didn't do: (1) `/ship` or `/new-strategy` for branch/PR/merge is his to
run, and this branch depends on Phase 1 merging first; (2) the `doctrine-auditor` subagent
must run before this PR merges, since it touches `STRATEGIES.md`.

---

## Self-Review Notes (completed during planning)

- **Spec coverage:** mechanism (Task 1), guard (Task 2), pipeline_daily wiring (Task 3),
  STRATEGIES.md documentation (Task 4) — every resolved design decision in the spec maps
  to a task. The spec's explicit scope boundary (no evaluation, no proposal) is enforced
  in Task 5's verification step, not just asserted in prose.
- **Placeholder scan:** clean — every step has real, runnable code; the duration constants
  are concrete numbers (16.0, 7.5), not TBD.
- **Type consistency:** `_sig_curve_carry(params) -> Callable[[pd.DataFrame], pd.DataFrame]`
  matches every other `_BUILDERS` entry's shape. `curve_carry_hedge_is_effective(params,
  calib_prices, calib_curve) -> bool` matches `legs_pass_calibration_corr_cap()`'s shape
  (params dict + pre-sliced data in, bool out) even though its specific arguments differ.
  Consistent across Tasks 1–3 and the integration tests.
