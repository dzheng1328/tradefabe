# Dashboard Paper Books View — Slice 2b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the positions/trade-log/capital-deployed story for equity books and the
risk-monitor/risk-register story for the carry book to the detail panel 2a shipped,
reaching full functional parity with `app.py`'s Streamlit rendering.

**Architecture:** `src/tradefabe/dashboard.py` gains `load_carry_risk()` (moved from
`app.py`, same precedent as every other loader move in sub-projects 1/2a).
`GET /api/books/{name}/detail` flips `compute_positions` to `True` and grows new
JSON-safe fields built from data `book_panel_data()` already computes — no new backend
math. The frontend gets five new presentational components
(`DeploymentStats`/`PositionsTable`/`TradeLog`/`CarryRiskPanel`/`RiskRegister`), a small
shared `lib/format.ts` extracted from `DetailPanel.tsx`'s existing local `fmt`, and
`DetailPanel.tsx` grows one `kind`-branched block that composes them — it does not grow
new formatting/rendering logic of its own.

**Tech Stack:** Python (FastAPI, pandas) for the backend; React + TypeScript for the
frontend; Vitest + React Testing Library for frontend tests; `pytest` for backend tests.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-dashboard-paper-books-2b-design.md`. Every
  task implements a section of it.
- Full functional parity with `app.py`'s `render_strategy_panel`/`render_trade_log`/
  `render_carry_risk_panel`/`render_risk_register` — same tables, same captions and
  warnings, same risk-register entries. This is a port, not a redesign.
- `app.py` must keep working, unmodified in behavior, through every task — it's still
  the live dashboard.
- No Streamlit import anywhere in `src/tradefabe/dashboard.py` or `src/tradefabe/api/`.
- No new sound cues (see spec's Visual & motion language section) — new sections render
  silently, same as the existing stat grid.
- Full backend suite (`.venv/bin/pytest tests/ -n0`) and full frontend suite
  (`cd frontend && npm test`) must pass at the end of every task that touches their
  respective side.
- Branch: `feat/dashboard-paper-books-2b`, created off `main` as part of Task 1 below
  (holds the approved spec commit already on `main`, so no separate "create branch"
  step is needed before it — just check it out).

---

### Task 1: `dashboard.load_carry_risk()` — move from `app.py`

**Files:**
- Modify: `src/tradefabe/dashboard.py` (add `load_carry_risk()`)
- Modify: `app.py` (remove the function, import it instead, both call sites unchanged)
- Test: `tests/test_dashboard_helpers.py` (new test)

**Interfaces:**
- Produces: `dashboard.load_carry_risk() -> dict | None`, reading
  `state/paper/carry_risk.json` relative to `dashboard.BASE`. Returns `None` if the file
  doesn't exist.

- [ ] **Step 1: Create the branch**

```bash
git checkout main
git pull
git checkout -b feat/dashboard-paper-books-2b
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_dashboard_helpers.py`:

```python
import json
import os

from tradefabe import dashboard


def test_load_carry_risk_returns_none_when_the_file_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    assert dashboard.load_carry_risk() is None


def test_load_carry_risk_reads_the_persisted_report(monkeypatch, tmp_path):
    paper_dir = tmp_path / "state" / "paper"
    paper_dir.mkdir(parents=True)
    report = {"generated_at": "2026-08-13T00:00:00", "coins": {"BTC": {"funding_7d": 0.001}}}
    with open(paper_dir / "carry_risk.json", "w") as fh:
        json.dump(report, fh)
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    assert dashboard.load_carry_risk() == report
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_dashboard_helpers.py -k load_carry_risk -v`
Expected: FAIL with `AttributeError: module 'tradefabe.dashboard' has no attribute
'load_carry_risk'`.

- [ ] **Step 4: Add `load_carry_risk()` to `dashboard.py`**

Add near `load_carry_backtest()` (both are small uncached JSON/CSV loaders for the
carry book):

```python
def load_carry_risk():
    """Deliberately uncached, same reasoning as load_paper_state() -- this is the
    report check_carry_risk() writes once per `tradefabe run` cycle, never fetched live
    from the dashboard itself."""
    path = os.path.join(BASE, "state", "paper", "carry_risk.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)
```

- [ ] **Step 5: Remove the function from `app.py` and import it instead**

In `app.py`, delete the `load_carry_risk()` function definition (currently at line 177,
directly above the `ACCRUAL_ONLY_BOOKS` comment block — leave that comment block in
place, it documents `ACCRUAL_ONLY_BOOKS` itself, not this function).

In the `from tradefabe.dashboard import (...)` block, add `load_carry_risk` to the
alphabetized-by-topic list (next to `load_carry_backtest`):

```python
    load_carry_backtest, load_carry_risk, load_paper_state, load_book_json, ann_stats, fmt,
```

Both existing call sites (`render_carry_risk_panel`'s `risk = load_carry_risk()` and
`render_risk_register`'s `risk_register.build(curve, load_carry_risk())`) need no
changes — same name, now resolved via the import instead of a local definition.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_dashboard_helpers.py -k load_carry_risk -v`
Expected: PASS, both tests.

- [ ] **Step 7: Manual smoke test**

Run: `.venv/bin/streamlit run app.py`, open the carry book (`carry_btc_eth`), confirm
the risk-monitor panel and risk register still render with real numbers. Ctrl+C to stop.

- [ ] **Step 8: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/tradefabe/dashboard.py app.py tests/test_dashboard_helpers.py
git commit -m "$(cat <<'EOF'
dashboard.py: move load_carry_risk() from app.py

Same precedent as every other loader move across sub-projects 1/2a --
src/tradefabe/api/ cannot import from app.py, and 2b's carry-risk API
fields need this reachable from there. Pure extraction, both app.py
call sites unchanged.
EOF
)"
```

---

### Task 2: `GET /api/books/{name}/detail` — positions, deployment, trades for equity books

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Modify: `tests/test_api_book_detail.py`

**Interfaces:**
- Consumes: `dashboard.book_panel_data(..., compute_positions=True)` (Task 1's move
  doesn't touch this; `compute_positions` already exists from sub-project 2a).
- Produces: response body gains, for `kind == "equity"`: `accrual_only: bool`,
  `cost_bps: number | null`, `deployment: {...} | null`,
  `positions: [{ticker, units, last_price, value, weight}] | null`,
  `positions_asof: string | null`, `trades: [{ts, ticker, side, shares, price,
  notional, position_after}]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_api_book_detail.py`, replace `test_2a_excludes_positions_and_deployment`
(2b intentionally reverses this — 2a's exclusion is no longer the contract) with:

```python
def test_equity_book_includes_positions_deployment_trades():
    """The whole point of flipping compute_positions to True for 2b -- these fields
    must now be present (2a's own test asserted the opposite; that was correct for 2a's
    scope and is now stale)."""
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    equity_books = [n for n in psum["book"].tolist()
                    if n != "carry_btc_eth" and n not in dashboard.ACCRUAL_ONLY_BOOKS]
    if not equity_books:
        return  # no plain equity book with real positions in this environment
    name = equity_books[0]
    body = client.get(f"/api/books/{name}/detail").json()
    assert body["accrual_only"] is False
    assert "deployment" in body
    assert "positions" in body
    assert "trades" in body
    assert isinstance(body["trades"], list)  # always a list, never null


