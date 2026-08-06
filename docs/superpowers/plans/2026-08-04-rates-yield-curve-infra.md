# Yield-Curve Data Infrastructure (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `src/tradefabe/rates.py`, a module that fetches free daily Treasury yield-curve
data from FRED and safely aligns it to trading days, so a future primitive (Phase 2,
`curve_carry`, planned separately) can be gated by real rate data instead of price action.

**Architecture:** One new module mirrors `engine.py`'s existing cache → live-fetch → stale-cache
→ synthetic fallback chain exactly (same `_cache_is_fresh` helper, same `CACHE_MAX_AGE_HOURS`
env var), so this doesn't introduce a second caching policy to learn. A separate,
independently-tested function (`align_to_trading_days`) handles the FRED-calendar-to-trading-day
join via `pd.merge_asof(..., direction="backward")`, because a naive `reindex().ffill()` join
was flagged during design review as a real look-ahead-leak risk (see
`docs/superpowers/specs/2026-08-04-carry-generalization-design.md`).

**Tech Stack:** pandas, `requests` (already a core dependency — no new dependency to add).
FRED's key-less CSV endpoint (`fred.stlouisfed.org/graph/fredgraph.csv`) — confirmed live
2026-08-04: `observation_date,DGS2,DGS10,...` columns, ISO dates, non-trading days absent as
rows entirely, a trading day with no observation is an EMPTY CSV field (parses to NaN via
plain `pd.read_csv`, no special coercion needed — this is NOT the older `"."`-marker FRED
convention, which belongs to a different, key-gated API).

## Global Constraints

- Spec scope boundary: Phase 1 (this plan) is data infrastructure ONLY. The `curve_carry`
  primitive (Phase 2) is a separate, not-yet-started plan — do not add it here.
- `DGS2`/`DGS10`/`DGS30` are Treasury's actual daily quoted par yields, not revised economic
  estimates — no vintage/revision-leak risk to guard against.
- No live network calls in any test — every test injects canned data via a mocked
  `requests.get`, matching the existing `tests/test_nan_marks.py` pattern.
- Never commit to `main` directly — branch first (`git checkout -b rates-yield-curve-infra`).
- **Do not push, open a PR, or merge.** CLAUDE.md requires branch/PR/CI-wait/merge/verify/
  cleanup to go through the user-invoked `/ship` skill, not be hand-run by an agent. This
  plan's last task ends at "code complete, tests green locally, committed to the local
  branch" — handing off to Dave to run `/ship` is the actual final step, done outside this
  plan.
- Stage code explicitly when committing (`git add src/ tests/`), never `git add -A` — CLAUDE.md
  flags `state/paper/` as Action-owned; nothing in this plan touches it, but the habit matters.

---

## File Structure

