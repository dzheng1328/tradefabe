# Dashboard Research Lab View — Sub-project 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `app.py`'s Streamlit Research Lab (`render_research_lab` +
`render_strategy_detail`) to the new React/FastAPI dashboard as a tabbed `/research`
page, and add a regression test proving a newly-promoted strategy needs zero
frontend/API code changes to appear anywhere in the new dashboard.

**Architecture:** `src/tradefabe/dashboard.py` gains one moved loader
(`load_pairs_backtest`, currently stranded in `app.py`) and one new pure function
(`piggyback_blend`) — everything else the API needs already exists there. Six new
`GET /api/research/*` endpoints in `src/tradefabe/api/main.py` assemble JSON from those
functions, following `book_detail`'s existing shape (`_finite_or_none`/`_deep_finite`
NaN-safety, Plotly `.to_json()` chart payloads). The frontend gets a real `/research`
route, a tabbed page shell holding one shared "selected strategy" piece of state, and
five tab components, each independently fetched on first activation.

**Tech Stack:** Python (FastAPI, pandas, Plotly) for the backend; React + TypeScript +
`react-router-dom` for the frontend; `pytest` (existing) for backend tests; Vitest +
React Testing Library (existing since 2a) for frontend tests.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-dashboard-research-lab-design.md`. Every
  task implements a section of it.
- `app.py` must keep working, unmodified in behavior, through every task — Streamlit
  stays the fallback per Dave's explicit call, it is not being retired.
- No chart/stat math gets duplicated in TypeScript — it stays server-side in
  `dashboard.py`/`main.py` and is reused, matching the pattern every prior sub-project
  established.
- No Streamlit import (`streamlit`, `st.*`) anywhere in `src/tradefabe/dashboard.py` or
  `src/tradefabe/api/`.
- Every numeric field that can be NaN/inf is routed through `_finite_or_none` /
  `_deep_finite` before it reaches a response body (same rule every existing endpoint
  in `main.py` follows).
- Full backend test suite (`.venv/bin/pytest tests/ -n0`) must pass at the end of every
  backend task. Full frontend suite (`npm test` in `frontend/`) must pass at the end of
  every frontend task.
- Branch: `feat/dashboard-research-lab` (already exists, holds the approved spec
  commit `d6a1ce7`). Continue on this branch — do not create a new one.
- GitHub issue #217 already filed for this sub-project.

---

### Task 1: Move `load_pairs_backtest()` from `app.py` to `dashboard.py`

**Files:**
- Modify: `src/tradefabe/dashboard.py` (add the function, undecorated)
- Modify: `app.py` (remove the local definition, call `dashboard.load_pairs_backtest()`
  at both existing call sites)
- Test: `tests/test_dashboard_loaders.py` (new file, or add to it if it already exists
  — check first with `ls tests/test_dashboard_loaders.py`)

**Interfaces:**
- Produces: `dashboard.load_pairs_backtest() -> pd.DataFrame | None` — OOS returns for
  family N (pairs/cointegration), same shape as `load_hourly_backtest()`/
  `load_kronos_backtest()`: `None` if `artifacts/pairs_returns.csv` doesn't exist yet,
  otherwise the CSV read with `index_col=0, parse_dates=True`.

`app.py`'s `render_research_lab` (line 733-735) already calls
`load_pairs_backtest()` as a bare module-level function — the FastAPI layer in
`src/tradefabe/api/` cannot import from `app.py` (it imports Streamlit at module load),
so Task 2's `/api/research/strategy/{name}` endpoint needs this reachable from
`dashboard.py`, same reasoning 2b's spec gave for moving `load_carry_risk()`.

- [ ] **Step 1: Check whether a loaders test file already exists**

Run: `ls tests/test_dashboard_loaders.py 2>&1 || echo "does not exist"`

If it exists, read it first and add the new test in the same style. If not, create it
per Step 2 below.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_dashboard_loaders.py
import os

from tradefabe import dashboard


def test_load_pairs_backtest_returns_none_when_artifact_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "ART", str(tmp_path))
    assert dashboard.load_pairs_backtest() is None


def test_load_pairs_backtest_reads_the_real_artifact_when_present():
    path = os.path.join(dashboard.ART, "pairs_returns.csv")
    if not os.path.exists(path):
        return  # study hasn't been run in this environment -- nothing to assert
    result = dashboard.load_pairs_backtest()
    assert result is not None
    assert not result.empty
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `.venv/bin/pytest tests/test_dashboard_loaders.py -v`
Expected: FAIL with `AttributeError: module 'tradefabe.dashboard' has no attribute
'load_pairs_backtest'`

- [ ] **Step 4: Move the function**

In `src/tradefabe/dashboard.py`, add (near the other `load_*_backtest` loaders, after
`load_hourly_backtest`):

```python
def load_pairs_backtest():
    """Backtest OOS returns for family N, pairs/cointegration (research/pairs_backtest.py,
    #172). A sixth curve source beside full/piggyback/factory/hourly/kronos -- same reason
    as hourly: the study builds its own signal over a ticker subset (only pairs that
    cleared the cointegration filter), not harness.py's full-universe daily cache. None if
    the study hasn't been run."""
    path = os.path.join(ART, "pairs_returns.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)
```

In `app.py`, delete the `@st.cache_data`-decorated `load_pairs_backtest` definition
(currently around line 163-172), and update its two call sites
(`render_strategy_detail`'s call and `render_research_lab`'s call, both currently
`load_pairs_backtest()`) to `dashboard.load_pairs_backtest()`.

- [ ] **Step 5: Run the test to confirm it passes**

Run: `.venv/bin/pytest tests/test_dashboard_loaders.py -v`
Expected: PASS

- [ ] **Step 6: Confirm `app.py` still imports and runs cleanly**

Run: `.venv/bin/python -c "import app"` — must not raise. (This only checks import-time
correctness; `app.py` has no importable test harness of its own, matching how every
prior sub-project verified this step.)

- [ ] **Step 7: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/tradefabe/dashboard.py app.py tests/test_dashboard_loaders.py
git commit -m "refactor: move load_pairs_backtest from app.py to dashboard.py

The FastAPI layer can't import app.py (Streamlit at module load); the new
/api/research/strategy/{name} endpoint needs this loader reachable, same
move-pattern 2b used for load_carry_risk."
```

---

### Task 2: `dashboard.piggyback_blend()` — the one new piece of shared math

**Files:**
- Modify: `src/tradefabe/dashboard.py` (add the function)
- Test: `tests/test_dashboard_loaders.py` (add to the file from Task 1)

**Interfaces:**
- Consumes: nothing new — takes `oos: pd.DataFrame` (from `load_backtest()`, already
  sliced to OOS by callers, matching `render_research_lab`'s own `oos` variable),
  `sleeve: list[str]`, `weight_pct: int`.
- Produces: `dashboard.piggyback_blend(oos: pd.DataFrame, sleeve: list[str], weight_pct:
  int) -> dict` with keys `combo: pd.Series` (cumulative growth of $1, indexed like
  `oos`), `bench_stats: dict` (`ann_stats(oos["bench_6040"])`), `combo_stats: dict`
  (`ann_stats(combo_returns)`) — Task 5's endpoint turns this into JSON.

This is the one genuinely new calculation (not a straight port) — `render_research_lab`
computes the blend inline with a Streamlit slider driving it. Pulling it into
`dashboard.py` keeps it a single source of truth per the Global Constraints, and makes
Task 5's endpoint a thin JSON wrapper, matching every other endpoint in `main.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_loaders.py (append)
import pandas as pd

from tradefabe.dashboard import piggyback_blend


def test_piggyback_blend_zero_weight_equals_bench_alone():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    oos = pd.DataFrame({
        "bench_6040": [0.01, -0.005, 0.02, 0.0, 0.01],
        "strat_a": [0.03, 0.03, -0.01, 0.02, 0.0],
    }, index=idx)
    result = piggyback_blend(oos, ["strat_a"], 0)
    expected_bench_growth = (1 + oos["bench_6040"]).cumprod()
    pd.testing.assert_series_equal(result["combo"], expected_bench_growth, check_names=False)


def test_piggyback_blend_full_weight_equals_sleeve_mean():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    oos = pd.DataFrame({
        "bench_6040": [0.01, -0.005, 0.02, 0.0, 0.01],
        "strat_a": [0.03, 0.03, -0.01, 0.02, 0.0],
        "strat_b": [-0.01, 0.01, 0.01, 0.04, -0.02],
    }, index=idx)
    result = piggyback_blend(oos, ["strat_a", "strat_b"], 100)
    sleeve_mean = oos[["strat_a", "strat_b"]].mean(axis=1)
    expected_growth = (1 + sleeve_mean).cumprod()
    pd.testing.assert_series_equal(result["combo"], expected_growth, check_names=False)


def test_piggyback_blend_returns_bench_and_combo_stats():
    idx = pd.date_range("2020-01-01", periods=30, freq="D")
    oos = pd.DataFrame({
        "bench_6040": [0.001] * 30,
        "strat_a": [0.002] * 30,
    }, index=idx)
    result = piggyback_blend(oos, ["strat_a"], 30)
    assert "bench_stats" in result and "Sharpe" in result["bench_stats"]
    assert "combo_stats" in result and "Sharpe" in result["combo_stats"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/pytest tests/test_dashboard_loaders.py -v -k piggyback_blend`
Expected: FAIL with `ImportError: cannot import name 'piggyback_blend'`

- [ ] **Step 3: Implement it**

Add to `src/tradefabe/dashboard.py`, near `growth_chart` (which the endpoint will pair
it with):

```python
def piggyback_blend(oos, sleeve, weight_pct):
    """Blend an equal-weighted sleeve of strategies into the 60/40 core at weight_pct%
    (0-100), mirroring render_research_lab's Streamlit slider inline exactly -- same
    (1-w)*bench + w*sleeve_mean formula, just returned as data instead of drawn as a
    chart directly. weight_pct=0 degenerates to the bench alone; weight_pct=100 to the
    sleeve mean alone -- both are valid inputs, not edge cases to special-case."""
    w = weight_pct / 100
    sleeve_returns = oos[sleeve].mean(axis=1)
    bench_returns = oos["bench_6040"].fillna(0)
    combo_returns = (1 - w) * bench_returns + w * sleeve_returns.fillna(0)
    return {
        "combo": (1 + combo_returns).cumprod(),
        "bench_stats": ann_stats(bench_returns),
        "combo_stats": ann_stats(combo_returns),
    }
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `.venv/bin/pytest tests/test_dashboard_loaders.py -v -k piggyback_blend`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/dashboard.py tests/test_dashboard_loaders.py
git commit -m "feat: add dashboard.piggyback_blend, shared math for the piggyback lab endpoint"
```

---

### Task 3: `GET /api/research/overview` and `GET /api/research/verdicts`

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Test: `tests/test_api_research.py` (new file)

**Interfaces:**
- Consumes: `dashboard.load_backtest()`, `dashboard.latest_verdicts(gy)`,
  `dashboard.growth_chart(show, colors)`, `dashboard.correlation_heatmap(cm)`,
  `dashboard.SLOTS`, `dashboard.BENCH_C`, `dashboard.SPY_C` (all exist already).
- Produces:
  - `GET /api/research/overview` → `{meta: {source, start, end, oos_start, n_assets},
    stats: {n_tested, n_alive, n_dead, luck_floor_p95, best_strategy, best_sharpe,
    bench_sharpe}, strategies: [str], growth_chart: {...}, correlation_heatmap: {...}}`
  - `GET /api/research/verdicts` → `{rows: [{strategy, freq, oos_sharpe, oos_sortino,
    oos_calmar, oos_maxdd, corr_bench, null_p95, verdict}]}`
  - Both `503` (`{"detail": "backtest artifacts not found"}`) if
    `dashboard.load_backtest()` raises `FileNotFoundError` — matching `book_detail`'s
    existing convention for the same failure mode.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_research.py
from fastapi.testclient import TestClient

from tradefabe.api.main import app


def test_overview_returns_expected_shape():
    client = TestClient(app)
    resp = client.get("/api/research/overview")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("meta", "stats", "strategies", "growth_chart", "correlation_heatmap"):
        assert key in body
    for key in ("source", "start", "end", "oos_start", "n_assets"):
        assert key in body["meta"]
    for key in ("n_tested", "n_alive", "n_dead", "luck_floor_p95", "best_strategy",
                "best_sharpe", "bench_sharpe"):
        assert key in body["stats"]
    assert body["stats"]["n_tested"] == body["stats"]["n_alive"] + body["stats"]["n_dead"]
    assert isinstance(body["strategies"], list) and len(body["strategies"]) > 0


def test_verdicts_row_count_matches_latest_verdicts():
    from tradefabe import dashboard
    client = TestClient(app)
    resp = client.get("/api/research/verdicts")
    assert resp.status_code == 200
    body = resp.json()
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    assert len(body["rows"]) == gy_last.shape[0]
    row = body["rows"][0]
    for key in ("strategy", "freq", "oos_sharpe", "oos_sortino", "oos_calmar",
                "oos_maxdd", "corr_bench", "null_p95", "verdict"):
        assert key in row
    assert row["verdict"] in ("ALIVE", "DEAD")
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_api_research.py -v`
Expected: FAIL with 404 (routes don't exist yet)

- [ ] **Step 3: Implement both endpoints**

Add to `src/tradefabe/api/main.py`, after the existing `book_detail` endpoint:

```python
@app.get("/api/research/overview")
def research_overview():
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    gy_last = dashboard.latest_verdicts(gy)
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]

    best = gy_last["oos_sharpe"].astype(float).idxmax()
    n_alive = int((gy_last["verdict"] == "ALIVE").sum())

    show = pd.DataFrame(index=oos.index)
    colors = []
    for s in strats:
        show[s] = (1 + oos[s].fillna(0)).cumprod()
        colors.append(dashboard.SLOTS[strats.index(s) % len(dashboard.SLOTS)])
    show["60/40"] = (1 + oos["bench_6040"].fillna(0)).cumprod()
    colors.append(dashboard.BENCH_C)
    show["SPY"] = (1 + oos["spy"].fillna(0)).cumprod()
    colors.append(dashboard.SPY_C)
    growth = dashboard.growth_chart(show, colors)

    cm = oos[strats + ["bench_6040"]].rename(columns={"bench_6040": "60/40"}).corr()
    heatmap = dashboard.correlation_heatmap(cm)

    return {
        "meta": {
            "source": meta["source"], "start": meta["start"], "end": meta["end"],
            "oos_start": meta["oos_start"], "n_assets": meta["n_assets"],
        },
        "stats": {
            "n_tested": int(gy_last.shape[0]), "n_alive": n_alive,
            "n_dead": int(gy_last.shape[0]) - n_alive,
            "luck_floor_p95": _finite_or_none(meta["null_bars"].get("M", float("nan"))),
            "best_strategy": best,
            "best_sharpe": _finite_or_none(gy_last.loc[best, "oos_sharpe"]),
            "bench_sharpe": _finite_or_none(gy_last["bench_sharpe"].iloc[0]),
        },
        "strategies": strats,
        "growth_chart": json.loads(growth.to_json()),
        "correlation_heatmap": json.loads(heatmap.to_json()),
    }


@app.get("/api/research/verdicts")
def research_verdicts():
    try:
        _full, _meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    gy_last = dashboard.latest_verdicts(gy)
    cols = ["freq", "oos_sharpe", "oos_sortino", "oos_calmar", "oos_maxdd",
            "corr_bench", "null_p95", "verdict"]
    rows = []
    for strategy, row in gy_last[cols].iterrows():
        rows.append({
            "strategy": strategy,
            "freq": row["freq"],
            "oos_sharpe": _finite_or_none(row["oos_sharpe"]),
            "oos_sortino": _finite_or_none(row["oos_sortino"]),
            "oos_calmar": _finite_or_none(row["oos_calmar"]),
            "oos_maxdd": _finite_or_none(row["oos_maxdd"]),
            "corr_bench": _finite_or_none(row["corr_bench"]),
            "null_p95": _finite_or_none(row["null_p95"]),
            "verdict": row["verdict"],
        })
    return {"rows": rows}
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_api_research.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_research.py
git commit -m "feat: add /api/research/overview and /api/research/verdicts endpoints"
```

---

### Task 4: `GET /api/research/strategy/{name}`

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Test: `tests/test_api_research.py`

**Interfaces:**
- Consumes: `dashboard.load_backtest()`, `dashboard.latest_verdicts`,
  `dashboard.strategy_description(name)`, `dashboard._dead_strategy_returns(name, oos,
  piggy, factory_bt, hourly_bt, kronos_bt, pairs_bt, pipeline_bt)`,
  `dashboard.ann_stats(r)`, `dashboard.backtest_chart(eq, dashboard.INK2)`, all six
  `load_*_backtest()` loaders (now including `load_pairs_backtest` from Task 1).
- Produces: `GET /api/research/strategy/{name}` → `200` with `{name, blurb, verdict,
  freq, corr_bench, null_p95, has_returns: bool, stats: {Sharpe, Sortino, Calmar,
  MaxDD, CAGR?, Vol?}, chart: {...} | null}` — `CAGR`/`Vol` and `chart` present only
  when `has_returns` is true (mirrors `render_strategy_detail`'s own `if r is not None`
  branch, which only has 4 stats + no chart in the fallback case). `404` if `name` is
  not in `gy_last.index`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_research.py (append)
def test_strategy_detail_unknown_name_is_404():
    client = TestClient(app)
    resp = client.get("/api/research/strategy/not_a_real_strategy")
    assert resp.status_code == 404


def test_strategy_detail_known_strategy_has_expected_shape():
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    name = gy_last.index[0]
    resp = client.get(f"/api/research/strategy/{name}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == name
    assert body["verdict"] in ("ALIVE", "DEAD")
    assert "Sharpe" in body["stats"]
    if body["has_returns"]:
        assert "CAGR" in body["stats"] and "Vol" in body["stats"]
        assert body["chart"] is not None
    else:
        assert body["chart"] is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_api_research.py -v -k strategy_detail`
Expected: FAIL (404 route not found for both)

- [ ] **Step 3: Implement**

Add to `src/tradefabe/api/main.py`:

```python
@app.get("/api/research/strategy/{name}")
def research_strategy_detail(name: str):
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    gy_last = dashboard.latest_verdicts(gy)
    if name not in gy_last.index:
        raise HTTPException(status_code=404, detail=f"unknown strategy: {name}")
    row = gy_last.loc[name]

    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    piggy = dashboard.load_piggyback_backtest()
    factory_bt = dashboard.load_factory_backtest()
    hourly_bt = dashboard.load_hourly_backtest()
    kronos_bt = dashboard.load_kronos_backtest()
    pairs_bt = dashboard.load_pairs_backtest()
    pipeline_bt = dashboard.load_pipeline_backtest()

    r = dashboard._dead_strategy_returns(name, oos, piggy, factory_bt, hourly_bt,
                                          kronos_bt, pairs_bt, pipeline_bt)

    body = {
        "name": name,
        "blurb": dashboard.strategy_description(name),
        "verdict": row["verdict"],
        "freq": row["freq"],
        "corr_bench": _finite_or_none(row["corr_bench"]),
        "null_p95": _finite_or_none(row["null_p95"]),
        "has_returns": r is not None,
    }
    if r is not None:
        s = dashboard.ann_stats(r)
        body["stats"] = _stats_json(s)
        eq = (1 + r).cumprod()
        chart = dashboard.backtest_chart(eq, dashboard.INK2)
        body["chart"] = json.loads(chart.to_json())
    else:
        body["stats"] = {
            "Sharpe": _finite_or_none(row["oos_sharpe"]),
            "Sortino": _finite_or_none(row["oos_sortino"]),
            "Calmar": _finite_or_none(row["oos_calmar"]),
            "MaxDD": _finite_or_none(row["oos_maxdd"]),
        }
        body["chart"] = None
    return body
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_api_research.py -v -k strategy_detail`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_research.py
git commit -m "feat: add /api/research/strategy/{name} endpoint"
```

---

### Task 5: `GET /api/research/luck_floor`, `GET /api/research/drawdown`, `GET /api/research/piggyback`

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Test: `tests/test_api_research.py`

**Interfaces:**
- Consumes: `dashboard.luck_floor_chart(arr, freq_label, marks, color_of)`,
  `dashboard.drawdown_chart(dd, color)`, `dashboard.piggyback_blend` (Task 2),
  `dashboard.SLOTS`, `dashboard.BENCH_C`, `dashboard.SPY_C`, `dashboard.INK2`.
- Produces:
  - `GET /api/research/luck_floor?strategy=...` → `{chart: {...}, label: str}`. `400`
    if `strategy` isn't a key in `nulls` (per-strategy artifact shape) — this endpoint
    only supports the current per-strategy null shape (DOCTRINE v1.5+); the legacy
    per-frequency `{M,W,D}` shape stays Streamlit-only since no live artifact has used
    it since 2026-07-29 per DOCTRINE.md's own discontinuity note, and adding dead-code
    branches for an artifact shape nothing produces anymore isn't worth the surface
    area (deviation from the spec's original "or freq=... fallback" — logged here per
    Task 7's self-review, not silently dropped).
  - `GET /api/research/drawdown?pick=...` → `{chart: {...}, max_drawdown: float}`.
    `pick` is a strategy name, `"60/40"`, or `"SPY"`. `400` on an unrecognized pick.
  - `GET /api/research/piggyback?sleeve=a,b&weight=30` → `{stats: {sharpe,
    sharpe_delta, calmar, calmar_delta, maxdd, maxdd_delta}, chart: {...}}`. `400` if
    `sleeve` is empty or any name isn't a valid OOS column, or `weight` isn't in
    `[0, 100]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_research.py (append)
def test_luck_floor_unknown_strategy_is_400():
    client = TestClient(app)
    resp = client.get("/api/research/luck_floor?strategy=not_a_real_strategy")
    assert resp.status_code == 400


def test_luck_floor_known_strategy_returns_chart():
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, nulls, _gy = dashboard.load_backtest()
    strategy = next(iter(nulls))
    resp = client.get(f"/api/research/luck_floor?strategy={strategy}")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body and "label" in body


def test_drawdown_bench_pick():
    client = TestClient(app)
    resp = client.get("/api/research/drawdown?pick=60/40")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body
    assert body["max_drawdown"] <= 0


def test_drawdown_unknown_pick_is_400():
    client = TestClient(app)
    resp = client.get("/api/research/drawdown?pick=not_a_real_pick")
    assert resp.status_code == 400


def test_piggyback_zero_weight_matches_bench_sharpe():
    from tradefabe import dashboard
    client = TestClient(app)
    full, meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    strat = gy_last.index[0]
    resp = client.get(f"/api/research/piggyback?sleeve={strat}&weight=0")
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["stats"]["sharpe_delta"]) < 1e-6
    assert "chart" in body


def test_piggyback_empty_sleeve_is_400():
    client = TestClient(app)
    resp = client.get("/api/research/piggyback?sleeve=&weight=30")
    assert resp.status_code == 400


def test_piggyback_weight_out_of_range_is_400():
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    strat = gy_last.index[0]
    resp = client.get(f"/api/research/piggyback?sleeve={strat}&weight=150")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_api_research.py -v -k "luck_floor or drawdown or piggyback"`
Expected: FAIL (routes don't exist)

- [ ] **Step 3: Implement**

Add to `src/tradefabe/api/main.py`:

```python
@app.get("/api/research/luck_floor")
def research_luck_floor(strategy: str):
    try:
        full, meta, nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")
    if strategy not in nulls:
        raise HTTPException(status_code=400, detail=f"no null distribution for: {strategy}")

    gy_last = dashboard.latest_verdicts(gy)
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
    color_of = {s: dashboard.SLOTS[i % len(dashboard.SLOTS)] for i, s in enumerate(strats)}
    arr = nulls[strategy]
    freq = meta.get("strategy_freq", {}).get(strategy, "")
    marks = ([(strategy, float(gy_last.loc[strategy, "oos_sharpe"]))]
              if strategy in gy_last.index else [])
    freq_names = {"M": "Monthly-rebalanced", "W": "Weekly-rebalanced", "D": "Daily-rebalanced"}
    label = f"{freq_names.get(freq, freq)} — {strategy}" if freq else strategy
    chart = dashboard.luck_floor_chart(arr, label, marks, color_of)
    return {"chart": json.loads(chart.to_json()), "label": label}


@app.get("/api/research/drawdown")
def research_drawdown(pick: str):
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
    col = {"60/40": "bench_6040", "SPY": "spy"}.get(pick, pick)
    if col not in oos.columns:
        raise HTTPException(status_code=400, detail=f"unknown pick: {pick}")

    color_of = {s: dashboard.SLOTS[i % len(dashboard.SLOTS)] for i, s in enumerate(strats)}
    c = color_of.get(pick, dashboard.BENCH_C if pick == "60/40" else dashboard.SPY_C)
    r = oos[col].fillna(0)
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    chart = dashboard.drawdown_chart(dd, c)
    return {"chart": json.loads(chart.to_json()), "max_drawdown": _finite_or_none(dd.min())}


@app.get("/api/research/piggyback")
def research_piggyback(sleeve: str, weight: int):
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")
    if not (0 <= weight <= 100):
        raise HTTPException(status_code=400, detail="weight must be 0-100")

    sleeve_names = [s for s in sleeve.split(",") if s]
    if not sleeve_names:
        raise HTTPException(status_code=400, detail="sleeve must name at least one strategy")

    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    unknown = [s for s in sleeve_names if s not in oos.columns]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies in sleeve: {unknown}")

    result = dashboard.piggyback_blend(oos, sleeve_names, weight)
    bench = result["bench_stats"]
    combo = result["combo_stats"]
    bench_growth = (1 + oos["bench_6040"].fillna(0)).cumprod()
    show = pd.DataFrame({"60/40 + sleeve": result["combo"], "60/40 alone": bench_growth})
    chart = dashboard.growth_chart(show, ["#2a78d6", dashboard.BENCH_C])

    return {
        "stats": {
            "sharpe": _finite_or_none(combo["Sharpe"]),
            "sharpe_delta": _finite_or_none(combo["Sharpe"] - bench["Sharpe"]),
            "calmar": _finite_or_none(combo["Calmar"]),
            "calmar_delta": _finite_or_none(combo["Calmar"] - bench["Calmar"]),
            "maxdd": _finite_or_none(combo["MaxDD"]),
            "maxdd_delta": _finite_or_none(combo["MaxDD"] - bench["MaxDD"]),
        },
        "chart": json.loads(chart.to_json()),
    }
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_api_research.py -v`
Expected: PASS (all tests in the file, including Tasks 3-4's)

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_research.py
git commit -m "feat: add /api/research/luck_floor, /drawdown, /piggyback endpoints"
```

---

### Task 6: Auto-add regression test

**Files:**
- Test: `tests/test_api_research_autoadd.py` (new file)

**Interfaces:**
- Consumes: `dashboard.book_panel_data`, `dashboard.load_paper_state`,
  `main.books_summary`, `main.book_detail` — no new production code, this task only
  adds coverage per the spec's "prove, not assert" auto-add requirement.

This is the "main priority" Dave named: confirm a brand-new strategy name, present only
in `factory_returns.csv` (the cascade's third source) and nowhere else, resolves
correctly through both the Paper Books summary path and the Research Lab strategy-
detail path with no code path treating it specially.

- [ ] **Step 1: Write the test**

```python
# tests/test_api_research_autoadd.py
"""Regression test for the auto-add claim in
docs/superpowers/specs/2026-08-13-dashboard-research-lab-design.md: a strategy that
exists ONLY in factory_returns.csv (never in full_returns.csv, piggyback_returns.csv,
or any state/paper/*.json book file) must still resolve through
dashboard._dead_strategy_returns -- the exact code path Research Lab's strategy-detail
endpoint uses for any graveyard entry that was never promoted to a live paper book.
This is the generic-resolution guarantee CLAUDE.md's 2026-07-26 outage note warns
about breaking silently."""
import pandas as pd

from tradefabe import dashboard


def test_dead_strategy_returns_resolves_a_factory_only_strategy():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    oos = pd.DataFrame({"bench_6040": [0.001] * 10, "spy": [0.001] * 10}, index=idx)
    factory_bt = pd.DataFrame({"brand_new_factory_candidate_xyz": [0.002] * 10}, index=idx)

    result = dashboard._dead_strategy_returns(
        "brand_new_factory_candidate_xyz", oos, piggy=None, factory_bt=factory_bt,
        hourly_bt=None, kronos_bt=None, pairs_bt=None, pipeline_bt=None,
    )
    assert result is not None
    assert len(result) == 10


def test_dead_strategy_returns_resolves_a_pipeline_only_strategy():
    """Same guarantee for the pipeline's own promoted-candidate CSV (#180) -- the
    source this repo's daily pipeline actually writes to (see pipeline_returns.csv
    in dashboard.load_pipeline_backtest's docstring)."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    oos = pd.DataFrame({"bench_6040": [0.001] * 10, "spy": [0.001] * 10}, index=idx)
    pipeline_bt = pd.DataFrame({"rp_new_candidate_abc": [0.0015] * 10}, index=idx)

    result = dashboard._dead_strategy_returns(
        "rp_new_candidate_abc", oos, piggy=None, factory_bt=None, hourly_bt=None,
        kronos_bt=None, pairs_bt=None, pipeline_bt=pipeline_bt,
    )
    assert result is not None
    assert len(result) == 10


def test_books_summary_has_no_hardcoded_book_names():
    """books_summary()'s output is entirely a function of load_paper_state() --
    confirms the API layer itself never special-cases a strategy name (the only
    intentional exception is the frontend's single FEATURED_BOOK cosmetic pick,
    which is a UI badge, not a data-inclusion filter -- out of scope for this test)."""
    from tradefabe import dashboard
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    names_in_state = set(psum["book"].tolist())
    from fastapi.testclient import TestClient
    from tradefabe.api.main import app
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=recent")
    body = resp.json()
    names_in_response = {b["book"] for b in body["books"]}
    assert names_in_response == names_in_state
```

- [ ] **Step 2: Run to confirm current behavior**

Run: `.venv/bin/pytest tests/test_api_research_autoadd.py -v`
Expected: PASS immediately — this is a regression test for existing behavior, not a
new feature. If any of these three tests FAIL, that is a real gap the spec's auto-add
claim didn't anticipate; stop and report it rather than editing the test to pass.

- [ ] **Step 3: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_research_autoadd.py
git commit -m "test: pin down that new strategies need zero hardcoded wiring to appear

Regression coverage for the auto-add claim in the Research Lab design spec --
_dead_strategy_returns already resolves factory-only and pipeline-only
strategies generically, and books_summary is driven entirely by
load_paper_state() with no hardcoded name list."
```

---

### Task 7: Nav wiring — real routes for Paper Books and Research Lab

**Files:**
- Modify: `frontend/src/components/Nav.tsx`
- Test: `frontend/src/components/Nav.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `react-router-dom`'s `NavLink` (already a dependency, used elsewhere via
  `Link`/`useNavigate` in `RowList.tsx`).
- Produces: `Nav.tsx` renders two real links — `/books` ("Paper Books") and `/research`
  ("Research Lab") — with the existing accent-underline treatment applied to whichever
  one matches the current route, instead of the underline being hardcoded onto "Paper
  Books" as static markup.

Both nav items are currently plain, non-interactive `<div>`s (confirmed by reading the
file directly — not links at all, so there is no page to navigate to yet even after
Task 9 adds the route). This blocks every other frontend task in this plan from being
reachable through the UI.

- [ ] **Step 1: Read the existing Nav test to match its conventions**

Run: `cat frontend/src/components/Nav.test.tsx`

- [ ] **Step 2: Write the failing test**

Add to `frontend/src/components/Nav.test.tsx` (wrap the render in a `MemoryRouter`,
matching `RowList.test.tsx`'s existing pattern for anything using `react-router-dom`):

```tsx
import { MemoryRouter } from "react-router-dom";
// ... existing imports stay

it("marks Research Lab as the active link on /research", () => {
  render(
    <MemoryRouter initialEntries={["/research"]}>
      <Nav />
    </MemoryRouter>
  );
  const researchLink = screen.getByRole("link", { name: "Research Lab" });
  expect(researchLink).toHaveAttribute("aria-current", "page");
  const booksLink = screen.getByRole("link", { name: "Paper Books" });
  expect(booksLink).not.toHaveAttribute("aria-current");
});

it("marks Paper Books as the active link on /books", () => {
  render(
    <MemoryRouter initialEntries={["/books"]}>
      <Nav />
    </MemoryRouter>
  );
  expect(screen.getByRole("link", { name: "Paper Books" })).toHaveAttribute("aria-current", "page");
});
```

Check the existing test file's top-level `render(<Nav />)` calls (there will be at
least one, testing the sound toggle) — wrap those in `<MemoryRouter>` too, since `Nav`
will now use `NavLink`, which throws outside a router context.

- [ ] **Step 3: Run to confirm failure**

Run: `cd frontend && npm test -- Nav.test.tsx`
Expected: FAIL (no links exist yet / existing tests throw outside a router)

- [ ] **Step 4: Implement**

Replace the two hardcoded nav-item `<div>`s in `Nav.tsx` with:

```tsx
import { NavLink } from "react-router-dom";
// (add to existing imports)

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink to={to} className="relative text-ink no-underline">
      {({ isActive }) => (
        <>
          {label}
          {isActive && (
            <span className="family-underline absolute -bottom-1.5 left-0 right-0 h-px bg-accent origin-left animate-underline-draw" />
          )}
        </>
      )}
    </NavLink>
  );
}
```

Then replace the two static blocks:

```tsx
<div className="relative text-ink">
  Paper Books
  <span className="family-underline absolute -bottom-1.5 left-0 right-0 h-px bg-accent origin-left animate-underline-draw" />
</div>
<div>Research Lab</div>
```

with:

```tsx
<NavItem to="/books" label="Paper Books" />
<NavItem to="/research" label="Research Lab" />
```

`NavLink`'s render-prop `isActive` already handles the `/books/:name` sub-routes
correctly (any path starting with `/books` matches, since `NavLink` matches by prefix
unless `end` is passed — leave `end` off deliberately, same reasoning `Nav`'s original
static markup had for treating every `/books/*` view as "Paper Books is active").

- [ ] **Step 5: Run the test to confirm it passes**

Run: `cd frontend && npm test -- Nav.test.tsx`
Expected: PASS

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS (this will fail until Task 9 adds the `/research` route only if some
other test renders `Nav` inside a full `<App>` — check for that; if `Nav.test.tsx`
renders `Nav` standalone inside its own `MemoryRouter` as above, no route needs to
exist yet for these tests to pass, since `MemoryRouter` doesn't require registered
`<Route>`s to resolve `NavLink`'s active state).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Nav.tsx frontend/src/components/Nav.test.tsx
git commit -m "fix: make Nav's Paper Books / Research Lab items real, active-aware links

Both were static, non-interactive divs -- there was no way to reach any
page but Paper Books through the nav at all."
```

---

### Task 8: `ResearchOverview.tsx` and `VerdictsTable.tsx`

**Files:**
- Create: `frontend/src/components/ResearchOverview.tsx`
- Create: `frontend/src/components/ResearchOverview.test.tsx`
- Create: `frontend/src/components/VerdictsTable.tsx`
- Create: `frontend/src/components/VerdictsTable.test.tsx`

**Interfaces:**
- Consumes: `GET /api/research/overview` (Task 3) and `GET /api/research/verdicts`
  (Task 3) response shapes, `StatTile` (existing), `PlotlyChart` (existing, lazy-loaded
  the same way `DetailPanel.tsx` does).
- Produces: `ResearchOverview` — no props, fetches its own data on mount (matches
  `RowList`'s existing self-fetching pattern). `VerdictsTable({ onSelect }: { onSelect:
  (name: string) => void })` — fetches its own rows, calls `onSelect` when a row is
  clicked; Task 10's page shell passes its shared-selection setter down as `onSelect`.

- [ ] **Step 1: Write `ResearchOverview.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ResearchOverview from "./ResearchOverview";

const OVERVIEW_RESPONSE = {
  meta: { source: "cache", start: "2007-01-03", end: "2026-08-13", oos_start: "2018-01-01", n_assets: 15 },
  stats: {
    n_tested: 477, n_alive: 4, n_dead: 473, luck_floor_p95: 0.65,
    best_strategy: "carry_btc_eth", best_sharpe: 1.14, bench_sharpe: 0.58,
  },
  strategies: ["tsmom_12m", "carry_btc_eth"],
  growth_chart: { data: [], layout: {} },
  correlation_heatmap: { data: [], layout: {} },
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) })
  ) as unknown as typeof fetch;
});

describe("ResearchOverview", () => {
  it("renders the eyebrow stats once data lands", async () => {
    render(<ResearchOverview />);
    await waitFor(() => expect(screen.getByText("477")).toBeInTheDocument());
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("473")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Write `VerdictsTable.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import VerdictsTable from "./VerdictsTable";

const VERDICTS_RESPONSE = {
  rows: [
    { strategy: "carry_btc_eth", freq: "D", oos_sharpe: 1.14, oos_sortino: 1.5,
      oos_calmar: 2.1, oos_maxdd: -0.062, corr_bench: 0.1, null_p95: 0.65, verdict: "ALIVE" },
    { strategy: "tsmom_gen_382d", freq: "M", oos_sharpe: 0.59, oos_sortino: 0.78,
      oos_calmar: 0.25, oos_maxdd: -0.113, corr_bench: 0.39, null_p95: 0.65, verdict: "DEAD" },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(VERDICTS_RESPONSE) })
  ) as unknown as typeof fetch;
});

describe("VerdictsTable", () => {
  it("renders one row per strategy with a colored verdict", async () => {
    render(<VerdictsTable onSelect={() => {}} />);
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    expect(screen.getByText("ALIVE")).toBeInTheDocument();
    expect(screen.getByText("DEAD")).toBeInTheDocument();
  });

  it("calls onSelect with the strategy name when a row is clicked", async () => {
    const onSelect = vi.fn();
    render(<VerdictsTable onSelect={onSelect} />);
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    await userEvent.click(screen.getByText("carry_btc_eth"));
    expect(onSelect).toHaveBeenCalledWith("carry_btc_eth");
  });
});
```

- [ ] **Step 3: Run both to confirm failure**

Run: `cd frontend && npm test -- ResearchOverview.test.tsx VerdictsTable.test.tsx`
Expected: FAIL (modules don't exist)

- [ ] **Step 4: Implement `ResearchOverview.tsx`**

```tsx
import { lazy, Suspense, useEffect, useState } from "react";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type OverviewResponse = {
  meta: { source: string; start: string; end: string; oos_start: string; n_assets: number };
  stats: {
    n_tested: number; n_alive: number; n_dead: number; luck_floor_p95: number | null;
    best_strategy: string; best_sharpe: number | null; bench_sharpe: number | null;
  };
  strategies: string[];
  growth_chart: { data: unknown[]; layout: Record<string, unknown> };
  correlation_heatmap: { data: unknown[]; layout: Record<string, unknown> };
};

export default function ResearchOverview() {
  const [data, setData] = useState<OverviewResponse | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/research/overview")
      .then((res) => res.json())
      .then(setData);
  }, []);

  if (!data) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-ink-muted font-mono">
        DATA <strong className="text-ink">{data.meta.source}</strong> {data.meta.start} →{" "}
        {data.meta.end} · OOS FROM <strong className="text-ink">{data.meta.oos_start}</strong> ·{" "}
        {data.meta.n_assets} assets
      </p>
      <div className="grid grid-cols-5 gap-4 mt-4">
        <StatTile label="Tested" value={String(data.stats.n_tested)} />
        <StatTile label="Alive" value={String(data.stats.n_alive)} />
        <StatTile label="Dead" value={String(data.stats.n_dead)} />
        <StatTile label="Luck floor p95" value={fmt(data.stats.luck_floor_p95)} />
        <StatTile label={`Best · ${data.stats.best_strategy}`} value={fmt(data.stats.best_sharpe)} />
      </div>
      <p className="text-xs text-ink-muted mt-2 font-mono">
        60/40 benchmark OOS Sharpe: <strong className="text-ink">{fmt(data.stats.bench_sharpe)}</strong>
      </p>
      <div className="mt-6">
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={data.growth_chart} />
        </Suspense>
      </div>
      <div className="mt-6">
        <Suspense fallback={<div className="h-[440px]" />}>
          <PlotlyChart figure={data.correlation_heatmap} />
        </Suspense>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement `VerdictsTable.tsx`**

```tsx
import { useEffect, useState } from "react";
import { fmt } from "../lib/format";
import RingLoader from "./RingLoader";

type VerdictRow = {
  strategy: string; freq: string; oos_sharpe: number | null; oos_sortino: number | null;
  oos_calmar: number | null; oos_maxdd: number | null; corr_bench: number | null;
  null_p95: number | null; verdict: string;
};

const COLUMNS: { key: keyof VerdictRow; label: string }[] = [
  { key: "strategy", label: "Strategy" }, { key: "freq", label: "Freq" },
  { key: "oos_sharpe", label: "Sharpe" }, { key: "oos_sortino", label: "Sortino" },
  { key: "oos_calmar", label: "Calmar" }, { key: "oos_maxdd", label: "MaxDD" },
  { key: "corr_bench", label: "Corr" }, { key: "null_p95", label: "Null p95" },
  { key: "verdict", label: "Verdict" },
];

export default function VerdictsTable({ onSelect }: { onSelect: (name: string) => void }) {
  const [rows, setRows] = useState<VerdictRow[] | null>(null);
  const [sortKey, setSortKey] = useState<keyof VerdictRow>("strategy");
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  useEffect(() => {
    fetch("http://localhost:8000/api/research/verdicts")
      .then((res) => res.json())
      .then((body: { rows: VerdictRow[] }) => setRows(body.rows));
  }, []);

  if (!rows) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av === null) return 1;
    if (bv === null) return -1;
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });

  function toggleSort(key: keyof VerdictRow) {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(1); }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead className="text-ink-muted uppercase">
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} className="text-left py-1 cursor-pointer select-none" onClick={() => toggleSort(c.key)}>
                {c.label}{sortKey === c.key ? (sortDir === 1 ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.strategy}
              className="border-t border-white/5 hover:bg-white/5 cursor-pointer"
              onClick={() => onSelect(r.strategy)}
            >
              <td className="py-1 text-ink">{r.strategy}</td>
              <td className="text-ink-muted">{r.freq}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_sharpe)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_sortino)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_calmar)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_maxdd, "pct")}</td>
              <td className="text-ink tabular-nums">{fmt(r.corr_bench)}</td>
              <td className="text-ink tabular-nums">{fmt(r.null_p95)}</td>
              <td className={r.verdict === "ALIVE" ? "text-accent" : "text-red-400"}>{r.verdict}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 6: Run both tests to confirm they pass**

Run: `cd frontend && npm test -- ResearchOverview.test.tsx VerdictsTable.test.tsx`
Expected: PASS

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ResearchOverview.tsx frontend/src/components/ResearchOverview.test.tsx frontend/src/components/VerdictsTable.tsx frontend/src/components/VerdictsTable.test.tsx
git commit -m "feat: add ResearchOverview and VerdictsTable components"
```

---

### Task 9: `StrategyDetail.tsx` and `Diagnostics.tsx`

**Files:**
- Create: `frontend/src/components/StrategyDetail.tsx`
- Create: `frontend/src/components/StrategyDetail.test.tsx`
- Create: `frontend/src/components/Diagnostics.tsx`
- Create: `frontend/src/components/Diagnostics.test.tsx`

**Interfaces:**
- Consumes: `GET /api/research/strategy/{name}`, `GET /api/research/luck_floor`,
  `GET /api/research/drawdown` (all Tasks 4-5).
- Produces: `StrategyDetail({ selected }: { selected: string | null })` — empty state
  when `selected` is `null`. `Diagnostics({ selected }: { selected: string | null })`
  — same empty-state contract, holds its own local `pick` state for the drawdown
  selector (defaults to `selected` when it changes, matching Streamlit's own selectbox
  default-to-current-strategy behavior in spirit, but user-overridable within the tab).

- [ ] **Step 1: Write `StrategyDetail.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StrategyDetail from "./StrategyDetail";

const STRATEGY_RESPONSE = {
  name: "carry_btc_eth", blurb: "Delta-neutral funding carry.", verdict: "ALIVE",
  freq: "D", corr_bench: 0.1, null_p95: 0.65, has_returns: true,
  stats: { Sharpe: 1.14, Sortino: 1.5, Calmar: 2.1, MaxDD: -0.062, CAGR: 0.12, Vol: 0.08 },
  chart: { data: [], layout: {} },
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(STRATEGY_RESPONSE) })
  ) as unknown as typeof fetch;
});

describe("StrategyDetail", () => {
  it("shows an empty state with nothing selected", () => {
    render(<StrategyDetail selected={null} />);
    expect(screen.getByText(/pick a strategy/i)).toBeInTheDocument();
  });

  it("renders blurb, verdict, and stats once a strategy is selected", async () => {
    render(<StrategyDetail selected="carry_btc_eth" />);
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    expect(screen.getByText("Delta-neutral funding carry.")).toBeInTheDocument();
    expect(screen.getByText("ALIVE")).toBeInTheDocument();
    expect(screen.getByText("1.14")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Write `Diagnostics.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Diagnostics from "./Diagnostics";

const LUCK_FLOOR_RESPONSE = { chart: { data: [], layout: {} }, label: "Daily-rebalanced — carry_btc_eth" };
const DRAWDOWN_RESPONSE = { chart: { data: [], layout: {} }, max_drawdown: -0.062 };

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    if (url.includes("luck_floor")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LUCK_FLOOR_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(DRAWDOWN_RESPONSE) });
  }) as unknown as typeof fetch;
});

describe("Diagnostics", () => {
  it("shows an empty state with nothing selected", () => {
    render(<Diagnostics selected={null} />);
    expect(screen.getByText(/pick a strategy/i)).toBeInTheDocument();
  });

  it("fetches luck floor and drawdown for the selected strategy", async () => {
    render(<Diagnostics selected="carry_btc_eth" />);
    await waitFor(() => expect(screen.getByText(/Daily-rebalanced/)).toBeInTheDocument());
    expect(screen.getByText(/-6.2%/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run both to confirm failure**

Run: `cd frontend && npm test -- StrategyDetail.test.tsx Diagnostics.test.tsx`
Expected: FAIL (modules don't exist)

- [ ] **Step 4: Implement `StrategyDetail.tsx`**

```tsx
import { lazy, Suspense, useEffect, useState } from "react";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type StrategyResponse = {
  name: string; blurb: string; verdict: string; freq: string;
  corr_bench: number | null; null_p95: number | null; has_returns: boolean;
  stats: Record<string, number | null>;
  chart: { data: unknown[]; layout: Record<string, unknown> } | null;
};

export default function StrategyDetail({ selected }: { selected: string | null }) {
  const [data, setData] = useState<StrategyResponse | null>(null);

  useEffect(() => {
    if (!selected) { setData(null); return; }
    fetch(`http://localhost:8000/api/research/strategy/${selected}`)
      .then((res) => res.json())
      .then(setData);
  }, [selected]);

  if (!selected) {
    return <p className="text-ink-muted text-sm">Pick a strategy from the Verdicts tab to see its detail.</p>;
  }
  if (!data) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  const statEntries = data.has_returns
    ? (["Sharpe", "Sortino", "Calmar", "MaxDD", "CAGR", "Vol"] as const)
    : (["Sharpe", "Sortino", "Calmar", "MaxDD"] as const);

  return (
    <div>
      <h3 className="text-xl font-bold text-ink">{data.name}</h3>
      <p className="text-ink-muted mt-1 border-l-2 border-accent pl-3">{data.blurb}</p>
      <div className="grid grid-cols-6 gap-4 mt-4">
        {statEntries.map((label) => (
          <StatTile
            key={label}
            label={label === "MaxDD" ? "Max Drawdown" : label === "Vol" ? "Vol (ann.)" : label}
            value={fmt(data.stats[label], label === "MaxDD" || label === "CAGR" || label === "Vol" ? "pct" : "ratio")}
          />
        ))}
      </div>
      <p className="text-xs text-ink-muted mt-2 font-mono">
        Verdict: <span className={data.verdict === "ALIVE" ? "text-accent" : "text-red-400"}>{data.verdict}</span>
        {" · "}corr to 60/40: {fmt(data.corr_bench)} · noise floor: {fmt(data.null_p95)} · rebalance {data.freq}
      </p>
      {data.chart ? (
        <div className="mt-4">
          <Suspense fallback={<div className="h-[280px]" />}>
            <PlotlyChart figure={data.chart} />
          </Suspense>
        </div>
      ) : (
        <p className="text-xs text-ink-muted mt-4">
          Backtest return series isn't stored in the standard format for this strategy —
          showing the summary stats logged at evaluation time instead.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Implement `Diagnostics.tsx`**

```tsx
import { lazy, Suspense, useEffect, useState } from "react";
import RingLoader from "./RingLoader";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type ChartResponse = { chart: { data: unknown[]; layout: Record<string, unknown> } };

export default function Diagnostics({ selected }: { selected: string | null }) {
  const [luckFloor, setLuckFloor] = useState<(ChartResponse & { label: string }) | null>(null);
  const [drawdownPick, setDrawdownPick] = useState<string | null>(selected);
  const [drawdown, setDrawdown] = useState<(ChartResponse & { max_drawdown: number }) | null>(null);

  useEffect(() => { setDrawdownPick(selected); }, [selected]);

  useEffect(() => {
    if (!selected) { setLuckFloor(null); return; }
    fetch(`http://localhost:8000/api/research/luck_floor?strategy=${selected}`)
      .then((res) => res.json())
      .then(setLuckFloor);
  }, [selected]);

  useEffect(() => {
    if (!drawdownPick) { setDrawdown(null); return; }
    fetch(`http://localhost:8000/api/research/drawdown?pick=${encodeURIComponent(drawdownPick)}`)
      .then((res) => res.json())
      .then(setDrawdown);
  }, [drawdownPick]);

  if (!selected) {
    return <p className="text-ink-muted text-sm">Pick a strategy from the Verdicts tab to see its diagnostics.</p>;
  }

  return (
    <div>
      <h4 className="text-sm text-ink">{luckFloor?.label ?? "Luck floor"}</h4>
      {luckFloor ? (
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={luckFloor.chart} />
        </Suspense>
      ) : (
        <div className="flex justify-center py-12"><RingLoader /></div>
      )}

      <div className="mt-6 pt-6 border-t border-white/5">
        <div className="flex items-center justify-between">
          <h4 className="text-sm text-ink">Underwater — drawdown from peak</h4>
          <select
            value={drawdownPick ?? ""}
            onChange={(e) => setDrawdownPick(e.target.value)}
            className="bg-surface border border-white/10 rounded px-2 py-1 text-xs text-ink font-mono"
          >
            <option value={selected}>{selected}</option>
            <option value="60/40">60/40</option>
            <option value="SPY">SPY</option>
          </select>
        </div>
        {drawdown ? (
          <>
            <Suspense fallback={<div className="h-[280px]" />}>
              <PlotlyChart figure={drawdown.chart} />
            </Suspense>
            <p className="text-xs text-ink-muted mt-2">
              Max drawdown: <strong className="text-ink">{(drawdown.max_drawdown * 100).toFixed(1)}%</strong>
            </p>
          </>
        ) : (
          <div className="flex justify-center py-12"><RingLoader /></div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run both tests to confirm they pass**

Run: `cd frontend && npm test -- StrategyDetail.test.tsx Diagnostics.test.tsx`
Expected: PASS

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/StrategyDetail.tsx frontend/src/components/StrategyDetail.test.tsx frontend/src/components/Diagnostics.tsx frontend/src/components/Diagnostics.test.tsx
git commit -m "feat: add StrategyDetail and Diagnostics components"
```

---

### Task 10: `PiggybackLab.tsx`

**Files:**
- Create: `frontend/src/components/PiggybackLab.tsx`
- Create: `frontend/src/components/PiggybackLab.test.tsx`

**Interfaces:**
- Consumes: `GET /api/research/overview` (for the `strategies` list to populate the
  multiselect — refetched here rather than threaded down as a prop, matching how every
  other tab independently owns its data fetching), `GET /api/research/piggyback`
  (Task 5).
- Produces: `PiggybackLab()` — no props. Left column (1/3): range slider (0-50, step 5,
  matching Streamlit's `st.slider(..., 0, 50, 30, 5)`) + a strategy checkbox list
  defaulting to `["xsec_momentum", "tsmom_12m"]` when those names are present in the
  fetched `strategies` list (same Streamlit default), otherwise empty. Right column
  (2/3): 3 `StatTile`s (Sharpe/Calmar/MaxDD deltas) + comparison chart. Slider changes
  are debounced 250ms before firing the piggyback fetch.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/PiggybackLab.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PiggybackLab from "./PiggybackLab";

const OVERVIEW_RESPONSE = {
  meta: { source: "cache", start: "2007-01-03", end: "2026-08-13", oos_start: "2018-01-01", n_assets: 15 },
  stats: { n_tested: 2, n_alive: 1, n_dead: 1, luck_floor_p95: 0.65, best_strategy: "tsmom_12m", best_sharpe: 0.51, bench_sharpe: 0.58 },
  strategies: ["tsmom_12m", "xsec_momentum"],
  growth_chart: { data: [], layout: {} },
  correlation_heatmap: { data: [], layout: {} },
};

const PIGGYBACK_RESPONSE = {
  stats: { sharpe: 0.6, sharpe_delta: 0.02, calmar: 0.3, calmar_delta: 0.05, maxdd: -0.08, maxdd_delta: -0.01 },
  chart: { data: [], layout: {} },
};

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    if (url.includes("piggyback")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(PIGGYBACK_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) });
  }) as unknown as typeof fetch;
});

describe("PiggybackLab", () => {
  it("fetches the sleeve simulation once strategies are known and a sleeve is selected", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("0.02")).toBeInTheDocument(), { timeout: 1000 });
  });

  it("lets the user toggle a sleeve strategy off", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const checkbox = screen.getByLabelText("xsec_momentum");
    await userEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd frontend && npm test -- PiggybackLab.test.tsx`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/PiggybackLab.tsx
import { lazy, Suspense, useEffect, useState } from "react";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

const DEFAULT_SLEEVE = ["xsec_momentum", "tsmom_12m"];
const DEBOUNCE_MS = 250;

type PiggybackResponse = {
  stats: { sharpe: number | null; sharpe_delta: number | null; calmar: number | null;
           calmar_delta: number | null; maxdd: number | null; maxdd_delta: number | null };
  chart: { data: unknown[]; layout: Record<string, unknown> };
};

export default function PiggybackLab() {
  const [strategies, setStrategies] = useState<string[] | null>(null);
  const [weight, setWeight] = useState(30);
  const [sleeve, setSleeve] = useState<string[]>([]);
  const [result, setResult] = useState<PiggybackResponse | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/research/overview")
      .then((res) => res.json())
      .then((body: { strategies: string[] }) => {
        setStrategies(body.strategies);
        setSleeve(DEFAULT_SLEEVE.filter((s) => body.strategies.includes(s)));
      });
  }, []);

  useEffect(() => {
    if (sleeve.length === 0) { setResult(null); return; }
    const id = setTimeout(() => {
      fetch(`http://localhost:8000/api/research/piggyback?sleeve=${sleeve.join(",")}&weight=${weight}`)
        .then((res) => res.json())
        .then(setResult);
    }, DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [sleeve, weight]);

  function toggle(name: string) {
    setSleeve((prev) => (prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]));
  }

  if (!strategies) {
    return <div className="flex justify-center py-12"><RingLoader /></div>;
  }

  return (
    <div className="flex gap-6">
      <div className="w-1/3 shrink-0">
        <label className="text-xs text-ink-muted uppercase font-mono">Sleeve weight ({weight}%)</label>
        <input
          type="range" min={0} max={50} step={5} value={weight}
          onChange={(e) => setWeight(Number(e.target.value))}
          className="w-full accent-accent mt-2"
        />
        <div className="mt-4 space-y-1">
          <div className="text-xs text-ink-muted uppercase font-mono">Sleeve strategies</div>
          {strategies.map((s) => (
            <label key={s} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                aria-label={s}
                checked={sleeve.includes(s)}
                onChange={() => toggle(s)}
                className="accent-accent"
              />
              {s}
            </label>
          ))}
        </div>
      </div>
      <div className="flex-1">
        {result ? (
          <>
            <div className="grid grid-cols-3 gap-4">
              <StatTile label="Sharpe" value={`${fmt(result.stats.sharpe)} (${fmt(result.stats.sharpe_delta)} vs 60/40)`} />
              <StatTile label="Calmar" value={`${fmt(result.stats.calmar)} (${fmt(result.stats.calmar_delta)} vs 60/40)`} />
              <StatTile label="Max drawdown" value={`${fmt(result.stats.maxdd, "pct")} (${fmt(result.stats.maxdd_delta, "pct")} vs 60/40)`} />
            </div>
            <div className="mt-4">
              <Suspense fallback={<div className="h-[340px]" />}>
                <PlotlyChart figure={result.chart} />
              </Suspense>
            </div>
            <p className="text-xs text-ink-muted mt-2">
              Reminder: a sleeve usually LOWERS raw dollars while smoothing the ride — Sharpe up ≠ more profit.
            </p>
          </>
        ) : (
          <p className="text-ink-muted text-sm">Pick at least one sleeve strategy.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd frontend && npm test -- PiggybackLab.test.tsx`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PiggybackLab.tsx frontend/src/components/PiggybackLab.test.tsx
git commit -m "feat: add PiggybackLab component"
```

---

### Task 11: `ResearchLab.tsx` page shell + route wiring

**Files:**
- Create: `frontend/src/components/ResearchLab.tsx`
- Create: `frontend/src/components/ResearchLab.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: all five components from Tasks 8-10.
- Produces: `ResearchLab()` — the `/research` route's element. Owns `activeTab` and
  `selected` (shared strategy name) state. Renders a tab bar (native buttons, styled
  like `RowList`'s existing `Sort by` control) and only mounts the active tab's
  component — this is what makes each tab's fetch lazy (a component that has never
  mounted has never called its `useEffect`).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/ResearchLab.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ResearchLab from "./ResearchLab";

vi.mock("./ResearchOverview", () => ({ default: () => <div>Overview content</div> }));
vi.mock("./VerdictsTable", () => ({ default: () => <div>Verdicts content</div> }));
vi.mock("./StrategyDetail", () => ({ default: () => <div>Detail content</div> }));
vi.mock("./Diagnostics", () => ({ default: () => <div>Diagnostics content</div> }));
vi.mock("./PiggybackLab", () => ({ default: () => <div>Piggyback content</div> }));

describe("ResearchLab", () => {
  it("shows the Overview tab by default and not the others", () => {
    render(<ResearchLab />);
    expect(screen.getByText("Overview content")).toBeInTheDocument();
    expect(screen.queryByText("Verdicts content")).not.toBeInTheDocument();
  });

  it("mounts only the clicked tab's content", async () => {
    render(<ResearchLab />);
    await userEvent.click(screen.getByRole("button", { name: "Verdicts" }));
    expect(screen.getByText("Verdicts content")).toBeInTheDocument();
    expect(screen.queryByText("Overview content")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd frontend && npm test -- ResearchLab.test.tsx`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Implement `ResearchLab.tsx`**

```tsx
import { useState } from "react";
import ResearchOverview from "./ResearchOverview";
import VerdictsTable from "./VerdictsTable";
import StrategyDetail from "./StrategyDetail";
import Diagnostics from "./Diagnostics";
import PiggybackLab from "./PiggybackLab";

const TABS = ["Overview", "Verdicts", "Strategy Detail", "Diagnostics", "Piggyback Lab"] as const;
type Tab = (typeof TABS)[number];

export default function ResearchLab() {
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [selected, setSelected] = useState<string | null>(null);

  function selectAndShowDetail(name: string) {
    setSelected(name);
    setActiveTab("Strategy Detail");
  }

  return (
    <div className="p-10 overflow-y-auto h-full">
      <div className="flex gap-4 border-b border-white/5 pb-2 mb-6 text-sm font-mono uppercase">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={tab === activeTab ? "text-accent border-b-2 border-accent pb-1" : "text-ink-muted"}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Overview" && <ResearchOverview />}
      {activeTab === "Verdicts" && <VerdictsTable onSelect={selectAndShowDetail} />}
      {activeTab === "Strategy Detail" && <StrategyDetail selected={selected} />}
      {activeTab === "Diagnostics" && <Diagnostics selected={selected} />}
      {activeTab === "Piggyback Lab" && <PiggybackLab />}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd frontend && npm test -- ResearchLab.test.tsx`
Expected: PASS

- [ ] **Step 5: Wire the route into `App.tsx`**

Add the import and route:

```tsx
import ResearchLab from "./components/ResearchLab";
```

```tsx
<Route path="/research" element={
  <div className="h-screen flex flex-col overflow-hidden">
    <Nav />
    <ResearchLab />
  </div>
} />
```

placed inside the existing `<Routes>` block alongside `/books` and `/books/:name`.

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 7: Manual smoke test with both dev servers running**

Run (two terminals): `.venv/bin/tradefabe-api` and `cd frontend && npm run dev`. Open
`http://localhost:5173/research`, click through all five tabs, click a Verdicts row
and confirm it jumps to Strategy Detail with that strategy selected, exercise the
Piggyback Lab slider and checkboxes. Compare a couple of Sharpe numbers against
`localhost:8501`'s Research Lab for the same strategies to confirm parity.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ResearchLab.tsx frontend/src/components/ResearchLab.test.tsx frontend/src/App.tsx
git commit -m "feat: add /research route with tabbed ResearchLab page shell

Closes out sub-project 3 -- Research Lab is now reachable in the new
dashboard with full parity to Streamlit's render_research_lab."
```

---

### Task 12: Open the PR

**Files:** none (process step)

- [ ] **Step 1: Push the branch**

Run: `git push -u origin feat/dashboard-research-lab`

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "Dashboard rebuild, sub-project 3: Research Lab view + auto-add verification" --body-file - <<'EOF'
## Summary
- Ports app.py's Streamlit Research Lab (render_research_lab + render_strategy_detail)
  to a tabbed /research page in the new React/FastAPI dashboard: Overview, Verdicts,
  Strategy Detail, Diagnostics (luck floor + drawdown), and the interactive Piggyback
  Lab sleeve simulator.
- Adds 6 new read-only /api/research/* endpoints, all built from dashboard.py's
  existing chart/stat functions -- no new backend math except piggyback_blend(), which
  replaces an inline Streamlit-slider calculation with a single shared source of truth.
- Adds a regression test proving a strategy that exists only in factory_returns.csv or
  pipeline_returns.csv resolves generically through the existing data layer -- the
  "no hand-wiring per new strategy" requirement.
- Streamlit stays running unchanged as a fallback; this does not retire app.py or
  change what the desktop app points at.

Design spec: docs/superpowers/specs/2026-08-13-dashboard-research-lab-design.md
Closes #217

## Test plan
- [ ] `.venv/bin/pytest tests/ -n0` passes
- [ ] `cd frontend && npm test` passes
- [ ] Manual: both dev servers running, walk all five /research tabs, confirm chart
      parity against localhost:8501's Research Lab, exercise the piggyback slider
EOF
```

- [ ] **Step 3: Wait for CI, confirm it's green on the current head**

```bash
gh pr checks <N> --watch --interval 20
gh run view <id> --json headSha -q .headSha   # compare against:
git rev-parse HEAD
```

- [ ] **Step 4: Report the PR URL back to Dave and stop — merge is his call per repo convention** (branch → PR → CI-wait is as far as this plan goes; CLAUDE.md's merge sequence is a separate, explicit step Dave runs or asks for by name).

---

## Self-Review Notes

- **Spec coverage:** all 8 spec sections have a task — endpoints (Tasks 3-5), Research
  Lab page/components (Tasks 7-11), auto-add verification (Task 6), process (Task 12).
- **One documented deviation from the spec:** the `luck_floor` endpoint dropped the
  `freq=...` legacy-artifact fallback the spec originally listed as an alternative
  query param — no live artifact has used the per-frequency `{M,W,D}` null shape since
  DOCTRINE v1.5 (2026-07-29), and `dashboard.py`'s own shape-detection helper
  (`per_strategy = not set(nulls).issubset({"M","W","D"})`) exists in Streamlit for
  reading old artifacts, not producing new ones. If this turns out to matter, it's a
  small addition to Task 5, not a redesign.
- **Type consistency check:** `VerdictRow`/`VerdictResponse` field names match Task
  3's endpoint output exactly (`oos_sharpe`, `oos_sortino`, etc.); `StrategyResponse`
  in Task 9 matches Task 4's endpoint; `PiggybackResponse` in Task 10 matches Task 5's
  `/piggyback` endpoint. `ResearchLab.tsx`'s `selectAndShowDetail` passed as
  `VerdictsTable`'s `onSelect` prop matches the `(name: string) => void` signature
  Task 8 defined.