def test_accrual_only_equity_book_has_null_deployment_and_positions():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    accrual_books = [n for n in psum["book"].tolist() if n in dashboard.ACCRUAL_ONLY_BOOKS]
    if not accrual_books:
        return  # no accrual-only equity book opened in this environment
    name = accrual_books[0]
    body = client.get(f"/api/books/{name}/detail").json()
    assert body["accrual_only"] is True
    assert body["deployment"] is None
    assert body["positions"] is None
    assert body["trades"] == []


def test_cost_bps_is_present_and_finite():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    body = client.get(f"/api/books/{name}/detail").json()
    assert "cost_bps" in body
    if body["cost_bps"] is not None:
        assert body["cost_bps"] >= 0


def test_positions_response_has_no_nan_token():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    equity_books = [n for n in psum["book"].tolist()
                    if n != "carry_btc_eth" and n not in dashboard.ACCRUAL_ONLY_BOOKS]
    if not equity_books:
        return
    resp = client.get(f"/api/books/{equity_books[0]}/detail")
    assert "NaN" not in resp.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_book_detail.py -k "positions or deployment or accrual or cost_bps" -v`
Expected: FAIL — `KeyError`/`AssertionError`, since these fields don't exist yet (and
the old `test_2a_excludes_positions_and_deployment` you just deleted would have passed,
confirming you're replacing the right contract).

- [ ] **Step 3: Add JSON-safe serialization helpers to `main.py`**

Add near `_stats_json`/`_carry_meta_json`:

```python
def _deployment_json(dep):
    if dep is None:
        return None
    return {
        "cash": _finite_or_none(dep["cash"]), "gross": _finite_or_none(dep["gross"]),
        "net": _finite_or_none(dep["net"]), "equity": _finite_or_none(dep["equity"]),
        "cash_pct": _finite_or_none(dep["cash_pct"]),
        "gross_pct": _finite_or_none(dep["gross_pct"]),
        "net_pct": _finite_or_none(dep["net_pct"]),
        "n_unpriced": int(dep["n_unpriced"]), "n_held": int(dep["n_held"]),
        "priced_at": dep.get("priced_at"),
        "is_short_funded": bool(dep["is_short_funded"]),
    }


def _positions_json(positions_df):
    if positions_df is None:
        return None
    has_weight = "weight" in positions_df.columns
    out = []
    for _, row in positions_df.iterrows():
        out.append({
            "ticker": row["ticker"],
            "units": _finite_or_none(row["units"]),
            "last_price": _finite_or_none(row.get("last_price")),
            "value": _finite_or_none(row.get("value")),
            "weight": _finite_or_none(row.get("weight")) if has_weight else None,
        })
    return out


def _trades_json(trades_df):
    out = []
    for _, row in trades_df.iterrows():
        ts = row["ts"]
        out.append({
            "ts": ts.isoformat() if pd.notna(ts) else None,
            "ticker": row["ticker"] if isinstance(row["ticker"], str) else None,
            "side": row["side"] if isinstance(row["side"], str) else None,
            "shares": _finite_or_none(row["shares"]),
            "price": _finite_or_none(row["price"]),
            "notional": _finite_or_none(row["notional"]),
            "position_after": _finite_or_none(row["position_after"]),
        })
    return out
```

- [ ] **Step 4: Wire the new fields into `book_detail`**

In `book_detail()`, change the `book_panel_data(...)` call's last keyword argument from
`compute_positions=False` to `compute_positions=True` (or drop the keyword entirely,
since `True` is the default — keep it explicit here since this endpoint's whole point
this slice is the positions data).

Then, in the `if data["kind"] == "equity":` branch, add the four new fields after the
existing three:

```python
    if data["kind"] == "equity":
        body["verdict"] = data["verdict"]
        body["corr_bench"] = _finite_or_none(data["corr_bench"])
        body["null_p95"] = _finite_or_none(data["null_p95"])
        body["freq"] = data["freq"]
        body["accrual_only"] = name in dashboard.ACCRUAL_ONLY_BOOKS
        body["cost_bps"] = _finite_or_none(dashboard.signals_cost_bps())
        body["deployment"] = _deployment_json(data["deployment"])
        body["positions"] = _positions_json(data["positions_df"])
        body["positions_asof"] = (
            data["positions_asof"].isoformat()
            if data.get("positions_asof") is not None else None
        )
        body["trades"] = _trades_json(data["trades_df"])
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_book_detail.py -v`
Expected: all pass, including the new ones and the pre-existing ones (`positions_df`
and `trades_df` are always present in `data` regardless of `compute_positions`, per
`book_panel_data()`'s return shape — `trades_df` is unconditional, `positions_df` is
`None` when `compute_positions=False` or the book is accrual-only, which `_positions_json`
already handles by returning `None`).

- [ ] **Step 6: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_book_detail.py
git commit -m "$(cat <<'EOF'
api: GET /api/books/{name}/detail gains positions/deployment/trades

Flips compute_positions to True (was False since 2a, which
deliberately deferred this data) and serializes the resulting
positions_df/deployment/trades_df into JSON-safe fields. Replaces 2a's
own exclusion test with the opposite contract -- 2b's whole point is
turning this data on.
EOF
)"
```

---

### Task 3: `GET /api/books/{name}/detail` — carry-risk and risk-register for the carry book

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Modify: `tests/test_api_book_detail.py`

**Interfaces:**
- Consumes: `dashboard.load_carry_risk()` (Task 1), `risk_register.build(curve,
  risk_json)`.
- Produces: response body gains, for `kind == "carry"`: `book_state: {equity, last_run}
  | null`, `carry_risk: {...} | null`, `risk_register: [{key, title, category,
  likelihood, impact, detail, source, url, measured}]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api_book_detail.py`:

```python
def test_carry_book_includes_risk_fields():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or "carry_btc_eth" not in psum["book"].values:
        return
    body = client.get("/api/books/carry_btc_eth/detail").json()
    assert "book_state" in body
    assert "carry_risk" in body
    assert "risk_register" in body
    assert isinstance(body["risk_register"], list)
    assert len(body["risk_register"]) > 0
    for entry in body["risk_register"]:
        for key in ("key", "title", "category", "likelihood", "impact", "detail", "measured"):
            assert key in entry


def test_carry_risk_survives_a_missing_report(monkeypatch):
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or "carry_btc_eth" not in psum["book"].values:
        return
    monkeypatch.setattr(dashboard, "load_carry_risk", lambda: None)
    resp = client.get("/api/books/carry_btc_eth/detail")
    assert resp.status_code == 200
    assert resp.json()["carry_risk"] is None


def test_carry_book_response_has_no_nan_token():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or "carry_btc_eth" not in psum["book"].values:
        return
    resp = client.get("/api/books/carry_btc_eth/detail")
    assert "NaN" not in resp.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_book_detail.py -k carry_risk_fields -v`