- **Create `src/tradefabe/rates.py`** — `load_yield_curve()`, `align_to_trading_days()`,
  `_synthetic_curve()` (private, mirrors `engine._synthetic_prices()`'s shape). Constants:
  `RATES_SERIES`, `RATES_CACHE`, `FRED_URL`.
- **Create `tests/test_rates.py`** — full coverage via injected fixtures, no network.
- **No other file changes.** `engine.py` is read from (imports `START`, `_cache_is_fresh`,
  `CACHE_MAX_AGE_HOURS`), never modified — this plan adds a sibling module, not a change to
  the existing source of truth.

---

## Task 1: Cache-hit path — `load_yield_curve()` returns fresh cache without any network call

**Files:**
- Create: `src/tradefabe/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Produces: `RATES_SERIES: tuple[str, ...]` = `("DGS2", "DGS10", "DGS30")`
- Produces: `RATES_CACHE: str` — path constant, `os.path.join(BASE, "data", "yield_curve.csv")`
- Produces: `load_yield_curve(series=RATES_SERIES, start=engine.START) -> tuple[pd.DataFrame, str]`
  — same `(data, source_label)` contract shape as `engine.load_prices()`.

- [ ] **Step 1: Create the branch**

```bash
cd ~/tradefabe
git checkout main && git pull -q
git checkout -b rates-yield-curve-infra
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_rates.py`:

```python
"""Tests for rates.py -- the yield-curve data infrastructure for generalizing structural
carry beyond crypto (docs/superpowers/specs/2026-08-04-carry-generalization-design.md).
No live network calls anywhere in this file -- every FRED fetch is mocked, matching
tests/test_nan_marks.py's injected-fixture pattern."""
import os
import time

import pandas as pd
import pytest

import tradefabe.rates as rates


@pytest.fixture
def scratch_cache(monkeypatch, tmp_path):
    """Redirect RATES_CACHE to a scratch path so no test touches the real cache file."""
    path = str(tmp_path / "yield_curve.csv")
    monkeypatch.setattr(rates, "RATES_CACHE", path)
    return path


def test_load_yield_curve_returns_fresh_cache_without_network_call(scratch_cache, monkeypatch):
    df = pd.DataFrame({"DGS2": [4.1, 4.2], "DGS10": [4.5, 4.6]},
                       index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    df.to_csv(scratch_cache)

    def _fail_if_called(*a, **k):
        raise AssertionError("requests.get must not be called when the cache is fresh")
    monkeypatch.setattr(rates, "requests", type("R", (), {"get": staticmethod(_fail_if_called)}))

    result, source = rates.load_yield_curve()
    assert source == "cache"
    assert list(result.columns) == ["DGS2", "DGS10"]
    assert len(result) == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradefabe.rates'`

- [ ] **Step 4: Write minimal implementation**

Create `src/tradefabe/rates.py`:

```python
"""
rates.py -- yield-curve data infrastructure for generalizing structural carry beyond
crypto (Phase 1 of docs/superpowers/specs/2026-08-04-carry-generalization-design.md).

Same source-of-truth discipline as engine.py: this is the ONLY place that fetches or
caches yield-curve data. Mirrors engine.load_prices()'s cache -> fetch -> stale-cache ->
synthetic fallback chain and CACHE_MAX_AGE_HOURS discipline exactly, so operators don't
learn a second caching policy.

FRED's key-less CSV endpoint (fred.stlouisfed.org/graph/fredgraph.csv) needs no signup,
no API key -- confirmed live 2026-08-04: `observation_date,DGS2,DGS10,...` columns, ISO
dates, non-trading days (weekends/holidays) absent as rows entirely, and a trading day
with no observation is an EMPTY CSV field (not FRED's older "." marker -- that belongs to
a different, key-gated FRED API). pandas parses an empty field as NaN with no special
coercion needed.

DGS2/DGS10/DGS30 are Treasury's actual daily quoted par yields, not revised/modeled
economic estimates (unlike GDP or employment series) -- no vintage/revision-leak risk.
"""
from __future__ import annotations
import os
import sys
from io import StringIO

import pandas as pd
import requests

from .paths import REPO_ROOT
from .engine import START, _cache_is_fresh

RATES_SERIES = ("DGS2", "DGS10", "DGS30")
BASE = str(REPO_ROOT)
RATES_CACHE = os.path.join(BASE, "data", "yield_curve.csv")
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def load_yield_curve(series=RATES_SERIES, start=START):
    """fresh cache -> FRED -> stale cache -> synthetic. Returns (curve, source_label),
    same contract shape as engine.load_prices()."""
    os.makedirs(os.path.dirname(RATES_CACHE), exist_ok=True)
    cached = None
    if os.path.exists(RATES_CACHE):
        cached = pd.read_csv(RATES_CACHE, index_col=0, parse_dates=True)
        if _cache_is_fresh(RATES_CACHE):
            return cached, "cache"
    raise NotImplementedError("fetch path added in Task 2")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/rates.py tests/test_rates.py
git commit -m "rates.py: cache-hit path for load_yield_curve()"
```

---

## Task 2: FRED fetch path — cache miss pulls live data and writes the cache

**Files:**
- Modify: `src/tradefabe/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: `RATES_CACHE`, `RATES_SERIES`, `FRED_URL` from Task 1.
- Produces: `load_yield_curve()`'s fetch branch — no new public names.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rates.py`:

```python
class _FakeResponse:
    def __init__(self, text):
        self.text = text
    def raise_for_status(self):
        pass


def test_load_yield_curve_fetches_from_fred_on_cache_miss(scratch_cache, monkeypatch):
    csv_text = (
        "observation_date,DGS2,DGS10,DGS30\n"
        "2024-01-02,4.33,3.95,4.10\n"
        "2024-01-03,4.35,3.99,4.15\n"
    )
    calls = []

    def _fake_get(url, params=None, timeout=None):
        calls.append((url, params, timeout))
        return _FakeResponse(csv_text)

    monkeypatch.setattr(rates.requests, "get", _fake_get)

    result, source = rates.load_yield_curve(start="2024-01-01")

    assert source == "FRED"
    assert calls[0][0] == rates.FRED_URL
    assert calls[0][1] == {"id": "DGS2,DGS10,DGS30"}
    assert list(result.columns) == ["DGS2", "DGS10", "DGS30"]
    assert result.loc[pd.Timestamp("2024-01-02"), "DGS10"] == 3.95
    assert os.path.exists(scratch_cache)   # cache was written


def test_load_yield_curve_drops_rows_before_start(scratch_cache, monkeypatch):
    csv_text = (
        "observation_date,DGS10\n"
        "2023-12-29,3.88\n"
        "2024-01-02,3.95\n"
    )
    monkeypatch.setattr(rates.requests, "get",
                         lambda url, params=None, timeout=None: _FakeResponse(csv_text))
    result, _ = rates.load_yield_curve(series=("DGS10",), start="2024-01-01")
    assert pd.Timestamp("2023-12-29") not in result.index
    assert pd.Timestamp("2024-01-02") in result.index


def test_empty_fred_field_parses_as_nan(scratch_cache, monkeypatch):
    csv_text = (
        "observation_date,DGS10\n"
        "2024-01-02,3.95\n"
        "2024-01-03,\n"          # empty field, e.g. a no-quote trading day
    )
    monkeypatch.setattr(rates.requests, "get",
                         lambda url, params=None, timeout=None: _FakeResponse(csv_text))
    result, _ = rates.load_yield_curve(series=("DGS10",), start="2024-01-01")
    assert pd.isna(result.loc[pd.Timestamp("2024-01-03"), "DGS10"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: FAIL — the new tests hit `NotImplementedError("fetch path added in Task 2")`.

- [ ] **Step 3: Implement the fetch path**

Replace the `raise NotImplementedError(...)` line in `load_yield_curve()` with:

```python
    try:
        resp = requests.get(FRED_URL, params={"id": ",".join(series)}, timeout=10)
        resp.raise_for_status()
        raw = pd.read_csv(StringIO(resp.text), parse_dates=["observation_date"])
        raw = raw.set_index("observation_date").sort_index()
        raw.index.name = None
        raw = raw.loc[raw.index >= pd.Timestamp(start)]
        raw = raw[[c for c in series if c in raw.columns]]
        if raw.empty:
            raise RuntimeError("FRED returned no rows for the requested series/range")
        raw.to_csv(RATES_CACHE)
        return raw, "FRED"
    except Exception as e:
        if cached is not None:
            print(f"[warn] live yield-curve data unavailable ({e}); "
                  f"falling back to STALE cache.", file=sys.stderr)
            return cached, "cache (stale)"
        print(f"[warn] live yield-curve data unavailable ({e}); "
              f"generating SYNTHETIC data.", file=sys.stderr)
        return _synthetic_curve(series, start), "SYNTHETIC (do not trust the numbers)"
```

Add the `_synthetic_curve` stub above `load_yield_curve` (real implementation in Task 3):

```python
def _synthetic_curve(series, start):
    raise NotImplementedError("synthetic fallback added in Task 3")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/rates.py tests/test_rates.py
git commit -m "rates.py: live FRED fetch path, cache write, start-date filtering"
```

---

## Task 3: Stale-cache and synthetic fallback paths

**Files:**
- Modify: `src/tradefabe/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: everything from Tasks 1-2.
- Produces: `_synthetic_curve(series, start) -> pd.DataFrame` (private, mirrors
  `engine._synthetic_prices()`'s role — used only as a last-resort fallback).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rates.py`:

```python
def test_load_yield_curve_falls_back_to_stale_cache_on_fetch_failure(scratch_cache, monkeypatch):
    stale = pd.DataFrame({"DGS10": [3.90]}, index=pd.to_datetime(["2024-01-02"]))
    stale.to_csv(scratch_cache)
    # make the cache look stale without waiting: set CACHE_MAX_AGE_HOURS-independent mtime
    old = time.time() - 3600 * 999
    os.utime(scratch_cache, (old, old))

    def _raise(*a, **k):
        raise RuntimeError("simulated network failure")
    monkeypatch.setattr(rates.requests, "get", _raise)

    result, source = rates.load_yield_curve()
    assert source == "cache (stale)"
    assert result.loc[pd.Timestamp("2024-01-02"), "DGS10"] == 3.90


def test_load_yield_curve_falls_back_to_synthetic_with_no_cache(scratch_cache, monkeypatch):
    assert not os.path.exists(scratch_cache)   # nothing cached yet

    def _raise(*a, **k):
        raise RuntimeError("simulated network failure")
    monkeypatch.setattr(rates.requests, "get", _raise)

    result, source = rates.load_yield_curve(start="2020-01-01")
    assert "SYNTHETIC" in source
    assert not result.empty
    assert list(result.columns) == list(rates.RATES_SERIES)


def test_synthetic_curve_is_deterministic():
    a = rates._synthetic_curve(rates.RATES_SERIES, "2020-01-01")
    b = rates._synthetic_curve(rates.RATES_SERIES, "2020-01-01")
    pd.testing.assert_frame_equal(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: FAIL — `_synthetic_curve` still raises `NotImplementedError`.

- [ ] **Step 3: Implement `_synthetic_curve`**

Replace the `_synthetic_curve` stub:

```python
def _synthetic_curve(series, start):
    """Deterministic synthetic yields so the machinery can be smoke-tested with no
    network -- same role as engine._synthetic_prices(), same fixed seed for
    reproducibility across calls."""
    import numpy as np
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(start, periods=252 * 5)
    base = rng.uniform(2.0, 5.0, len(series))
    data = {}
    for level, name in zip(base, series):
        walk = level + np.cumsum(rng.normal(0, 0.01, len(idx)))
        data[name] = np.clip(walk, 0.01, 8.0)
    return pd.DataFrame(data, index=idx)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/rates.py tests/test_rates.py
git commit -m "rates.py: stale-cache and synthetic fallback paths"
```

---

## Task 4: `align_to_trading_days()` — the no-lookahead-safe join

This is the highest-risk function in this plan: a bank-holiday-aware, look-ahead-safe join
between FRED's calendar and the engine's trading-day price index, flagged during design
review as the one place a subtle bug would silently defeat `engine.py`'s existing
`w_exec = w.shift(1)` no-lookahead guarantee further downstream.

**Files:**
- Modify: `src/tradefabe/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure function, no cache/network involvement).
- Produces: `align_to_trading_days(curve: pd.DataFrame, trading_index) -> pd.DataFrame` —
  reindexes `curve` onto `trading_index`, using the most recent FRED observation AT OR
  BEFORE each trading day, never a later one.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rates.py`:

```python
def test_align_to_trading_days_never_uses_a_future_observation():
    """The core no-lookahead guarantee. The curve has observations on day 1 and day 5
    only (day 5 is a LATER, future value relative to day 3). A trading day on day 3 must
    get day 1's value, never day 5's -- a naive reindex().ffill() anchored wrong, or a
    forward-direction merge_asof, would leak day 5's value backward."""
    curve = pd.DataFrame(
        {"DGS10": [4.00, 4.50]},
        index=pd.to_datetime(["2024-01-01", "2024-01-05"]),
    )
    trading_days = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-05"])

    aligned = rates.align_to_trading_days(curve, trading_days)

    assert aligned.loc[pd.Timestamp("2024-01-03"), "DGS10"] == 4.00   # day 1's value, not day 5's
    assert aligned.loc[pd.Timestamp("2024-01-05"), "DGS10"] == 4.50


def test_align_to_trading_days_handles_a_trading_day_before_any_observation():
    curve = pd.DataFrame({"DGS10": [4.00]}, index=pd.to_datetime(["2024-01-05"]))
    trading_days = pd.to_datetime(["2024-01-02", "2024-01-05"])

    aligned = rates.align_to_trading_days(curve, trading_days)

    assert pd.isna(aligned.loc[pd.Timestamp("2024-01-02"), "DGS10"])
    assert aligned.loc[pd.Timestamp("2024-01-05"), "DGS10"] == 4.00


def test_align_to_trading_days_bridges_a_bank_holiday_gap():
    """FRED's calendar has no concept of a trading day -- a bank holiday that isn't a
    trading day must not shift anything. Curve has data on the Friday before and the
    Tuesday after a Monday bank holiday; the trading index skips the holiday entirely
    (as real trading calendars do)."""
    curve = pd.DataFrame(
        {"DGS10": [4.10, 4.20]},
        index=pd.to_datetime(["2024-01-12", "2024-01-16"]),   # Fri, Tue (Mon = holiday)
    )
    trading_days = pd.to_datetime(["2024-01-12", "2024-01-16"])   # holiday not a trading day

    aligned = rates.align_to_trading_days(curve, trading_days)

    assert aligned.loc[pd.Timestamp("2024-01-12"), "DGS10"] == 4.10
    assert aligned.loc[pd.Timestamp("2024-01-16"), "DGS10"] == 4.20


def test_align_to_trading_days_preserves_all_trading_days():
    curve = pd.DataFrame({"DGS10": [4.00]}, index=pd.to_datetime(["2024-01-01"]))
    trading_days = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    aligned = rates.align_to_trading_days(curve, trading_days)
    assert len(aligned) == 3
    assert list(aligned.index) == list(trading_days)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: FAIL — `AttributeError: module 'tradefabe.rates' has no attribute 'align_to_trading_days'`

- [ ] **Step 3: Implement `align_to_trading_days`**

Add to `src/tradefabe/rates.py`:

```python
def align_to_trading_days(curve, trading_index):
    """No-lookahead-safe join: each trading day gets the most recent FRED observation AT
    OR BEFORE it, never a future one. pd.merge_asof(direction="backward") enforces this
    by construction -- unlike reindex().ffill(), it cannot match a date after the trading
    day regardless of how the two indices are anchored relative to each other."""
    curve_sorted = curve.sort_index()
    left = pd.DataFrame({"date": pd.DatetimeIndex(trading_index).sort_values()})
    right = curve_sorted.reset_index().rename(columns={curve_sorted.index.name or "index": "date"})
    merged = pd.merge_asof(left, right, on="date", direction="backward")
    return merged.set_index("date")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/rates.py tests/test_rates.py
git commit -m "rates.py: align_to_trading_days(), the no-lookahead-safe FRED join"
```

---

## Task 5: End-to-end integration test and full-suite verification

**Files:**
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: `load_yield_curve()` (Tasks 1-3) and `align_to_trading_days()` (Task 4) together.
- Produces: nothing new — this task only adds a test proving the two functions compose
  correctly, and closes the plan with a full-suite run.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rates.py`:

```python
def test_load_and_align_compose_end_to_end(scratch_cache, monkeypatch):
    """The two halves of this module used together, the way a future primitive
    (Phase 2, curve_carry) actually will: fetch, then align to a trading calendar that
    doesn't match FRED's own calendar."""
    csv_text = (
        "observation_date,DGS10\n"
        "2024-01-02,3.95\n"
        "2024-01-03,3.97\n"
        "2024-01-05,4.01\n"      # 2024-01-04 (a trading day) has no FRED observation
    )
    monkeypatch.setattr(rates.requests, "get",
                         lambda url, params=None, timeout=None: _FakeResponse(csv_text))

    curve, source = rates.load_yield_curve(series=("DGS10",), start="2024-01-01")
    assert source == "FRED"

    trading_days = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    aligned = rates.align_to_trading_days(curve, trading_days)

    assert aligned.loc[pd.Timestamp("2024-01-04"), "DGS10"] == 3.97   # carried from 01-03
    assert aligned.loc[pd.Timestamp("2024-01-05"), "DGS10"] == 4.01   # real observation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rates.py -v`
Expected: FAIL only if Tasks 1-4 were skipped — should already PASS if done in order. If it
fails, it means `load_yield_curve()`'s index isn't tz/type-compatible with
`align_to_trading_days()`'s expectations; fix the mismatch before proceeding, don't skip
the test.

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all tests pass, `tests/test_rates.py` included (12 passed for this file, plus the
existing 603).

- [ ] **Step 4: Commit**

```bash
git add tests/test_rates.py
git commit -m "rates.py: end-to-end integration test, full suite green"
```

- [ ] **Step 5: Hand off — do not push, PR, or merge**

Phase 1 is code-complete and tested on the local `rates-yield-curve-infra` branch. Per
CLAUDE.md, the branch → PR → CI-wait → merge → verify → cleanup sequence is Dave's to run
via `/ship`, not an agent's to hand-run. Report status and stop here.

---

## Self-Review Notes (completed during planning)

- **Spec coverage:** every Phase-1 requirement in the design spec has a task — cache
  discipline (Task 1-3), calibration-only firewall (the design doesn't require a separate
  guard in `rates.py` itself; the firewall is enforced by callers only ever passing
  calibration-window-sliced data to anything calibration-time, same as `engine.load_prices()`
  — noted here so it isn't mistaken for a gap), the no-lookahead join (Task 4), no live
  network calls in tests (all tasks).
- **Placeholder scan:** clean — every step has real, runnable code.
- **Type consistency:** `load_yield_curve()` returns `(pd.DataFrame, str)` throughout;
  `align_to_trading_days()` takes `(pd.DataFrame, array-like of dates)` and returns
  `pd.DataFrame` indexed by date — consistent across every task and the integration test.