Expected: FAIL — `KeyError: 'book_state'`.

- [ ] **Step 3: Add the recursive NaN-guard and wire `risk_register` import**

At the top of `main.py`, add the import:

```python
from tradefabe import risk_register
```

Add near `_finite_or_none`:

```python
def _deep_finite(obj):
    """Recursively applies _finite_or_none-style NaN-safety through a nested structure
    -- carry_risk.json nests two levels (coins -> BTC/ETH -> postures -> tier). Only a
    genuine float/int leaf that is NaN/inf gets nulled; bool/str/None pass through
    unchanged (bool is checked before the int/float branch since bool is an int
    subclass in Python)."""
    if isinstance(obj, dict):
        return {k: _deep_finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_finite(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float)):
        return _finite_or_none(obj)
    return obj
```

- [ ] **Step 4: Wire the new fields into `book_detail`**

In `book_detail()`'s `else:` branch (the `kind != "equity"` case), add the three new
fields after the existing `carry_meta` one:

```python
    else:
        body["carry_meta"] = _carry_meta_json(data["carry_meta"])
        book_json = data.get("book_json") or {}
        body["book_state"] = {
            "equity": _finite_or_none(book_json.get("equity")),
            "last_run": book_json.get("last_run"),
        }
        curve, _carry_meta_unused = dashboard.load_carry_backtest()
        risk_json = dashboard.load_carry_risk()
        body["carry_risk"] = _deep_finite(risk_json) if risk_json is not None else None
        body["risk_register"] = risk_register.build(curve, risk_json)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_book_detail.py -v`
Expected: all pass.

- [ ] **Step 6: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass. This is the last backend task — the API side of 2b is now complete.

- [ ] **Step 7: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_book_detail.py
git commit -m "$(cat <<'EOF'
api: GET /api/books/{name}/detail gains carry_risk/risk_register/book_state

Completes 2b's backend half. carry_risk.json's nested numeric fields
route through a new recursive NaN-guard (_finite_or_none only handled
flat dicts); risk_register.build()'s entries are already JSON-safe
strings/bools, passed through unchanged.
EOF
)"
```

---

### Task 4: Frontend — extract `lib/format.ts`, shared by `DetailPanel` and the new components

**Files:**
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/lib/format.test.ts`
- Modify: `frontend/src/components/DetailPanel.tsx` (use the extracted `fmt`, drop the
  local copy)

**Interfaces:**
- Produces: `fmt(v: number | null | undefined, kind?: "ratio" | "pct"): string`,
  `money(v: number | null | undefined): string`, `pct(v: number | null | undefined):
  string`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/format.test.ts
import { describe, expect, it } from "vitest";
import { fmt, money, pct } from "./format";

describe("fmt", () => {
  it("formats a ratio to two decimals", () => {
    expect(fmt(0.8)).toBe("0.80");
  });
  it("formats a percent to one decimal", () => {
    expect(fmt(-0.12, "pct")).toBe("-12.0%");
  });
  it("renders an em dash for null/undefined", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(undefined)).toBe("—");
  });
});

describe("money", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(money(103241)).toBe("$103,241");
  });
  it("renders an em dash for null, never $NaN or $-0", () => {
    expect(money(null)).toBe("—");
  });
  it("prefixes the sign before the dollar sign for negative values", () => {
    expect(money(-500)).toBe("-$500");
  });
});

describe("pct", () => {
  it("formats a fraction as a signed percent", () => {
    expect(pct(0.0875)).toBe("+8.8%");
    expect(pct(-0.05)).toBe("-5.0%");
  });
  it("renders an em dash for null", () => {
    expect(pct(null)).toBe("—");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- format.test.ts`
Expected: FAIL — `format.ts` doesn't exist.

- [ ] **Step 3: Write `lib/format.ts`**

```typescript
// Shared numeric formatting for the detail-panel sections -- mirrors
// tradefabe.dashboard's fmt()/money() exactly (same rounding, same em-dash-for-unknown
// convention) so a value never reads differently between the two stacks.

export function fmt(v: number | null | undefined, kind: "ratio" | "pct" = "ratio"): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return kind === "ratio" ? v.toFixed(2) : `${(v * 100).toFixed(1)}%`;
}

export function money(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- format.test.ts`
Expected: PASS, all cases.

- [ ] **Step 5: Update `DetailPanel.tsx` to use the shared module**

Remove the local `fmt` function (currently lines 36-39) and add an import at the top:

```typescript
import { fmt } from "../lib/format";
```

- [ ] **Step 6: Run the frontend suite**

Run: `cd frontend && npm test`
Expected: all pass, including `DetailPanel.test.tsx` unchanged (same `fmt` behavior,
just relocated).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/format.ts frontend/src/lib/format.test.ts frontend/src/components/DetailPanel.tsx
git commit -m "$(cat <<'EOF'
frontend: extract lib/format.ts (fmt/money/pct), shared by 2b's new components

DetailPanel.tsx had a local fmt() only it used; 2b's five new sections
all need the same money/pct formatting dashboard.py already defines
server-side, so this gives the frontend one place for it instead of
each new component reimplementing its own.
EOF
)"
```

---

### Task 5: Frontend — `DeploymentStats` and `PositionsTable` components

**Files:**
- Create: `frontend/src/components/DeploymentStats.tsx`
- Create: `frontend/src/components/DeploymentStats.test.tsx`
- Create: `frontend/src/components/PositionsTable.tsx`
- Create: `frontend/src/components/PositionsTable.test.tsx`

**Interfaces:**
- Consumes: the `deployment`/`positions`/`positions_asof` shapes Task 2 added to the
  API response.
- Produces: `<DeploymentStats deployment={...} />`,
  `<PositionsTable positions={...} positionsAsof={...} />` — both pure, props-only
  components (no fetch, no state), composed by `DetailPanel` in Task 9.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/components/DeploymentStats.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DeploymentStats from "./DeploymentStats";

const DEPLOYMENT = {
  cash: 20000, gross: 90000, net: 80000, equity: 100000,
  cash_pct: 0.2, gross_pct: 0.9, net_pct: 0.8,
  n_unpriced: 0, n_held: 3, priced_at: "2026-08-12", is_short_funded: false,
};

describe("DeploymentStats", () => {
  it("renders the four capital-deployed figures", () => {
    render(<DeploymentStats deployment={DEPLOYMENT} />);
    expect(screen.getByText("$20,000")).toBeInTheDocument(); // cash
    expect(screen.getByText("$90,000")).toBeInTheDocument(); // gross
    expect(screen.getByText("$80,000")).toBeInTheDocument(); // net
    expect(screen.getByText("$100,000")).toBeInTheDocument(); // equity
  });

  it("shows the vol-targeting caption when not short-funded", () => {
    render(<DeploymentStats deployment={DEPLOYMENT} />);
    expect(screen.getByText(/Vol-targeted sizing/)).toBeInTheDocument();
  });

  it("shows the short-funded caption instead when is_short_funded is true", () => {
    render(<DeploymentStats deployment={{ ...DEPLOYMENT, is_short_funded: true, net: -10000 }} />);
    expect(screen.getByText(/net short/)).toBeInTheDocument();
    expect(screen.queryByText(/Vol-targeted sizing/)).not.toBeInTheDocument();
  });

  it("warns when some positions could not be priced", () => {
    render(<DeploymentStats deployment={{ ...DEPLOYMENT, n_unpriced: 2, n_held: 3 }} />);
    expect(screen.getByText(/2 of 3 held position/)).toBeInTheDocument();
  });

  it("does not warn when everything is priced", () => {
    render(<DeploymentStats deployment={DEPLOYMENT} />);
    expect(screen.queryByText(/could not be priced/)).not.toBeInTheDocument();
  });
});
```

```typescript
// frontend/src/components/PositionsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PositionsTable from "./PositionsTable";

const POSITIONS = [
  { ticker: "SPY", units: 12.5, last_price: 450.2, value: 5627.5, weight: 0.056 },
  { ticker: "IEF", units: -8.0, last_price: 95.1, value: -760.8, weight: -0.008 },
];

describe("PositionsTable", () => {
  it("renders one row per position with ticker, units, price, value, weight", () => {
    render(<PositionsTable positions={POSITIONS} positionsAsof="2026-08-12" />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("IEF")).toBeInTheDocument();
    expect(screen.getByText("$5,628")).toBeInTheDocument();
  });

  it("shows an em dash for an unpriced position rather than $NaN", () => {
    render(
      <PositionsTable
        positions={[{ ticker: "XYZ", units: 5, last_price: null, value: null, weight: null }]}
        positionsAsof="2026-08-12"
      />
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows an empty-state caption when there are no positions", () => {
    render(<PositionsTable positions={[]} positionsAsof="2026-08-12" />);
    expect(screen.getByText(/No open positions/)).toBeInTheDocument();
  });

  it("shows an empty-state caption when positions is null", () => {
    render(<PositionsTable positions={null} positionsAsof={null} />);
    expect(screen.getByText(/No open positions/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- DeploymentStats.test.tsx PositionsTable.test.tsx`
Expected: FAIL — both components don't exist yet.

- [ ] **Step 3: Write `DeploymentStats.tsx`**

```tsx
import StatTile from "./StatTile";
import { fmt, money } from "../lib/format";

type Deployment = {
  cash: number | null; gross: number | null; net: number | null; equity: number | null;
  cash_pct: number | null; gross_pct: number | null; net_pct: number | null;
  n_unpriced: number; n_held: number; priced_at: string | null; is_short_funded: boolean;
};

export default function DeploymentStats({ deployment }: { deployment: Deployment }) {
  const d = deployment;
  return (
    <div>
      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Cash (undeployed)" value={`${money(d.cash)} · ${fmt(d.cash_pct, "pct")}`} />
        <StatTile label="Gross exposure" value={`${money(d.gross)} · ${fmt(d.gross_pct, "pct")}`} />
        <StatTile label="Net exposure" value={`${money(d.net)} · ${fmt(d.net_pct, "pct")}`} />
        <StatTile label="Total equity" value={money(d.equity)} />
      </div>
      {d.n_unpriced > 0 && (
        <p className="text-xs text-amber-400 mt-2">
          {d.n_unpriced} of {d.n_held} held position(s) could not be priced, so the
          figures above are incomplete. This is shown rather than silently summed to
          $0 — an unpriceable book is not an empty one.
        </p>
      )}
      <p className="text-xs text-ink-muted mt-2">
        Gross = sum of |position value| (both legs of a long/short book); net = long
        minus short (directional tilt).{" "}
        {d.is_short_funded ? (
          <>
            <strong className="text-ink">Cash exceeds equity because this book is net
            short</strong> — the short proceeds are cash. Nothing is borrowed and
            nothing is wrong.
          </>
        ) : (
          "Vol-targeted sizing deliberately leaves room in cash rather than forcing " +
          "100% deployment — that's a feature of the sizing, not a bug."
        )}
        {d.priced_at && ` Priced from the ledger's own marks as of ${d.priced_at} UTC.`}
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Write `PositionsTable.tsx`**

```tsx
import { fmt, money } from "../lib/format";

type Position = {
  ticker: string; units: number | null; last_price: number | null;
  value: number | null; weight: number | null;
};

export default function PositionsTable({
  positions, positionsAsof,
}: {
  positions: Position[] | null;
  positionsAsof: string | null;
}) {
  if (!positions || positions.length === 0) {
    return <p className="text-ink-muted text-sm">No open positions (book hasn't rebalanced yet).</p>;
  }
  return (
    <div>
      <table className="w-full text-sm font-mono tabular-nums">
        <thead>
          <tr className="text-ink-muted text-xs uppercase text-left">
            <th className="pb-2">Ticker</th>
            <th className="pb-2 text-right">Units</th>
            <th className="pb-2 text-right">Last price</th>
            <th className="pb-2 text-right">Value</th>
            <th className="pb-2 text-right">Weight</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.ticker} className="border-t border-white/5">
              <td className="py-1.5 font-sans">{p.ticker}</td>
              <td className="py-1.5 text-right">{p.units?.toFixed(2) ?? "—"}</td>
              <td className="py-1.5 text-right">{p.last_price !== null ? money(p.last_price) : "—"}</td>
              <td className="py-1.5 text-right">{money(p.value)}</td>
              <td className="py-1.5 text-right">{fmt(p.weight, "pct")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-muted mt-2">
        Priced as of the cached data date ({positionsAsof ?? "unknown"}), not a live
        quote. Weight is % of TOTAL equity (cash + positions), not % of invested value
        — it no longer always sums to 100%.
      </p>
    </div>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- DeploymentStats.test.tsx PositionsTable.test.tsx`
Expected: PASS, all cases.

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/DeploymentStats.tsx frontend/src/components/DeploymentStats.test.tsx \
        frontend/src/components/PositionsTable.tsx frontend/src/components/PositionsTable.test.tsx
git commit -m "$(cat <<'EOF'
frontend: DeploymentStats and PositionsTable components

Pure, props-only ports of render_strategy_panel's "Capital deployed"
stat row and current-positions table -- not wired into DetailPanel
yet (Task 9).
EOF
)"
```

---

### Task 6: Frontend — `TradeLog` component

**Files:**
- Create: `frontend/src/components/TradeLog.tsx`
- Create: `frontend/src/components/TradeLog.test.tsx`

**Interfaces:**
- Consumes: `trades`/`accrual_only`/`cost_bps` fields from Task 2's API response.
- Produces: `<TradeLog trades={...} accrualOnly={...} costBps={...} />`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/TradeLog.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TradeLog from "./TradeLog";

const TRADES = [
  {
    ts: "2026-08-12T14:30:00", ticker: "SPY", side: "BUY", shares: 5.2,
    price: 450.2, notional: 2341.04, position_after: 12.5,
  },
];

describe("TradeLog", () => {
  it("renders one row per fill", () => {
    render(<TradeLog trades={TRADES} accrualOnly={false} costBps={5} />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(screen.getByText(/1 fill/)).toBeInTheDocument();
  });

  it("shows the accrual-only caption instead of an empty-log message", () => {
    render(<TradeLog trades={[]} accrualOnly={true} costBps={null} />);
    expect(screen.getByText(/delta-neutral carry/)).toBeInTheDocument();
  });

  it("shows the not-yet-filled caption for a non-accrual book with no trades", () => {
    render(<TradeLog trades={[]} accrualOnly={false} costBps={5} />);
    expect(screen.getByText(/No fills recorded yet/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- TradeLog.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Write `TradeLog.tsx`**

```tsx
import { money } from "../lib/format";

type Trade = {
  ts: string | null; ticker: string | null; side: string | null;
  shares: number | null; price: number | null; notional: number | null;
  position_after: number | null;
};

export default function TradeLog({
  trades, accrualOnly, costBps,
}: {
  trades: Trade[];
  accrualOnly: boolean;
  costBps: number | null;
}) {
  if (accrualOnly) {
    return (
      <p className="text-ink-muted text-sm">
        This book is delta-neutral carry: its value moves from funding accrual, not
        discrete trades, so no fill log ever applies here — not an empty log waiting
        to fill, a different economics entirely.
      </p>
    );
  }
  if (trades.length === 0) {
    return (
      <p className="text-ink-muted text-sm">
        No fills recorded yet. The log starts at this book's next rebalance — earlier
        trades happened before the ledger recorded them and cannot be reconstructed,
        since only the resulting position was kept.
      </p>
    );
  }
  const lastTs = trades[0]?.ts;
  return (
    <div>
      <table className="w-full text-sm font-mono tabular-nums">
        <thead>
          <tr className="text-ink-muted text-xs uppercase text-left">
            <th className="pb-2">When (UTC)</th>
            <th className="pb-2 font-sans">Ticker</th>
            <th className="pb-2 font-sans">Side</th>
            <th className="pb-2 text-right">Δ units</th>
            <th className="pb-2 text-right">Fill price</th>
            <th className="pb-2 text-right">Notional</th>
            <th className="pb-2 text-right">Position after</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-t border-white/5">
              <td className="py-1.5">{t.ts ? t.ts.replace("T", " ").slice(0, 16) : "—"}</td>
              <td className="py-1.5 font-sans">{t.ticker ?? "—"}</td>
              <td className="py-1.5 font-sans">{t.side ?? "—"}</td>
              <td className="py-1.5 text-right">
                {t.shares !== null ? `${t.shares >= 0 ? "+" : ""}${t.shares.toFixed(2)}` : "—"}
              </td>
              <td className="py-1.5 text-right">{t.price !== null ? money(t.price) : "—"}</td>
              <td className="py-1.5 text-right">{money(t.notional)}</td>
              <td className="py-1.5 text-right">{t.position_after?.toFixed(2) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-muted mt-2">
        {trades.length} fill(s), newest first; last {lastTs ? lastTs.replace("T", " ").slice(0, 16) : "—"} UTC.
        Sides are named from the POSITION's view, not the order's: BUY/SELL open or
        grow a long, SHORT/COVER open or reduce a short. Simulated fills at the mark
        close with a {costBps !== null ? costBps.toFixed(0) : "—"}bp per-side cost,
        capped at the most recent 500.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- TradeLog.test.tsx`
Expected: PASS, all three cases.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/TradeLog.tsx frontend/src/components/TradeLog.test.tsx
git commit -m "$(cat <<'EOF'
frontend: TradeLog component

Port of render_trade_log() -- three states (accrual-only caption,
empty-log caption, populated table), not wired into DetailPanel yet
(Task 9).
EOF
)"
```

---

### Task 7: Frontend — `CarryRiskPanel` component

**Files:**
- Create: `frontend/src/components/CarryRiskPanel.tsx`
- Create: `frontend/src/components/CarryRiskPanel.test.tsx`

**Interfaces:**
- Consumes: the `carry_risk` field from Task 3's API response.
- Produces: `<CarryRiskPanel risk={...} />`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/CarryRiskPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CarryRiskPanel from "./CarryRiskPanel";

const RISK = {
  generated_at: "2026-08-13T04:19:37", funding_window_days: 7,
  coins: {
    BTC: {
      funding_7d: 0.0011, funding_flip_alert: false, max_leverage: 40, maint_margin: 0.0125,
      postures: {
        "10%": { leverage: 4, liq_distance: 0.2375 },
        "25%": { leverage: 10, liq_distance: 0.0875 },
        "50%": { leverage: 20, liq_distance: 0.0375 },
        "100%": { leverage: 40, liq_distance: 0.0125 },
      },
    },
    ETH: {
      funding_7d: -0.0005, funding_flip_alert: true, max_leverage: 25, maint_margin: 0.02,
      postures: {
        "10%": { leverage: 2.5, liq_distance: 0.38 },
        "25%": { leverage: 6.25, liq_distance: 0.14 },
        "50%": { leverage: 12.5, liq_distance: 0.06 },
        "100%": { leverage: 25, liq_distance: 0.02 },
      },
    },
  },
  blended_funding_7d: 0.0003, blended_funding_flip_alert: false,
  headline_leverage_fraction: 0.25, liq_distance_warn: 0.25,
  high_risk_alert: { BTC: false, ETH: true },
};

describe("CarryRiskPanel", () => {
  it("shows an empty-state caption when risk is null", () => {
    render(<CarryRiskPanel risk={null} />);
    expect(screen.getByText(/No risk report yet/)).toBeInTheDocument();
  });

  it("renders both coins' 7d funding", () => {
    render(<CarryRiskPanel risk={RISK} />);
    expect(screen.getByText("+0.1%")).toBeInTheDocument(); // BTC
    expect(screen.getByText("-0.1%")).toBeInTheDocument(); // ETH, rounds to -0.1%
  });

  it("shows a funding-flip badge only for the coin that flipped", () => {
    render(<CarryRiskPanel risk={RISK} />);
    expect(screen.getAllByText("funding flip")).toHaveLength(1);
  });

  it("shows the high-risk warning naming only the flagged coin", () => {
    render(<CarryRiskPanel risk={RISK} />);
    expect(screen.getByText(/High risk/)).toBeInTheDocument();
    expect(screen.getByText(/ETH/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- CarryRiskPanel.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Write `CarryRiskPanel.tsx`**

```tsx
import { pct } from "../lib/format";

type Posture = { leverage: number; liq_distance: number };
type CoinRisk = {
  funding_7d: number | null; funding_flip_alert: boolean;
  max_leverage: number | null; maint_margin: number | null;
  postures: Record<string, Posture>;
};
type CarryRisk = {
  generated_at: string; funding_window_days: number;
  coins: { BTC: CoinRisk; ETH: CoinRisk };
  blended_funding_7d: number | null; blended_funding_flip_alert: boolean;
  headline_leverage_fraction: number; liq_distance_warn: number;
  high_risk_alert: { BTC: boolean; ETH: boolean };
};

const TIERS = ["10%", "25%", "50%", "100%"];

export default function CarryRiskPanel({ risk }: { risk: CarryRisk | null }) {
  if (!risk) {
    return (
      <p className="text-ink-muted text-sm">
        No risk report yet — generated automatically by `tradefabe run`.
      </p>
    );
  }
  const flagged = (["BTC", "ETH"] as const).filter((c) => risk.high_risk_alert[c]);
  return (
    <div>
      <p className="text-xs text-ink-muted font-mono">
        As of {risk.generated_at} · trailing {risk.funding_window_days}d funding
      </p>
      <div className="grid grid-cols-2 gap-4 mt-2">
        {(["BTC", "ETH"] as const).map((coin) => (
          <div key={coin}>
            <div className="text-xs text-ink-muted uppercase">{coin} 7d funding</div>
            <div className="text-xl text-ink font-mono tabular-nums">
              {pct(risk.coins[coin].funding_7d)}
            </div>
            {risk.coins[coin].funding_flip_alert && (
              <span className="text-xs text-amber-400 font-mono">funding flip</span>
            )}
          </div>
        ))}
      </div>
      {risk.blended_funding_flip_alert && (
        <p className="text-sm text-amber-400 mt-3">
          Blended 7d funding has turned negative — bear-regime bleed. The book loses
          money net of the fee drag until this flips back.
        </p>
      )}
      <table className="w-full text-sm font-mono tabular-nums mt-4">
        <thead>
          <tr className="text-ink-muted text-xs uppercase text-left">
            <th className="pb-2 font-sans">Posture</th>
            <th className="pb-2 text-right">BTC leverage</th>
            <th className="pb-2 text-right">BTC liq distance</th>
            <th className="pb-2 text-right">ETH leverage</th>
            <th className="pb-2 text-right">ETH liq distance</th>
          </tr>
        </thead>
        <tbody>
          {TIERS.map((tier) => {
            const btc = risk.coins.BTC.postures[tier];
            const eth = risk.coins.ETH.postures[tier];
            return (
              <tr key={tier} className="border-t border-white/5">
                <td className="py-1.5 font-sans">{tier}</td>
                <td className="py-1.5 text-right">{btc ? `${btc.leverage.toFixed(1)}x` : "—"}</td>
                <td className="py-1.5 text-right">{btc ? pct(btc.liq_distance) : "—"}</td>
                <td className="py-1.5 text-right">{eth ? `${eth.leverage.toFixed(1)}x` : "—"}</td>
                <td className="py-1.5 text-right">{eth ? pct(eth.liq_distance) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {flagged.length > 0 && (
        <p className="text-sm text-red-400 mt-3">
          High risk: at {(risk.headline_leverage_fraction * 100).toFixed(0)}% of
          Hyperliquid's live max leverage, <strong>{flagged.join(", ")}</strong>{" "}
          liquidation distance is under the{" "}
          {(risk.liq_distance_warn * 100).toFixed(0)}% pump-cushion threshold.
        </p>
      )}
      <p className="text-xs text-ink-muted mt-3">
        Postures are % of Hyperliquid's live max leverage per coin, not what this
        paper book actually holds — the book models pure funding yield with no
        leverage. This is a what-if overlay: if an operator ran the short leg at that
        leverage, how far could price pump before liquidation.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- CarryRiskPanel.test.tsx`
Expected: PASS. (If the `+0.1%`/`-0.1%` rounding doesn't match `pct()`'s
one-decimal format exactly, adjust the test's expected string to whatever `pct(0.0011)`
actually produces — `+0.1%` — rather than the component.)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/CarryRiskPanel.tsx frontend/src/components/CarryRiskPanel.test.tsx
git commit -m "$(cat <<'EOF'
frontend: CarryRiskPanel component

Port of render_carry_risk_panel() -- funding/flip badges per coin,
leverage/liq-distance posture table, high-risk warning. Not wired
into DetailPanel yet (Task 9).
EOF
)"
```

---

### Task 8: Frontend — `RiskRegister` component

**Files:**
- Create: `frontend/src/components/RiskRegister.tsx`
- Create: `frontend/src/components/RiskRegister.test.tsx`

**Interfaces:**
- Consumes: the `risk_register` field from Task 3's API response.
- Produces: `<RiskRegister entries={...} />`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/RiskRegister.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import RiskRegister from "./RiskRegister";

const ENTRIES = [
  {
    key: "venue_failure", title: "Venue failure", category: "total loss",
    likelihood: "45% of 40 exchanges failed.", impact: "Total loss of posted margin.",
    detail: "Two independent samples agree.", source: "Moore & Christin (FC 2013)",
    url: "https://example.com/paper", measured: false,
  },
  {
    key: "operational", title: "Operational / data bugs", category: "operational",
    likelihood: "Several realised, all caught.", impact: "Wrong or stale numbers.",
    detail: "Realised examples in CLAUDE.md.", source: null, url: null, measured: true,
  },
];

describe("RiskRegister", () => {
  it("renders one collapsed entry per row, titles visible", () => {
    render(<RiskRegister entries={ENTRIES} />);
    expect(screen.getByText("Venue failure")).toBeInTheDocument();
    expect(screen.getByText("Operational / data bugs")).toBeInTheDocument();
    expect(screen.queryByText(/Two independent samples/)).not.toBeInTheDocument();
  });

  it("reveals likelihood/impact/detail when an entry is opened", async () => {
    render(<RiskRegister entries={ENTRIES} />);
    await userEvent.click(screen.getByText("Venue failure"));
    expect(screen.getByText(/Two independent samples/)).toBeInTheDocument();
    expect(screen.getByText(/45% of 40 exchanges/)).toBeInTheDocument();
  });

  it("shows a cited badge with a source link when a source is present", async () => {
    render(<RiskRegister entries={ENTRIES} />);
    await userEvent.click(screen.getByText("Venue failure"));
    expect(screen.getByText("cited")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Moore & Christin/ })).toHaveAttribute(
      "href", "https://example.com/paper"
    );
  });

  it("shows a measured badge and no source link when source is null", async () => {
    render(<RiskRegister entries={ENTRIES} />);
    await userEvent.click(screen.getByText("Operational / data bugs"));
    expect(screen.getByText("measured")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- RiskRegister.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Write `RiskRegister.tsx`**

```tsx
type Entry = {
  key: string; title: string; category: string; likelihood: string; impact: string;
  detail: string; source: string | null; url: string | null; measured: boolean;
};

const SEVERITY_COLOR: Record<string, string> = {
  "total loss": "text-red-400", severe: "text-amber-400",
  moderate: "text-amber-400", operational: "text-ink-muted",
};

export default function RiskRegister({ entries }: { entries: Entry[] }) {
  return (
    <div>
      {entries.map((r) => (
        <details key={r.key} className="border-t border-white/5 py-3">
          <summary className="text-sm text-ink cursor-pointer">{r.title}</summary>
          <div className="mt-2 text-xs font-mono">
            <span className={SEVERITY_COLOR[r.category] ?? "text-ink-muted"}>{r.category}</span>
            {" · "}
            <span className={r.measured ? "text-accent" : "text-ink-muted"}>
              {r.measured ? "measured" : "cited"}
            </span>
          </div>
          <p className="text-sm text-ink mt-2"><strong>How often:</strong> {r.likelihood}</p>
          <p className="text-sm text-ink mt-1"><strong>If it happens:</strong> {r.impact}</p>
          <p className="text-xs text-ink-muted mt-2">{r.detail}</p>
          {r.source && (
            <p className="text-xs text-ink-muted mt-2">
              Source:{" "}
              {r.url ? (
                <a href={r.url} className="underline" target="_blank" rel="noreferrer">
                  {r.source}
                </a>
              ) : (
                r.source
              )}
            </p>
          )}
        </details>
      ))}
      <p className="text-xs text-ink-muted mt-3">
        Cited entries carry a real source; measured entries are computed from this
        lab's own data. Neither is a forecast — a base rate is what happened to a
        population, not a probability for this book. Absence of a bad case in a
        sample is not evidence one cannot occur.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- RiskRegister.test.tsx`
Expected: PASS, all four cases.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/RiskRegister.tsx frontend/src/components/RiskRegister.test.tsx
git commit -m "$(cat <<'EOF'
frontend: RiskRegister component

Port of render_risk_register() -- one <details> expander per entry
(same pattern DetailPanel's backtest-history section already uses),
severity + measured/cited badges. Not wired into DetailPanel yet
(Task 9).
EOF
)"
```

---

### Task 9: Wire everything into `DetailPanel.tsx`

**Files:**
- Modify: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/src/components/DetailPanel.test.tsx`

**Interfaces:**
- Consumes: `DeploymentStats`, `PositionsTable`, `TradeLog`, `CarryRiskPanel`,
  `RiskRegister` (Tasks 5-8); the full response shape from Tasks 2-3.

- [ ] **Step 1: Write the failing tests**

Add to `DetailPanel.test.tsx`, extending the shared `DETAIL_RESPONSE` fixture per test
(rather than mutating the module-level constant, to keep tests independent):

```tsx
it("renders capital-deployed stats, positions, and trade log for an equity book", async () => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          ...DETAIL_RESPONSE,
          accrual_only: false,
          cost_bps: 5,
          deployment: {
            cash: 20000, gross: 90000, net: 80000, equity: 100000,
            cash_pct: 0.2, gross_pct: 0.9, net_pct: 0.8,
            n_unpriced: 0, n_held: 1, priced_at: "2026-08-12", is_short_funded: false,
          },
          positions: [{ ticker: "SPY", units: 10, last_price: 450, value: 4500, weight: 0.045 }],
          positions_asof: "2026-08-12",
          trades: [],
        }),
    })
  ) as unknown as typeof fetch;
  render(<DetailPanel name="tsmom_12m" />);
  await waitFor(() => expect(screen.getByText("$100,000")).toBeInTheDocument());
  expect(screen.getByText("SPY")).toBeInTheDocument();
  expect(screen.getByText(/No fills recorded yet/)).toBeInTheDocument();
});

it("shows the accrual-only caption instead of deployment/positions for a delta-neutral equity book", async () => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          ...DETAIL_RESPONSE,
          accrual_only: true, cost_bps: null, deployment: null, positions: null,
          positions_asof: null, trades: [],
        }),
    })
  ) as unknown as typeof fetch;
  render(<DetailPanel name="tsmom_12m" />);
  await waitFor(() =>
    expect(screen.getByText(/no cash\/gross\/net breakdown/)).toBeInTheDocument()
  );
});

it("renders the risk-monitor panel and risk register for the carry book", async () => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          ...DETAIL_RESPONSE,
          kind: "carry",
          carry_meta: { net_yield: 0.12, pct_days_positive: 0.87 },
          book_state: { equity: 105000, last_run: "2026-08-12" },
          carry_risk: {
            generated_at: "2026-08-13T00:00:00", funding_window_days: 7,
            coins: {
              BTC: { funding_7d: 0.001, funding_flip_alert: false, max_leverage: 40,
                     maint_margin: 0.0125, postures: {} },
              ETH: { funding_7d: 0.001, funding_flip_alert: false, max_leverage: 25,
                     maint_margin: 0.02, postures: {} },
            },
            blended_funding_7d: 0.001, blended_funding_flip_alert: false,
            headline_leverage_fraction: 0.25, liq_distance_warn: 0.25,
            high_risk_alert: { BTC: false, ETH: false },
          },
          risk_register: [
            { key: "op", title: "Operational / data bugs", category: "operational",
              likelihood: "Several.", impact: "Wrong numbers.", detail: "See CLAUDE.md.",
              source: null, url: null, measured: true },
          ],
        }),
    })
  ) as unknown as typeof fetch;
  render(<DetailPanel name="carry_btc_eth" />);
  await waitFor(() => expect(screen.getByText("Operational / data bugs")).toBeInTheDocument());
  expect(screen.getByText(/trailing 7d funding/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- DetailPanel.test.tsx`
Expected: FAIL — the new sections aren't rendered yet, so the new assertions can't find
their text (existing tests in this file still pass, since `DETAIL_RESPONSE`'s shape is
additive).

- [ ] **Step 3: Extend the `DetailResponse` type and add the imports**

In `DetailPanel.tsx`, add the new imports:

```tsx
import DeploymentStats from "./DeploymentStats";
import PositionsTable from "./PositionsTable";
import TradeLog from "./TradeLog";
import CarryRiskPanel from "./CarryRiskPanel";
import RiskRegister from "./RiskRegister";
```

Extend the `DetailResponse` type with the fields Tasks 2-3 added:

```tsx
type DetailResponse = {
  // ...existing fields unchanged...
  accrual_only?: boolean;
  cost_bps?: number | null;
  deployment?: {
    cash: number | null; gross: number | null; net: number | null; equity: number | null;
    cash_pct: number | null; gross_pct: number | null; net_pct: number | null;
    n_unpriced: number; n_held: number; priced_at: string | null; is_short_funded: boolean;
  } | null;
  positions?: {
    ticker: string; units: number | null; last_price: number | null;
    value: number | null; weight: number | null;
  }[] | null;
  positions_asof?: string | null;
  trades?: {
    ts: string | null; ticker: string | null; side: string | null; shares: number | null;
    price: number | null; notional: number | null; position_after: number | null;
  }[];
  book_state?: { equity: number | null; last_run: string | null } | null;
  carry_risk?: Parameters<typeof CarryRiskPanel>[0]["risk"];
  risk_register?: Parameters<typeof RiskRegister>[0]["entries"];
};
```

- [ ] **Step 4: Add the new section after the existing backtest-history `<details>` block**

Immediately after the closing `</details>` of the backtest-history section (the last
thing currently in the component, right before the final `</motion.div>`), add:

```tsx
      <div className="mt-6 pt-6 border-t border-white/5">
        {data.kind === "equity" ? (
          data.accrual_only ? (
            <p className="text-ink-muted text-sm">
              This book is delta-neutral carry: its value moves from funding accrual,
              not discrete positions, so there's no cash/gross/net breakdown to show
              here — the live equity chart above is the real number.
            </p>
          ) : (
            <>
              <SectionHeader>Capital deployed</SectionHeader>
              <div className="mt-3">
                <DeploymentStats deployment={data.deployment!} />
              </div>
              <div className="mt-6">
                <SectionHeader>Current positions</SectionHeader>
                <div className="mt-3">
                  <PositionsTable positions={data.positions ?? null} positionsAsof={data.positions_asof ?? null} />
                </div>
              </div>
            </>
          )
        ) : null}

        {data.kind === "equity" && (
          <div className="mt-6 pt-6 border-t border-white/5">
            <SectionHeader>Trade log</SectionHeader>
            <div className="mt-3">
              <TradeLog
                trades={data.trades ?? []}
                accrualOnly={data.accrual_only ?? false}
                costBps={data.cost_bps ?? null}
              />
            </div>
          </div>
        )}

        {data.kind === "carry" && (
          <>
            <SectionHeader>Book state</SectionHeader>
            <p className="text-sm text-ink mt-2">
              Equity <strong className="font-mono">{money(data.book_state?.equity ?? null)}</strong>
              {" · "}last run <strong className="font-mono">{data.book_state?.last_run ?? "—"}</strong>
            </p>

            <div className="mt-6 pt-6 border-t border-white/5">
              <SectionHeader>Risk monitor — funding-flip alert + short-leg liquidation distance</SectionHeader>
              <div className="mt-3">
                <CarryRiskPanel risk={data.carry_risk ?? null} />
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-white/5">
              <SectionHeader>Risk register — what the ~12%/yr is actually paying for</SectionHeader>
              <div className="mt-3">
                <RiskRegister entries={data.risk_register ?? []} />
              </div>
            </div>
          </>
        )}
      </div>
```

This uses `money`, which isn't imported yet — add it to the existing `import { fmt }
from "../lib/format";` line from Task 4:

```tsx
import { fmt, money } from "../lib/format";
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- DetailPanel.test.tsx`
Expected: all pass, including every pre-existing test in the file (the new block is
additive and sits after everything those tests assert on).

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 7: Manual full-stack smoke test**

Terminal 1: `.venv/bin/tradefabe-api`
Terminal 2: `cd frontend && npm run dev`

Open `http://localhost:5173`, navigate to Paper Books:
- Select an equity book with real positions — confirm the capital-deployed stats,
  positions table, and trade log all render with real numbers.
- Select an accrual-only equity book (e.g. `funding_timing_1h` or `carry_kronos_vol`,
  if live) — confirm the delta-neutral caption replaces the deployment/positions
  sections, and the trade log shows its own accrual-only caption.
- Select `carry_btc_eth` — confirm the book-state line, risk-monitor panel (funding
  numbers matching `state/paper/carry_risk.json`), and risk register (expand at least
  two entries) all render correctly.
- Confirm no console errors and no `NaN`/`undefined` visible anywhere in the new
  sections.

Stop both servers (Ctrl+C in each terminal) once confirmed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/DetailPanel.tsx frontend/src/components/DetailPanel.test.tsx
git commit -m "$(cat <<'EOF'
frontend: wire DeploymentStats/PositionsTable/TradeLog/CarryRiskPanel/
RiskRegister into DetailPanel

Completes 2b -- the detail panel now has full functional parity with
app.py's render_strategy_panel across both equity and carry book
kinds. DetailPanel itself stays a thin composer: the kind-branch here
is the only new logic it owns, all rendering detail lives in the five
components from Tasks 5-8.
EOF
)"
```

---

### Task 10: Open the PR

**Files:** none (process step)

- [ ] **Step 1: File the GitHub issue**

```bash
gh issue create --title "Dashboard rebuild, sub-project 2b: positions, trade log, carry risk" \
  --body-file - <<'EOF'
Sub-project 2b of the dashboard rebuild (React/FastAPI off Streamlit) -- the piece 2a
(#206, #209-#211) explicitly deferred: "Positions/trade-log/carry-risk-panel are
explicitly out of scope -- slice 2b."

Full spec: `docs/superpowers/specs/2026-08-13-dashboard-paper-books-2b-design.md`.

**Scope:** capital-deployed stats, positions table, and trade log for equity books;
risk-monitor panel and risk register for the carry book. Full functional parity with
`app.py`'s existing Streamlit rendering -- a port, not a redesign.

**Out of scope:** Research Lab view (sub-project 3), any change to `state/`,
`engine.py`, or doctrine logic.
EOF
```

Note the issue number printed by this command for the next step.

- [ ] **Step 2: Push the branch and open the PR**

```bash
git push -u origin feat/dashboard-paper-books-2b
gh pr create --title "Dashboard rebuild, sub-project 2b: positions, trade log, carry risk" \
  --body-file - <<'EOF'
Closes #<issue-number-from-step-1>.

## Summary
- `dashboard.load_carry_risk()` moved from `app.py` (same precedent as every prior
  loader move).
- `GET /api/books/{name}/detail` flips `compute_positions` to `True` and gains, for
  equity books: `accrual_only`, `cost_bps`, `deployment`, `positions`,
  `positions_asof`, `trades`; for the carry book: `book_state`, `carry_risk`
  (through a new recursive NaN-guard), `risk_register`.
- New frontend components: `DeploymentStats`, `PositionsTable`, `TradeLog`,
  `CarryRiskPanel`, `RiskRegister` -- pure, props-only ports of `app.py`'s
  `render_strategy_panel`/`render_trade_log`/`render_carry_risk_panel`/
  `render_risk_register`, wired into `DetailPanel` via one `kind`-branched block.
- New `frontend/src/lib/format.ts` (`fmt`/`money`/`pct`), extracted from
  `DetailPanel`'s previously-local `fmt` and shared by all five new components.

Spec: `docs/superpowers/specs/2026-08-13-dashboard-paper-books-2b-design.md`
Plan: `docs/superpowers/plans/2026-08-13-dashboard-paper-books-2b.md`

## Test plan
- [ ] `.venv/bin/pytest tests/ -n0` -- full backend suite green
- [ ] `cd frontend && npm test` -- full frontend suite green
- [ ] `.venv/bin/streamlit run app.py` -- both views still load, unchanged behavior
- [ ] `.venv/bin/tradefabe-api` + `cd frontend && npm run dev` -- manual walkthrough per
      Task 9 Step 7 of the plan (equity book with positions, accrual-only equity book,
      carry book's risk monitor + risk register)
EOF
```

- [ ] **Step 3: Wait for CI, then merge**

Run: `gh pr checks <PR-number> --watch`

Once green, verify the head SHA matches:
```bash
gh pr view <PR-number> --json headRefOid -q .headRefOid
git rev-parse HEAD
```

Then, per CLAUDE.md's documented sequence (never chain the branch delete onto the merge
command):
```bash
gh pr merge <PR-number> --squash
gh pr view <PR-number> --json state,mergedAt   # must print MERGED before anything below
```

Once `state` prints `MERGED` as its own step:
```bash
git checkout main
git pull
git branch -D feat/dashboard-paper-books-2b
git push origin --delete feat/dashboard-paper-books-2b
```

- [ ] **Step 4: Confirm the issue closed**

```bash
gh issue view <issue-number> --json state -q .state
```
Expected: `CLOSED`.
