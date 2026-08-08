# Dashboard Paper Books View — Slice 2a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sub-project-1 placeholder screen with the real Paper Books view —
a compact row list (full parity with today's Streamlit card grid: 4 sort modes,
monitor-only filter, up-for-review nudge, sparklines) and a shared core detail panel
(blurb, 6 stats, verdict, live-equity chart with range control, backtest-history +
divergence expander) for every book kind, reachable via `/books/:name` routing.

**Architecture:** `src/tradefabe/dashboard.py` gains the remaining Streamlit-cached
loaders `app.py` still holds (so it can build a full `book_panel_data()` response with
no Streamlit runtime) plus three small extracted helpers (`book_colors`,
`latest_verdicts`, `available_windows`) and a `compute_positions` flag on
`book_panel_data()`. `src/tradefabe/api/main.py` gains query params on
`GET /api/books/summary` and two new endpoints (`up_for_review`, `{name}/detail`), all
built from `dashboard.py` functions with no new business logic. The frontend gets
routing (`react-router-dom`), a `RowList` + `DetailPanel`/`RangeControl` pair, a
`PlotlyChart` wrapper with a dark-theme layout override (validated by a pre-plan spike —
see the spec), and its first test framework (Vitest + RTL).

**Tech Stack:** Python (FastAPI, pandas) for the backend; React + TypeScript +
`react-router-dom` + `react-plotly.js` for the frontend; Vitest + React Testing Library
for frontend tests; `pytest` (existing) for backend tests.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-dashboard-paper-books-2a-design.md`. Every
  task implements a section of it; nothing here goes beyond its scope except where
  noted (Task 1 also moves seven `@st.cache_data` loaders that the spec's `/detail`
  endpoint needs but that sub-project 1 left in `app.py` — a mechanical extension of the
  exact pattern sub-project 1's own Task 1 already established, not a new decision).
- `app.py` must keep working, unmodified in behavior, through every task — it's the
  live dashboard until sub-project 4 retires it.
- No Streamlit import (`streamlit`, `st.*`) anywhere in `src/tradefabe/dashboard.py` or
  `src/tradefabe/api/`.
- No business logic (sort/filter/family grouping, chart building, NaN-safety) gets
  duplicated in TypeScript — it stays server-side and is reused, per the council
  guardrail in the spec.
- Chart layout dark-theme override is a **frontend-only** change (`plotlyDarkTheme.ts`)
  — never edit `dashboard.themed_layout()`'s colors; `app.py` still renders these same
  charts live with the light theme.
- `book_panel_data()`'s new `compute_positions` parameter defaults to `True` — every
  existing caller (`app.py`, six existing test files) needs zero changes.
- Full test suite (`.venv/bin/pytest tests/ -n0`) must pass at the end of every backend
  task. Full frontend suite (`npm test` in `frontend/`) must pass at the end of every
  frontend task once Task 5 introduces it.
- Branch: `feat/dashboard-paper-books-2a` (already created, holds the approved spec
  commit).

---

### Task 1: Backend data-layer prep — move remaining loaders, add three helpers, add `compute_positions`

**Files:**
- Modify: `src/tradefabe/dashboard.py` (loaders moved in, `book_colors`,
  `latest_verdicts`, `available_windows` added, `book_panel_data` gains a parameter)
- Modify: `app.py` (imports rewired; three inline duplications replaced with the new
  helpers)
- Modify: `tests/test_book_panel_data.py` (new case for `compute_positions=False`)
- Test: full existing suite must pass at the end of this task

**Interfaces:**
- Produces: `dashboard.load_backtest() -> (full: pd.DataFrame, meta: dict, nulls: dict,
  gy: pd.DataFrame)`, `dashboard.load_piggyback_backtest() -> pd.DataFrame | None`,
  `dashboard.load_factory_backtest() -> pd.DataFrame | None`,
  `dashboard.load_pipeline_backtest() -> pd.DataFrame | None`,
  `dashboard.load_hourly_backtest() -> pd.DataFrame | None`,
  `dashboard.load_kronos_backtest() -> pd.DataFrame | None`,
  `dashboard.load_price_snapshot() -> (pd.Series | None, pd.Timestamp | None)`,
  `dashboard.book_colors(names: list[str]) -> dict[str, str]`,
  `dashboard.latest_verdicts(gy: pd.DataFrame) -> pd.DataFrame` (indexed by strategy
  name, one row per strategy — `gy.drop_duplicates("strategy", keep="last").set_index("strategy")`),
  `dashboard.available_windows(live_hist: pd.Series) -> list[str]`,
  `dashboard.book_panel_data(..., compute_positions: bool = True) -> dict` (new
  keyword-only-by-convention parameter; `positions_df`/`deployment` are `None` when
  `False`, and the expensive pricing loop that builds them does not run).

This is one task in four parts, landed together for the same reason sub-project 1's
Task 1 was: `app.py` cannot run with only some of the imports rewired.

#### Part A — move the seven remaining loaders

`app.py` still holds seven `@st.cache_data`-decorated loaders
(`load_backtest`, `load_piggyback_backtest`, `load_factory_backtest`,
`load_pipeline_backtest`, `load_hourly_backtest`, `load_kronos_backtest`,
`load_price_snapshot`) that sub-project 1 deliberately left behind — its Task 1 only
moved what the one placeholder screen needed (`load_paper_state`). The `/detail`
endpoint (Task 4) needs all seven to build a `book_panel_data()` response for any book
regardless of origin. Same reasoning sub-project 1 already applied to
`load_carry_backtest`: these decorators exist purely for Streamlit's rerun cache, their
reads are small CSV/JSON/`.npz` files, and dropping the decorator on move is the
established precedent (CLAUDE.md's dashboard-rebuild note names `load_carry_backtest`
as the example).

- [ ] **Step 1: Write and run the extraction script**

```python
# scratch_extract_loaders.py -- run once, then delete
import ast
import re

FUNC_NAMES = [
    "load_backtest", "load_piggyback_backtest", "load_factory_backtest",
    "load_pipeline_backtest", "load_hourly_backtest", "load_kronos_backtest",
    "load_price_snapshot",
]

with open("app.py") as f:
    src = f.read()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)

func_nodes = {}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in FUNC_NAMES:
        func_nodes[node.name] = node
missing = set(FUNC_NAMES) - set(func_nodes)
assert not missing, f"functions not found: {missing}"

body_parts = []
for name, node in func_nodes.items():
    # decorator excluded by design -- @st.cache_data is Streamlit-specific and dropped
    # on move, same as load_carry_backtest in sub-project 1.
    block = "".join(lines[node.lineno - 1:node.end_lineno]).rstrip("\n")
    assert not re.search(r"\bst\.[a-zA-Z_]", block), f"{name}: still references streamlit"
    body_parts.append((node.lineno, block))
body_parts.sort(key=lambda t: t[0])
new_body = "\n\n\n".join(p[1] for p in body_parts) + "\n"

with open("src/tradefabe/dashboard.py") as f:
    dash_src = f.read()
# Insert directly after load_carry_backtest (the natural "loaders" section, already
# the first function in the file) rather than appending at the end.
marker = "\ndef load_paper_state("
idx = dash_src.index(marker)
dash_src = dash_src[:idx] + new_body + "\n\n" + dash_src[idx:]
with open("src/tradefabe/dashboard.py", "w") as f:
    f.write(dash_src)

removals = []
for name, node in func_nodes.items():
    start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    removals.append((start, node.end_lineno))
for (s, e) in sorted(removals, reverse=True):
    del lines[s - 1:e]
with open("app.py", "w") as f:
    f.writelines(lines)

print(f"moved {len(func_nodes)} functions")
```

Run: `python3 scratch_extract_loaders.py`
Expected output: `moved 7 functions`

- [ ] **Step 2: Delete the scratch script**

```bash
rm scratch_extract_loaders.py
```

- [ ] **Step 3: Verify `dashboard.py` is syntactically valid and Streamlit-free**

Run: `python3 -c "import ast; ast.parse(open('src/tradefabe/dashboard.py').read())" && grep -c streamlit src/tradefabe/dashboard.py`
Expected: no syntax error, printed count is `0`.

#### Part B — rewire `app.py`'s imports

- [ ] **Step 4: Add the seven names to `app.py`'s `from tradefabe.dashboard import (...)` block**

Find the import block (from sub-project 1's Task 1) and add the seven names, keeping
the rest unchanged:

```python
from tradefabe.dashboard import (
    ART, BASE, BENCH_C, CRIT, GOOD, INK2, MIN_CHART_POINTS, RANGE_WINDOWS,
    REVIEW_AGE_DAYS, SLOTS, SPY_C, Y_PAD,
    load_carry_backtest, load_paper_state, load_book_json, ann_stats, fmt,
    signals_cost_bps, money, _rgba, themed_layout, book_panel_data, trades_frame,
    window_slice, padded_range, live_equity_chart, backtest_chart, divergence_status,
    luck_floor_chart, drawdown_chart, correlation_heatmap, growth_chart,
    fmt_full_dollars, book_family, factory_owned_names, books_up_for_review,
    _is_monitor_only, group_books_by_family, book_introduced_dates, book_return_today,
    sort_books_flat, strategy_description, retirement_note, _dead_strategy_returns,
    load_backtest, load_piggyback_backtest, load_factory_backtest,
    load_pipeline_backtest, load_hourly_backtest, load_kronos_backtest,
    load_price_snapshot, book_colors, latest_verdicts, available_windows,
)
```

(`book_colors`, `latest_verdicts`, `available_windows` don't exist yet — Part C below
creates them. Listing them here now means Part C's edit is additive only.)

- [ ] **Step 5: Confirm no leftover blank-block artifacts**

Run: `sed -n '1,25p' app.py` and collapse any run of 3+ blank lines left by Step 1's
deletions down to 2, by hand.

#### Part C — add `book_colors`, `latest_verdicts`, `available_windows` to `dashboard.py`

Three small extractions of logic currently inlined in `app.py`, needed both there (DRY)
and by the API (Tasks 2 and 4).

- [ ] **Step 6: Write the failing tests**

Create `tests/test_dashboard_helpers.py`:

```python
import pandas as pd

from tradefabe import dashboard


def test_book_colors_assigns_by_position_cycling_through_slots():
    names = ["a", "b", "c"]
    colors = dashboard.book_colors(names)
    assert colors == {
        "a": dashboard.SLOTS[0], "b": dashboard.SLOTS[1], "c": dashboard.SLOTS[2],
    }


def test_book_colors_wraps_around_when_more_names_than_slots():
    names = [f"book_{i}" for i in range(len(dashboard.SLOTS) + 2)]
    colors = dashboard.book_colors(names)
    assert colors[f"book_{len(dashboard.SLOTS)}"] == dashboard.SLOTS[0]
    assert colors[f"book_{len(dashboard.SLOTS) + 1}"] == dashboard.SLOTS[1]


def test_latest_verdicts_keeps_last_row_per_strategy_indexed_by_name():
    gy = pd.DataFrame({
        "strategy": ["a", "a", "b"],
        "verdict": ["DEAD", "ALIVE", "DEAD"],
    })
    out = dashboard.latest_verdicts(gy)
    assert out.loc["a", "verdict"] == "ALIVE"
    assert out.loc["b", "verdict"] == "DEAD"
    assert list(out.index) == ["a", "b"]


def test_available_windows_excludes_windows_wider_than_the_live_span():
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    live_hist = pd.Series([100_000, 100_100, 100_050], index=idx)
    windows = dashboard.available_windows(live_hist)
    assert windows[-1] == "ALL"
    assert "1Y" not in windows
    assert "1D" in windows


def test_available_windows_includes_all_when_span_covers_everything():
    idx = pd.date_range("2020-01-01", periods=800, freq="D")
    live_hist = pd.Series(range(800), index=idx)
    windows = dashboard.available_windows(live_hist)
    assert windows == ["5H", "1D", "1W", "1M", "3M", "1Y", "ALL"]
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_dashboard_helpers.py -v`
Expected: FAIL — `AttributeError: module 'tradefabe.dashboard' has no attribute 'book_colors'`
(and similarly for the other two).

- [ ] **Step 8: Implement the three helpers**

Add to `src/tradefabe/dashboard.py`, directly after `book_family` (near the other
per-book lookup helpers):

```python
def book_colors(names: list[str]) -> dict[str, str]:
    """One stable color per book, cycling through SLOTS by position in `names`. Shared
    by the row list and the detail-panel chart so the same book always gets the same
    color wherever it's drawn -- extracted from what was an inline dict comprehension
    duplicated across render call sites in app.py before this."""
    return {n: SLOTS[i % len(SLOTS)] for i, n in enumerate(names)}


def latest_verdicts(gy: pd.DataFrame) -> pd.DataFrame:
    """graveyard.csv can log more than one row per strategy over time (re-runs under
    doctrine v1.5's segregated n_tested); this keeps only the most recent verdict per
    strategy, indexed by name for O(1) `.loc[name]` lookups -- the shape book_panel_data,
    group_books_by_family, and sort_books_flat all expect as `gy_last`."""
    return gy.drop_duplicates("strategy", keep="last").set_index("strategy")


def available_windows(live_hist: pd.Series) -> list[str]:
    """Which range-control options are meaningful for this book's live history --
    narrower than its actual span reads as a real choice, wider is a no-op that would
    just show 'ALL' again under a misleading label. 'ALL' is always available."""
    if live_hist.empty:
        return ["ALL"]
    span = live_hist.index[-1] - live_hist.index[0]
    return [w for w in RANGE_WINDOWS if span >= RANGE_WINDOWS[w]] + ["ALL"]
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_dashboard_helpers.py -v`
Expected: all 5 pass.

- [ ] **Step 10: Replace the three inline duplications in `app.py` with the new helpers**

In `render_paper_books` (around where `color_of` is built):
```python
color_of = {n: SLOTS[i % len(SLOTS)] for i, n in enumerate(names)}
```
becomes:
```python
color_of = book_colors(names)
```

At the bottom of the file, both occurrences of:
```python
gy_last = gy.drop_duplicates("strategy", keep="last").set_index("strategy")
```
(the module-level one near `full, meta, nulls, gy = load_backtest()`, and the one
inside `render_research_lab`) become:
```python
gy_last = latest_verdicts(gy)
```

In `render_strategy_panel`, find:
```python
    span = live_hist.index[-1] - live_hist.index[0]
    options = [w for w in ("5H", "1D", "1W", "1M", "3M", "1Y", "ALL")
               if w == "ALL" or span >= RANGE_WINDOWS[w]]
```
Replace with:
```python
    options = available_windows(live_hist)
```
(`span` is no longer used elsewhere in this function — confirm with
`grep -n "span" app.py` inside `render_strategy_panel`'s body before deleting the
now-unused local; if it's still referenced, keep the `span =` line and only replace the
`options = [...]` list comprehension.)

#### Part D — add `compute_positions` to `book_panel_data()`

- [ ] **Step 11: Write the failing test**

Add to `tests/test_book_panel_data.py`:

```python
def test_book_panel_data_skips_positions_when_compute_positions_is_false():
    name = "some_book"
    full = pd.DataFrame({name: [0.001] * 40}, index=pd.bdate_range("2018-01-02", periods=40))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = app.book_panel_data(
        name, _phist(name, dates, [100_000, 100_100, 100_050]),
        full, _meta(), _gy_last_row(name, verdict="ALIVE"), None, None,
        compute_positions=False,
    )
    assert data["positions_df"] is None
    assert data["deployment"] is None
    # everything else 2a actually needs is still populated
    assert data["stats"] is not None
    assert data["live_hist"] is not None


def test_book_panel_data_still_computes_positions_by_default():
    name = "some_book"
    full = pd.DataFrame({name: [0.001] * 40}, index=pd.bdate_range("2018-01-02", periods=40))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = app.book_panel_data(
        name, _phist(name, dates, [100_000, 100_100, 100_050]),
        full, _meta(), _gy_last_row(name, verdict="ALIVE"), None, None,
    )
    # book_json has no positions in this fixture, but the deployment dict itself
    # must still be built (not None) -- that's the default-True contract.
    assert data["deployment"] is not None
```

- [ ] **Step 12: Run the tests to verify the first one fails**

Run: `.venv/bin/pytest tests/test_book_panel_data.py -v -k compute_positions`
Expected: `test_book_panel_data_skips_positions_when_compute_positions_is_false` FAILS
with `TypeError: book_panel_data() got an unexpected keyword argument 'compute_positions'`.
`test_book_panel_data_still_computes_positions_by_default` also fails for the same
reason (the parameter doesn't exist yet, so the call itself errors).

- [ ] **Step 13: Implement the parameter**

In `src/tradefabe/dashboard.py`, change `book_panel_data`'s signature:

```python
def book_panel_data(name, phist, full, meta, gy_last, price_now, price_date, piggy=None,
                    factory_bt=None, hourly_bt=None, kronos_bt=None, pipeline_bt=None,
                    compute_positions=True):
```

And guard the existing positions/deployment block:

```python
    positions_df = None
    deployment = None
    if compute_positions and kind == "equity" and name not in ACCRUAL_ONLY_BOOKS:
        book = load_book_json(name)
        ...  # unchanged body
```

(The rest of the function body is untouched — only the `if` condition gains the
`compute_positions and` clause, and the signature gains the new parameter with a
default that preserves every existing call site's behavior.)

- [ ] **Step 14: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_book_panel_data.py -v`
Expected: all pass, including the two new ones.

#### Part E — verify and commit

- [ ] **Step 15: Manual smoke test**

Run: `.venv/bin/streamlit run app.py` and confirm both views (Paper Books, Research
Lab) load without a traceback, and clicking through a couple of books' range controls
still works. Stop the server (Ctrl+C).

- [ ] **Step 16: Run the full test suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all tests pass.

- [ ] **Step 17: Commit**

```bash
git add src/tradefabe/dashboard.py app.py tests/test_dashboard_helpers.py tests/test_book_panel_data.py
git commit -m "$(cat <<'EOF'
dashboard.py: move remaining loaders, add book_colors/latest_verdicts/
available_windows, add compute_positions to book_panel_data

Seven @st.cache_data loaders (load_backtest and five backtest-curve
siblings, load_price_snapshot) move to dashboard.py undecorated, same
precedent as load_carry_backtest in sub-project 1 -- the /detail
endpoint (Task 4) needs all of them to build a book_panel_data()
response for any book. Three small helpers extracted from app.py
inline duplication (color assignment, latest-verdict-per-strategy,
range-window availability) so the API can reuse the same logic instead
of reimplementing it. book_panel_data() gains compute_positions=True,
letting 2a's detail endpoint skip the expensive positions-pricing loop
for data it isn't returning yet, at zero cost to existing callers.
EOF
)"
```

---

### Task 2: Extend `GET /api/books/summary` with sort/filter and row-list fields

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Modify: `tests/test_api_books_summary.py` (existing tests updated for the new
  response shape; new tests added)

**Interfaces:**
- Consumes: `dashboard.group_books_by_family`, `dashboard.sort_books_flat`,
  `dashboard.book_colors`, `dashboard.book_family`, `dashboard.book_introduced_dates`,
  `dashboard.book_return_today`, `dashboard._is_monitor_only`, `dashboard.latest_verdicts`,
  `dashboard.load_backtest` (Task 1).
- Produces: `GET /api/books/summary?sort=family|recent|return_today|total_return&show_monitor_only=true|false`.
  Response for `sort=family` (default): `{"families": [{"family": str, "label": str,
  "books": [<row>]}]}`. Response for the other three: `{"books": [<row>]}`. Each `<row>`:
  `{book, equity, return, last_run, retired_at, family, color, introduced,
  return_today, monitor_only, sparkline}`.

This is a **breaking response-shape change** on an existing route (deliberate, per the
approved spec) — the existing three tests in `tests/test_api_books_summary.py` assert
the old flat-list shape and must be rewritten, not just extended.

- [ ] **Step 1: Rewrite `tests/test_api_books_summary.py`**

Replace the file's contents entirely:

```python
import math

import pandas as pd
from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_summary_default_sort_groups_by_family():
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "families" in body
    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        assert body["families"] == []
        return
    total_books = sum(len(f["books"]) for f in body["families"])
    assert total_books == len(psum)
    for fam in body["families"]:
        assert set(fam.keys()) == {"family", "label", "books"}


def test_summary_flat_sort_modes_return_a_flat_books_list():
    client = TestClient(app)
    for sort in ("recent", "return_today", "total_return"):
        resp = client.get(f"/api/books/summary?sort={sort}")
        assert resp.status_code == 200
        body = resp.json()
        assert "books" in body
        assert "families" not in body


def test_summary_unknown_sort_is_a_400():
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=bogus")
    assert resp.status_code == 400


def test_summary_row_has_all_expected_keys():
    client = TestClient(app)
    body = client.get("/api/books/summary?sort=recent").json()
    if not body["books"]:
        return  # no paper state in this environment
    row = body["books"][0]
    for key in ("book", "equity", "return", "last_run", "retired_at", "family",
                "color", "introduced", "return_today", "monitor_only", "sparkline"):
        assert key in row


def test_summary_row_color_matches_book_colors_helper():
    client = TestClient(app)
    body = client.get("/api/books/summary?sort=recent").json()
    if not body["books"]:
        return
    psum, _phist = dashboard.load_paper_state()
    expected = dashboard.book_colors(psum["book"].tolist())
    for row in body["books"]:
        assert row["color"] == expected[row["book"]]


def test_summary_show_monitor_only_false_excludes_monitor_only_books():
    client = TestClient(app)
    all_body = client.get("/api/books/summary?sort=recent&show_monitor_only=true").json()
    filtered_body = client.get("/api/books/summary?sort=recent&show_monitor_only=false").json()
    filtered_names = {r["book"] for r in filtered_body["books"]}
    for row in all_body["books"]:
        if row["monitor_only"]:
            assert row["book"] not in filtered_names


def test_summary_nan_fields_become_json_null_not_nan_token():
    """A book with < 2 distinct calendar days of history has NaN return_today --
    the response body must be valid JSON (null), never the bare NaN token FastAPI's
    default json.dumps(allow_nan=True) would otherwise emit."""
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=recent")
    assert "NaN" not in resp.text
    body = resp.json()
    for row in body["books"]:
        if row["return_today"] is not None:
            assert math.isfinite(row["return_today"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_books_summary.py -v`
Expected: FAIL — the endpoint still returns a flat list and ignores query params.

- [ ] **Step 3: Implement the extended endpoint**

Replace `src/tradefabe/api/main.py`'s `books_summary` function and imports:

```python
import json
import math

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradefabe import dashboard

app = FastAPI(title="tradefabe dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _finite_or_none(v):
    """FastAPI/Starlette's default JSONResponse uses json.dumps(allow_nan=True), which
    emits the bare (invalid-JSON) token NaN for a non-finite float -- browser fetch().json()
    throws on that. Every numeric field that can be NaN (ann_stats, book_return_today,
    etc.) must be routed through this before it reaches a response body."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _load_gy_last():
    """None if artifacts/full_returns.csv or graveyard.csv doesn't exist yet -- same
    FileNotFoundError handling app.py's own entry point already does."""
    try:
        _full, _meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        return None
    return dashboard.latest_verdicts(gy)


def _sparkline(phist, name, n=20):
    h = (phist[phist["book"] == name].drop_duplicates("date", keep="last")
         .sort_values("date")["equity"])
    return [_finite_or_none(v) for v in h.tail(n).tolist()]


def _row_json(r, *, colors, introduced, return_today, monitor_only, phist):
    name = r["book"]
    intro = introduced.get(name, pd.NaT)
    return {
        "book": name,
        "equity": _finite_or_none(r["equity"]),
        "return": _finite_or_none(r["return"]),
        "last_run": r["last_run"],
        "retired_at": r.get("retired_at") if pd.notna(r.get("retired_at")) else None,
        "family": dashboard.book_family(name),
        "color": colors.get(name),
        "introduced": intro.isoformat() if pd.notna(intro) else None,
        "return_today": _finite_or_none(return_today.get(name, float("nan"))),
        "monitor_only": monitor_only.get(name, False),
        "sparkline": _sparkline(phist, name),
    }


@app.get("/api/books/summary")
def books_summary(sort: str = "family", show_monitor_only: bool = True):
    psum, phist = dashboard.load_paper_state()
    if psum is None:
        return {"families": []} if sort == "family" else {"books": []}

    gy_last = _load_gy_last()
    names = psum["book"].tolist()
    colors = dashboard.book_colors(names)
    introduced = dashboard.book_introduced_dates(phist)
    return_today = dashboard.book_return_today(phist)
    monitor_only = {n: dashboard._is_monitor_only(n, gy_last) for n in names}

    def row_kwargs():
        return dict(colors=colors, introduced=introduced, return_today=return_today,
                   monitor_only=monitor_only, phist=phist)

    if sort == "family":
        groups = dashboard.group_books_by_family(psum, gy_last, show_monitor_only)
        return {"families": [
            {"family": family, "label": label,
             "books": [_row_json(r, **row_kwargs()) for r in rows]}
            for family, label, rows in groups
        ]}

    if sort not in ("recent", "return_today", "total_return"):
        raise HTTPException(status_code=400, detail=f"unknown sort: {sort}")

    rows = dashboard.sort_books_flat(psum, phist, gy_last, show_monitor_only, sort)
    return {"books": [_row_json(r, **row_kwargs()) for r in rows]}
```

(`json` import stays even though this function no longer uses `json.loads` directly —
Task 3/4 below add endpoints that do.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_books_summary.py -v`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_books_summary.py
git commit -m "$(cat <<'EOF'
api: sort/filter query params and row-list fields on GET /api/books/summary

Breaking response-shape change on the existing route, per the approved
spec: sort=family (default) now groups into {family, label, books},
the other three sort modes return a flat {books}. Each row gains
family/color/introduced/return_today/monitor_only/sparkline -- built
entirely from dashboard.py functions (group_books_by_family,
sort_books_flat, book_colors, etc.), no new logic. All numeric fields
route through _finite_or_none() so NaN serializes as JSON null, not
the bare (invalid-JSON) NaN token Starlette's default encoder emits.
EOF
)"
```

---

### Task 3: `GET /api/books/up_for_review`

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Create: `tests/test_api_books_up_for_review.py`

**Interfaces:**
- Consumes: `dashboard.books_up_for_review` (existing), `_load_gy_last` (Task 2).
- Produces: `GET /api/books/up_for_review` → `{"books": [{book, days_live, equity,
  return, introduced, verdict}]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_books_up_for_review.py`:

```python
from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_up_for_review_matches_the_dashboard_helper():
    client = TestClient(app)
    resp = client.get("/api/books/up_for_review")
    assert resp.status_code == 200
    body = resp.json()
    assert "books" in body

    psum, phist = dashboard.load_paper_state()
    if psum is None:
        assert body["books"] == []
        return
    expected = dashboard.books_up_for_review(psum, phist)
    assert len(body["books"]) == len(expected)


def test_up_for_review_rows_carry_a_verdict_field():
    client = TestClient(app)
    body = client.get("/api/books/up_for_review").json()
    for row in body["books"]:
        assert "verdict" in row
        assert "days_live" in row
        assert "introduced" in row
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_books_up_for_review.py -v`
Expected: FAIL — `404 Not Found`, the route doesn't exist yet.

- [ ] **Step 3: Implement the endpoint**

Add to `src/tradefabe/api/main.py`, after `books_summary`:

```python
@app.get("/api/books/up_for_review")
def books_up_for_review():
    psum, phist = dashboard.load_paper_state()
    if psum is None:
        return {"books": []}
    gy_last = _load_gy_last()
    rows = dashboard.books_up_for_review(psum, phist)
    out = []
    for r in rows:
        name = r["book"]
        verdict = "—"
        if gy_last is not None and name in gy_last.index:
            verdict = gy_last.loc[name, "verdict"]
        out.append({
            "book": name,
            "days_live": r["days_live"],
            "equity": _finite_or_none(r["equity"]),
            "return": _finite_or_none(r["return"]),
            "introduced": r["introduced"].isoformat(),
            "verdict": verdict,
        })
    return {"books": out}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_books_up_for_review.py -v`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_books_up_for_review.py
git commit -m "$(cat <<'EOF'
api: GET /api/books/up_for_review

Separate route (not folded into /summary) since it's conditionally
rendered and has no reason to share a refresh cadence with the main
list. Thin wrapper over dashboard.books_up_for_review(), same
NaN-safety convention as /summary.
EOF
)"
```

---

### Task 4: `GET /api/books/{name}/detail`

**Files:**
- Modify: `src/tradefabe/api/main.py`
- Create: `tests/test_api_book_detail.py`

**Interfaces:**
- Consumes: `dashboard.book_panel_data(..., compute_positions=False)`,
  `dashboard.available_windows`, `dashboard.strategy_description`,
  `dashboard.retirement_note`, `dashboard.divergence_status`,
  `dashboard.live_equity_chart`, `dashboard.backtest_chart` (all Task 1 / existing).
- Produces: `GET /api/books/{name}/detail?window=ALL` → `404` for an unknown `name`;
  `200` with `{name, kind, blurb, retirement_note, stats, verdict (or carry_meta),
  live_start, bt_start, available_windows, live_equity_chart, backtest_chart,
  divergence_state, divergence_detail}` for a known one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_book_detail.py`:

```python
import math

from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_unknown_book_is_a_404():
    client = TestClient(app)
    resp = client.get("/api/books/not_a_real_book/detail")
    assert resp.status_code == 404


def test_known_book_returns_the_expected_shape():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return  # no paper state in this environment
    name = psum["book"].iloc[0]
    resp = client.get(f"/api/books/{name}/detail")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("name", "kind", "blurb", "stats", "live_start", "bt_start",
                "available_windows", "live_equity_chart", "backtest_chart",
                "divergence_state", "divergence_detail"):
        assert key in body
    assert body["name"] == name
    assert body["kind"] in ("equity", "carry")
    for stat_key in ("Sharpe", "Sortino", "Calmar", "MaxDD", "CAGR", "Vol"):
        assert stat_key in body["stats"]


def test_2a_excludes_positions_and_deployment():
    """The whole point of compute_positions=False -- 2a's response must not carry
    fields that 2b's slice adds later, and the expensive pricing loop must not run."""
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    body = client.get(f"/api/books/{name}/detail").json()
    assert "positions" not in body
    assert "deployment" not in body
    assert "trades" not in body


def test_window_param_changes_the_chart_payload():
    client = TestClient(app)
    psum, phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    live_hist = (phist[phist["book"] == name].drop_duplicates("date", keep="last")
                 .set_index("date")["equity"].sort_index())
    windows = dashboard.available_windows(live_hist)
    if len(windows) < 2:
        return  # too little history to distinguish two windows in this environment
    all_resp = client.get(f"/api/books/{name}/detail?window=ALL").json()
    narrow_resp = client.get(f"/api/books/{name}/detail?window={windows[0]}").json()
    assert all_resp["live_equity_chart"] != narrow_resp["live_equity_chart"]


def test_stats_nan_serializes_as_json_null_not_nan_token():
    """A book with < 30 OOS observations has every ann_stats() field as NaN --
    response body must be valid JSON."""
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    resp = client.get(f"/api/books/{name}/detail")
    assert "NaN" not in resp.text
    for v in resp.json()["stats"].values():
        if v is not None:
            assert math.isfinite(v)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_book_detail.py -v`
Expected: FAIL — `404 Not Found` for every request, the route doesn't exist yet.

- [ ] **Step 3: Implement the endpoint**

Add to `src/tradefabe/api/main.py`:

```python
def _stats_json(stats):
    return {k: _finite_or_none(v) for k, v in stats.items()}


@app.get("/api/books/{name}/detail")
def book_detail(name: str, window: str = "ALL"):
    psum, phist = dashboard.load_paper_state()
    if psum is None or name not in psum["book"].values:
        raise HTTPException(status_code=404, detail=f"unknown book: {name}")

    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")
    gy_last = dashboard.latest_verdicts(gy)

    price_now, price_date = dashboard.load_price_snapshot()
    piggy = dashboard.load_piggyback_backtest()
    factory_bt = dashboard.load_factory_backtest()
    hourly_bt = dashboard.load_hourly_backtest()
    kronos_bt = dashboard.load_kronos_backtest()
    pipeline_bt = dashboard.load_pipeline_backtest()

    data = dashboard.book_panel_data(
        name, phist, full, meta, gy_last, price_now, price_date, piggy,
        factory_bt, hourly_bt, kronos_bt, pipeline_bt, compute_positions=False,
    )

    live_hist = data["live_hist"]
    color = dashboard.book_colors(psum["book"].tolist())[name]
    windows = dashboard.available_windows(live_hist)
    win_choice = window if window in windows else "ALL"
    live_chart = dashboard.live_equity_chart(live_hist, color, win_choice)
    bt_chart = dashboard.backtest_chart(data["bt_curve"], dashboard.INK2)
    div_state, div_detail = dashboard.divergence_status(data)

    body = {
        "name": name,
        "kind": data["kind"],
        "blurb": dashboard.strategy_description(name),
        "retirement_note": dashboard.retirement_note(data.get("book_json")),
        "stats": _stats_json(data["stats"]),
        "live_start": data["live_start"].isoformat(),
        "bt_start": data["bt_start"].isoformat() if data.get("bt_start") is not None else None,
        "available_windows": windows,
        "live_equity_chart": json.loads(live_chart.to_json()),
        "backtest_chart": json.loads(bt_chart.to_json()),
        "divergence_state": div_state,
        "divergence_detail": div_detail,
    }
    if data["kind"] == "equity":
        body["verdict"] = data["verdict"]
        body["corr_bench"] = _finite_or_none(data["corr_bench"])
        body["null_p95"] = _finite_or_none(data["null_p95"])
        body["freq"] = data["freq"]
    else:
        body["carry_meta"] = {k: _finite_or_none(v) for k, v in data["carry_meta"].items()}
    return body
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_book_detail.py -v`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass. This is also the point where every Task 1-4 backend change is
proven to compose correctly end to end.

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_book_detail.py
git commit -m "$(cat <<'EOF'
api: GET /api/books/{name}/detail

Calls book_panel_data(..., compute_positions=False) -- the response
carries everything slice 2a's UI needs (blurb, stats, verdict/carry
meta, both charts as go.Figure.to_json() payloads, divergence status)
and nothing 2b will add (positions/deployment/trades), without paying
for the positions-pricing loop it isn't returning. Window changes are
a new request (?window=X), matching the "charts are API responses"
model confirmed by the pre-plan spike. 404 on an unknown book name,
503 if backtest artifacts haven't been generated yet.
EOF
)"
```

---

### Task 5: Frontend deps, routing shell, Vitest/RTL, `plotlyDarkTheme` + `PlotlyChart`

**Files:**
- Modify: `frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`,
  `frontend/tailwind.config.js`, `frontend/src/index.css`
- Create: `frontend/vitest.config.ts`, `frontend/src/lib/plotlyDarkTheme.ts`,
  `frontend/src/lib/plotlyDarkTheme.test.ts`, `frontend/src/lib/motion.ts`,
  `frontend/src/lib/sound.ts`, `frontend/src/lib/sound.test.ts`,
  `frontend/src/components/PlotlyChart.tsx`, `frontend/src/components/Nav.tsx`,
  `frontend/src/test/setup.ts`

**Interfaces:**
- Produces: `applyDarkTheme(layout: Record<string, unknown>) -> Record<string,
  unknown>` (pure merge function), `<PlotlyChart figure={{data, layout}} />` component,
  a router with `/books` → redirect to the first book, `/books/:name` route (rendered by
  Task 6/7's components, stubbed here). Also, per the spec's visual-language amendment:
  `SPRING` (shared Framer Motion spring config), `isSoundEnabled()`/`setSoundEnabled()`/
  `playSelect()`/`playRangeChange()`/`playDataLanded()` (Web Audio UI sounds), `<Nav />`
  (title/links/mute-toggle, used by both `/books` and `/books/:name`), the `.grain-overlay`
  CSS class, and Tailwind's `font-mono` now resolving to IBM Plex Mono.

- [ ] **Step 1: Add the new dependencies**

```bash
cd frontend
npm install react-router-dom react-plotly.js plotly.js
npm install -D @types/react-plotly.js @types/plotly.js vitest @testing-library/react @testing-library/jest-dom jsdom
cd ..
```

- [ ] **Step 2: Write the failing test for `plotlyDarkTheme`**

Create `frontend/src/lib/plotlyDarkTheme.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { applyDarkTheme } from "./plotlyDarkTheme";

describe("applyDarkTheme", () => {
  it("overrides the light-theme background and font colors", () => {
    const light = {
      paper_bgcolor: "#fcfcfb",
      plot_bgcolor: "#fcfcfb",
      font: { family: "IBM Plex Mono, monospace", size: 11, color: "#2b2a27" },
      xaxis: { gridcolor: "#e5e4e0" },
      yaxis: { gridcolor: "#e5e4e0" },
      height: 340,
    };
    const dark = applyDarkTheme(light);
    expect(dark.paper_bgcolor).toBe("#181c15");
    expect(dark.plot_bgcolor).toBe("#181c15");
    expect((dark.font as { color: string }).color).toBe("#7d8877");
    expect((dark.xaxis as { gridcolor: string }).gridcolor).not.toBe("#e5e4e0");
    expect((dark.yaxis as { gridcolor: string }).gridcolor).not.toBe("#e5e4e0");
  });

  it("preserves layout keys it doesn't own, like height", () => {
    const dark = applyDarkTheme({ height: 340, showlegend: false });
    expect(dark.height).toBe(340);
    expect(dark.showlegend).toBe(false);
  });
});
```

- [ ] **Step 3: Add the test script and Vitest config**

In `frontend/package.json`, add to `"scripts"`:
```json
"test": "vitest run"
```

Create `frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './plotlyDarkTheme'`.

- [ ] **Step 5: Implement `plotlyDarkTheme.ts`**

Create `frontend/src/lib/plotlyDarkTheme.ts`:

```ts
// Overrides the color-bearing keys of a Plotly layout fetched from the API. The
// backend's dashboard.themed_layout() bakes in the OLD Streamlit theme's light colors
// (paper_bgcolor #fcfcfb) -- it can't be changed there because app.py still renders
// these same charts live with that theme. Confirmed working via a pre-plan spike:
// react-plotly.js renders correctly against the dark canvas once these keys are
// overridden client-side. Only color-bearing keys are touched; trace-level `data`
// (line/fill colors) already come from the API's per-book SLOTS palette and are
// left untouched.
const SURFACE = "#181c15";
const INK_MUTED = "#7d8877";
const GRID = "#2a2f24";

export function applyDarkTheme(
  layout: Record<string, unknown>
): Record<string, unknown> {
  const font = (layout.font as Record<string, unknown>) ?? {};
  const xaxis = (layout.xaxis as Record<string, unknown>) ?? {};
  const yaxis = (layout.yaxis as Record<string, unknown>) ?? {};
  return {
    ...layout,
    paper_bgcolor: SURFACE,
    plot_bgcolor: SURFACE,
    font: { ...font, color: INK_MUTED },
    xaxis: { ...xaxis, gridcolor: GRID, linecolor: GRID },
    yaxis: { ...yaxis, gridcolor: GRID, linecolor: GRID },
  };
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: both `applyDarkTheme` tests pass.

- [ ] **Step 7: Implement `PlotlyChart`**

Create `frontend/src/components/PlotlyChart.tsx`:

```tsx
import Plot from "react-plotly.js";
import { applyDarkTheme } from "../lib/plotlyDarkTheme";

type PlotlyFigure = {
  data: Plotly.Data[];
  layout: Record<string, unknown>;
};

export default function PlotlyChart({ figure }: { figure: PlotlyFigure }) {
  return (
    <Plot
      data={figure.data}
      layout={{ ...applyDarkTheme(figure.layout), autosize: true }}
      style={{ width: "100%", height: "340px" }}
      useResizeHandler
      config={{ displayModeBar: false }}
    />
  );
}
```

- [ ] **Step 8: Add IBM Plex Mono for data typography**

Per the spec's visual-language amendment: numeric displays go monospace, tied to the
same face `dashboard.themed_layout()` already sets for the Plotly charts.

In `frontend/tailwind.config.js`, extend `theme.extend.fontFamily` (find the existing
`display` entry and add `mono` alongside it):

```js
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
```

In `frontend/src/index.css`, extend the existing Google Fonts `@import` to also pull
IBM Plex Mono (find the current `@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk...')` line and replace it):

```css
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;900&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
```

- [ ] **Step 9: Add the ambient dither-texture overlay**

Append to `frontend/src/index.css` (a static, non-animated overlay — see the spec for
why this stays out of the Plotly chart fills):

```css
.grain-overlay {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9999;
  opacity: 0.045;
  mix-blend-mode: overlay;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
```

- [ ] **Step 10: Implement the shared spring-motion config**

Create `frontend/src/lib/motion.ts`:

```ts
// Shared spring transition for Framer Motion -- real weight/slight overshoot instead
// of a smooth eased fade, per the spec's "alive and breathing" visual-language
// amendment. One shared config so every tactile moment (row selection, detail-panel
// mount) feels consistent rather than each call site picking its own numbers.
export const SPRING = { type: "spring" as const, stiffness: 500, damping: 28 };
```

- [ ] **Step 11: Write the failing test for the sound mute toggle**

Create `frontend/src/lib/sound.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { isSoundEnabled, setSoundEnabled } from "./sound";

describe("sound mute toggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to enabled", () => {
    expect(isSoundEnabled()).toBe(true);
  });

  it("persists a mute choice across calls", () => {
    setSoundEnabled(false);
    expect(isSoundEnabled()).toBe(false);
    setSoundEnabled(true);
    expect(isSoundEnabled()).toBe(true);
  });
});
```

- [ ] **Step 12: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './sound'`.

- [ ] **Step 13: Implement `sound.ts`**

Create `frontend/src/lib/sound.ts`:

```ts
// Short synthesized UI sounds (Web Audio oscillator blips), not audio files -- nothing
// to source/license/commit. Three real interaction moments only (row select, range
// click, first-data-landed), never hover or re-render, per the spec. A persisted mute
// toggle is required, not optional: a tool left open all day with unmutable sound
// would get tiresome fast.
const STORAGE_KEY = "tradefabe.sound.enabled";
let ctx: AudioContext | null = null;

export function isSoundEnabled(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== "off";
}

export function setSoundEnabled(on: boolean) {
  localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
}

function getContext(): AudioContext | null {
  if (typeof window === "undefined" || typeof window.AudioContext === "undefined") {
    return null; // no Web Audio support -- e.g. the Vitest/jsdom test environment
  }
  if (!ctx) ctx = new AudioContext();
  return ctx;
}

function blip(freq: number, durationSec: number, gain: number) {
  if (!isSoundEnabled()) return;
  const audioCtx = getContext();
  if (!audioCtx) return;
  try {
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "triangle";
    osc.frequency.value = freq;
    g.gain.setValueAtTime(0, audioCtx.currentTime);
    g.gain.linearRampToValueAtTime(gain, audioCtx.currentTime + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + durationSec);
    osc.connect(g);
    g.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + durationSec);
  } catch {
    // A UI sound effect must never break the interaction it's attached to -- e.g. a
    // browser that hasn't unlocked audio playback yet without a user gesture.
  }
}

export function playSelect() {
  blip(420, 0.06, 0.05);
}

export function playRangeChange() {
  blip(560, 0.04, 0.04);
}

export function playDataLanded() {
  blip(300, 0.08, 0.03);
}
```

- [ ] **Step 14: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: both `sound` mute-toggle tests pass.

- [ ] **Step 15: Implement the shared `Nav` (title, links, mute toggle)**

Extracted once here rather than duplicated per-layout, since Step 16 needs it in two
places (`/books` with no selection, `/books/:name` with one).

Create `frontend/src/components/Nav.tsx`:

```tsx
import { useState } from "react";
import { isSoundEnabled, setSoundEnabled } from "../lib/sound";

export default function Nav() {
  const [soundOn, setSoundOn] = useState(isSoundEnabled());
  return (
    <nav className="w-56 border-r border-white/5 p-6 text-sm text-ink-muted flex flex-col">
      <div className="text-ink font-bold mb-6">tradefabe</div>
      <div className="mb-2 text-ink">Paper Books</div>
      <div>Research Lab</div>
      <button
        className="mt-auto text-xs text-ink-muted text-left"
        onClick={() => {
          const next = !soundOn;
          setSoundEnabled(next);
          setSoundOn(next);
        }}
      >
        Sound: {soundOn ? "on" : "off"}
      </button>
    </nav>
  );
}
```

- [ ] **Step 16: Wire up routing in `main.tsx`, replace the placeholder `App.tsx`, mount the grain overlay**

Replace `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
```

Replace `frontend/src/App.tsx` (Task 6/7 fill in `RowList`/`DetailPanel`; this step
only wires the shell, the grain overlay, and a redirect so the route tree is real from
here on):

```tsx
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import Nav from "./components/Nav";
import RowList from "./components/RowList";
import DetailPanel from "./components/DetailPanel";

function BooksLayout() {
  const { name } = useParams();
  return (
    <div className="min-h-screen flex">
      <Nav />
      <div className="flex-1 flex overflow-hidden">
        <div className="w-96 border-r border-white/5 overflow-y-auto">
          <RowList selectedName={name ?? null} />
        </div>
        <main className="flex-1 p-10 overflow-y-auto">
          {name ? <DetailPanel name={name} /> : null}
        </main>
      </div>
    </div>
  );
}

// /books alone has no book selected yet -- RowList knows the default-sorted order
// (fetches it itself), so the redirect target is resolved inside RowList's own data
// rather than duplicating sort logic here. Rendering RowList with no selection lets it
// redirect once its fetch resolves.
function BooksIndexRedirect() {
  return (
    <div className="min-h-screen flex">
      <Nav />
      <div className="w-96 border-r border-white/5 overflow-y-auto">
        <RowList selectedName={null} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <>
      <div className="grain-overlay" aria-hidden="true" />
      <Routes>
        <Route path="/" element={<Navigate to="/books" replace />} />
        <Route path="/books" element={<BooksIndexRedirect />} />
        <Route path="/books/:name" element={<BooksLayout />} />
      </Routes>
    </>
  );
}
```

`RowList`/`DetailPanel` don't exist yet — Task 6 creates `RowList` (including the
redirect-to-first-book behavior noted above), Task 7 creates `DetailPanel`. This task
ends with the app failing to compile until then, which is expected and fixed within
this same plan (not left broken across a PR boundary, since Tasks 5-7 land in one PR).

- [ ] **Step 17: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts \
        frontend/tailwind.config.js frontend/src/index.css frontend/src/main.tsx \
        frontend/src/App.tsx frontend/src/lib/ frontend/src/components/PlotlyChart.tsx \
        frontend/src/components/Nav.tsx frontend/src/test/
git commit -m "$(cat <<'EOF'
frontend: routing shell, Vitest+RTL, PlotlyChart, and the visual-
language amendment (mono data type, grain overlay, spring motion, sound)

react-router-dom added: /books redirects to the first book (RowList
resolves the default sort order itself), /books/:name is list + detail.
plotlyDarkTheme.ts overrides only the color-bearing layout keys on top
of whatever the API returns -- confirmed against the real dark theme
by a pre-plan spike -- rather than touching dashboard.py's
still-live-in-app.py themed_layout(). First frontend test framework
for this repo (Vitest + RTL); CI wiring lands in a later task once
RowList/DetailPanel give it something real to gate on.

Also lands the spec's 2026-08-06 visual-language amendment's shared
infrastructure: IBM Plex Mono for data typography (ties frontend
numbers to the same face the Plotly charts already use), a static
ambient dither-texture overlay, a shared Framer Motion spring config,
and synthesized (no audio files) Web Audio UI sounds with a persisted
mute toggle in the new Nav component.
EOF
)"
```

---

### Task 6: `RowList` component

**Files:**
- Create: `frontend/src/components/RowList.tsx`, `frontend/src/components/RowList.test.tsx`

**Interfaces:**
- Consumes: `GET /api/books/summary?sort=...&show_monitor_only=...` (Task 2),
  `GET /api/books/up_for_review` (Task 3), `SPRING` and `playSelect()` (Task 5).
- Produces: `<RowList selectedName={string | null} />`. Navigates via
  `react-router-dom`'s `useNavigate` when a row is clicked, and redirects `/books` to
  the first book in default (family) order once its fetch resolves.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/RowList.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RowList from "./RowList";

const FAMILY_RESPONSE = {
  families: [
    {
      family: "A", label: "Trend",
      books: [
        { book: "tsmom_12m", equity: 103241, return: 0.032, last_run: "2026-08-06",
          retired_at: null, family: "A", color: "#2a78d6", introduced: "2026-01-01",
          return_today: 0.012, monitor_only: false, sparkline: [100000, 100500, 101000] },
      ],
    },
    {
      family: "D", label: "Carry",
      books: [
        { book: "carry_btc_eth", equity: 112003, return: 0.12, last_run: "2026-08-06",
          retired_at: null, family: "D", color: "#1baf7a", introduced: "2025-05-01",
          return_today: 0.001, monitor_only: false, sparkline: [110000, 111500, 112003] },
      ],
    },
  ],
};

const UP_FOR_REVIEW_RESPONSE = { books: [] };

function mockFetchSequence() {
  return vi.fn((url: string) => {
    if (url.includes("up_for_review")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(FAMILY_RESPONSE) });
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  global.fetch = mockFetchSequence();
});

afterEach(() => {
  vi.restoreAllMocks();
});

vi.mock("../lib/sound", () => ({ playSelect: vi.fn() }));

describe("RowList", () => {
  it("renders family-grouped rows by default", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText("carry_btc_eth")).toBeInTheDocument();
    expect(screen.getByText("Trend")).toBeInTheDocument();
  });

  it("refetches with the flat sort when a non-Family option is chosen", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const select = screen.getByLabelText(/sort by/i);
    await userEvent.selectOptions(select, "Total return");
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("sort=total_return"))).toBe(true);
    });
  });

  it("refetches with show_monitor_only=false when the checkbox is unchecked", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const checkbox = screen.getByLabelText(/show monitor-only/i);
    await userEvent.click(checkbox);
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("show_monitor_only=false"))).toBe(true);
    });
  });

  it("plays the select sound when a row is clicked", async () => {
    const { playSelect } = await import("../lib/sound");
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await userEvent.click(screen.getByText("tsmom_12m"));
    expect(playSelect).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './RowList'`.

- [ ] **Step 3: Implement `RowList`**

Create `frontend/src/components/RowList.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { SPRING } from "../lib/motion";
import { playSelect } from "../lib/sound";

type BookRow = {
  book: string;
  equity: number | null;
  return: number | null;
  return_today: number | null;
  family: string;
  color: string;
  introduced: string | null;
  monitor_only: boolean;
  retired_at: string | null;
  sparkline: (number | null)[];
};

type FamilyGroup = { family: string; label: string; books: BookRow[] };
type SummaryResponse = { families: FamilyGroup[] } | { books: BookRow[] };

type ReviewRow = { book: string; days_live: number; verdict: string };

const SORT_OPTIONS: Record<string, string> = {
  Family: "family",
  "Recently added": "recent",
  "Return today": "return_today",
  "Total return": "total_return",
};

function Sparkline({ points }: { points: (number | null)[] }) {
  const vals = points.filter((v): v is number => v !== null);
  if (vals.length < 2) return <span className="w-10 inline-block" />;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const w = 40, h = 16;
  const step = w / (vals.length - 1);
  const d = vals
    .map((v, i) => `${i === 0 ? "M" : "L"}${i * step},${h - ((v - min) / span) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="inline-block">
      <path d={d} fill="none" stroke="#9fe870" strokeWidth={1.5} />
    </svg>
  );
}

function Row({ r, selected }: { r: BookRow; selected: boolean }) {
  const delta = r.return_today ?? r.return;
  return (
    <Link to={`/books/${r.book}`} className="block no-underline" onClick={playSelect}>
      <motion.div
        whileHover={{ backgroundColor: "rgba(159,232,112,0.06)" }}
        animate={{
          backgroundColor: selected ? "rgba(159,232,112,0.12)" : "rgba(0,0,0,0)",
        }}
        transition={SPRING}
        className="flex items-center justify-between px-4 py-2 h-14 text-sm border-b border-white/5"
      >
        <span className="text-ink truncate">{r.book}</span>
        <Sparkline points={r.sparkline} />
        <span className="text-ink-muted font-mono tabular-nums">
          ${r.equity?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "—"}
        </span>
        <span
          className={`font-mono tabular-nums ${
            delta != null && delta >= 0 ? "text-accent" : "text-red-400"
          }`}
        >
          {delta != null ? `${(delta * 100).toFixed(1)}%` : "—"}
        </span>
      </motion.div>
    </Link>
  );
}

export default function RowList({ selectedName }: { selectedName: string | null }) {
  const [sortLabel, setSortLabel] = useState("Family");
  const [showMonitorOnly, setShowMonitorOnly] = useState(true);
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [review, setReview] = useState<ReviewRow[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const sort = SORT_OPTIONS[sortLabel];
    fetch(`http://localhost:8000/api/books/summary?sort=${sort}&show_monitor_only=${showMonitorOnly}`)
      .then((res) => res.json())
      .then((body: SummaryResponse) => {
        setData(body);
        if (selectedName === null) {
          const first = "families" in body ? body.families[0]?.books[0] : body.books[0];
          if (first) navigate(`/books/${first.book}`, { replace: true });
        }
      });
  }, [sortLabel, showMonitorOnly, selectedName, navigate]);

  useEffect(() => {
    fetch("http://localhost:8000/api/books/up_for_review")
      .then((res) => res.json())
      .then((body: { books: ReviewRow[] }) => setReview(body.books));
  }, []);

  if (!data) return <p className="p-4 text-ink-muted">Loading…</p>;

  return (
    <div>
      <div className="p-4 flex items-center justify-between text-xs">
        <label className="flex items-center gap-2">
          Sort by
          <select
            aria-label="Sort by"
            value={sortLabel}
            onChange={(e) => setSortLabel(e.target.value)}
            className="bg-surface text-ink rounded px-1 py-0.5"
          >
            {Object.keys(SORT_OPTIONS).map((label) => (
              <option key={label} value={label}>{label}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            aria-label="Show monitor-only (backtest-DEAD) books"
            type="checkbox"
            checked={showMonitorOnly}
            onChange={(e) => setShowMonitorOnly(e.target.checked)}
          />
          Show monitor-only
        </label>
      </div>

      {review.length > 0 && (
        <details className="px-4 pb-2 text-xs text-ink-muted">
          <summary>Up for review ({review.length})</summary>
          <ul className="mt-2 space-y-1">
            {review.map((r) => (
              <li key={r.book}>{r.book} — {r.days_live}d live, {r.verdict}</li>
            ))}
          </ul>
        </details>
      )}

      {"families" in data
        ? data.families.map((fam) => (
            <div key={fam.family}>
              <div className="px-4 pt-3 pb-1 text-xs uppercase text-ink-muted">{fam.label}</div>
              {fam.books.map((r) => (
                <Row key={r.book} r={r} selected={r.book === selectedName} />
              ))}
            </div>
          ))
        : data.books.map((r) => (
            <Row key={r.book} r={r} selected={r.book === selectedName} />
          ))}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: all `RowList` tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RowList.tsx frontend/src/components/RowList.test.tsx
git commit -m "$(cat <<'EOF'
frontend: RowList component -- sort/filter/up-for-review/sparklines

Full parity with today's Streamlit render_book_status: Family/Recent/
Return-today/Total-return sort modes, monitor-only filter, up-for-
review expander, per-book inline SVG sparkline (no charting lib for a
40px shape). Redirects /books (no selection) to the first book in
default order once the summary fetch resolves. Sort/filter state
drives query params on GET /api/books/summary -- no client-side
re-sorting of server-provided data. $ and % figures render in the
shared mono face; row selection uses the shared spring transition and
plays the select sound, per the visual-language amendment.
EOF
)"
```

---

### Task 7: `DetailPanel` + `RangeControl` components

**Files:**
- Create: `frontend/src/components/DetailPanel.tsx`,
  `frontend/src/components/DetailPanel.test.tsx`,
  `frontend/src/components/RangeControl.tsx`

**Interfaces:**
- Consumes: `GET /api/books/{name}/detail?window=...` (Task 4), `<PlotlyChart>`,
  `SPRING`, `playDataLanded()`, `playRangeChange()` (Task 5).
- Produces: `<DetailPanel name={string} />`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/DetailPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DetailPanel from "./DetailPanel";

const DETAIL_RESPONSE = {
  name: "tsmom_12m",
  kind: "equity",
  blurb: "Sign of the trailing 12-month return.",
  retirement_note: null,
  stats: { Sharpe: 0.8, Sortino: 1.1, Calmar: 0.5, MaxDD: -0.12, CAGR: 0.06, Vol: 0.1 },
  live_start: "2026-01-01T00:00:00",
  bt_start: "2018-01-02T00:00:00",
  available_windows: ["1D", "1W", "1M", "ALL"],
  live_equity_chart: { data: [], layout: {} },
  backtest_chart: { data: [], layout: {} },
  divergence_state: "ok",
  divergence_detail: "Live is tracking backtest within the expected band.",
  verdict: "ALIVE",
  corr_bench: 0.1,
  null_p95: 0.4,
  freq: "D",
};

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(DETAIL_RESPONSE) })
  ) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

vi.mock("../lib/sound", () => ({ playDataLanded: vi.fn(), playRangeChange: vi.fn() }));

describe("DetailPanel", () => {
  it("renders the blurb and stats once loaded", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() =>
      expect(screen.getByText(/trailing 12-month return/)).toBeInTheDocument()
    );
    expect(screen.getByText("0.80")).toBeInTheDocument(); // Sharpe
  });

  it("refetches the detail with the new window when a range option is clicked", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("1W")).toBeInTheDocument());
    await userEvent.click(screen.getByText("1W"));
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("window=1W"))).toBe(true);
    });
  });

  it("refetches when the name prop changes", async () => {
    const { rerender } = render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
    rerender(<DetailPanel name="carry_btc_eth" />);
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("/books/carry_btc_eth/detail"))).toBe(true);
    });
  });

  it("plays the data-landed sound once on initial load, not again on a window refetch", async () => {
    const { playDataLanded } = await import("../lib/sound");
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(playDataLanded).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByText("1W"));
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("window=1W"))).toBe(true);
    });
    expect(playDataLanded).toHaveBeenCalledTimes(1);
  });

  it("plays the range-change sound when a range option is clicked", async () => {
    const { playRangeChange } = await import("../lib/sound");
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("1W")).toBeInTheDocument());
    await userEvent.click(screen.getByText("1W"));
    expect(playRangeChange).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './DetailPanel'`.

- [ ] **Step 3: Implement `RangeControl`**

Create `frontend/src/components/RangeControl.tsx`:

```tsx
import { motion } from "framer-motion";
import { SPRING } from "../lib/motion";
import { playRangeChange } from "../lib/sound";

export default function RangeControl({
  options, value, onChange,
}: {
  options: string[];
  value: string;
  onChange: (window: string) => void;
}) {
  return (
    <div className="flex gap-1 text-xs font-mono">
      {options.map((w) => (
        <motion.button
          key={w}
          onClick={() => {
            playRangeChange();
            onChange(w);
          }}
          whileTap={{ scale: 0.92 }}
          animate={{
            backgroundColor: w === value ? "#9fe870" : "rgba(0,0,0,0)",
            color: w === value ? "#0d0f0c" : "#7d8877",
          }}
          transition={SPRING}
          className="px-2 py-1 rounded"
        >
          {w}
        </motion.button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Implement `DetailPanel`**

Create `frontend/src/components/DetailPanel.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import PlotlyChart from "./PlotlyChart";
import RangeControl from "./RangeControl";
import { SPRING } from "../lib/motion";
import { playDataLanded } from "../lib/sound";

type DetailResponse = {
  name: string;
  kind: "equity" | "carry";
  blurb: string;
  retirement_note: { at: string; reason: string } | null;
  stats: Record<"Sharpe" | "Sortino" | "Calmar" | "MaxDD" | "CAGR" | "Vol", number | null>;
  live_start: string;
  bt_start: string | null;
  available_windows: string[];
  live_equity_chart: { data: unknown[]; layout: Record<string, unknown> };
  backtest_chart: { data: unknown[]; layout: Record<string, unknown> };
  divergence_state: "insufficient" | "ok" | "diverging";
  divergence_detail: string;
  verdict?: string;
  corr_bench?: number | null;
  null_p95?: number | null;
  freq?: string;
  carry_meta?: Record<string, number | null>;
};

function fmt(v: number | null | undefined, kind: "ratio" | "pct" = "ratio") {
  if (v === null || v === undefined) return "—";
  return kind === "ratio" ? v.toFixed(2) : `${(v * 100).toFixed(1)}%`;
}

export default function DetailPanel({ name }: { name: string }) {
  const [data, setData] = useState<DetailResponse | null>(null);
  const [window, setWindow] = useState("ALL");
  // True from a name change until that book's first response lands -- distinguishes
  // "just opened this book" (plays the landed sound) from "changed the range window on
  // a book already open" (RangeControl's own click sound already covers that feedback;
  // playing both would double up).
  const isInitialLoad = useRef(true);

  useEffect(() => {
    setData(null);
    setWindow("ALL");
    isInitialLoad.current = true;
  }, [name]);

  useEffect(() => {
    fetch(`http://localhost:8000/api/books/${name}/detail?window=${window}`)
      .then((res) => res.json())
      .then((body: DetailResponse) => {
        setData(body);
        if (isInitialLoad.current) {
          playDataLanded();
          isInitialLoad.current = false;
        }
      });
  }, [name, window]);

  if (!data) return <p className="text-ink-muted">Loading…</p>;

  const statEntries: [string, number | null][] = [
    ["Sharpe", data.stats.Sharpe], ["Sortino", data.stats.Sortino],
    ["Calmar", data.stats.Calmar], ["Max Drawdown", data.stats.MaxDD],
    ["CAGR", data.stats.CAGR], ["Vol (ann.)", data.stats.Vol],
  ];

  return (
    <motion.div key={name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}>
      <h2 className="text-2xl font-bold text-ink">{name}</h2>
      <p className="text-ink-muted mt-1">{data.blurb}</p>

      {data.retirement_note && (
        <div className="bg-surface rounded-card p-4 mt-4 text-sm">
          Retired {data.retirement_note.at} — {data.retirement_note.reason}
        </div>
      )}

      <div className="grid grid-cols-6 gap-4 mt-6 pb-6 border-b border-white/5">
        {statEntries.map(([label, kind]) => (
          <div key={label}>
            <div className="text-xs text-ink-muted uppercase">{label}</div>
            <div className="text-xl text-ink font-mono tabular-nums">
              {fmt(kind, label === "Max Drawdown" || label === "CAGR" || label === "Vol (ann.)" ? "pct" : "ratio")}
            </div>
          </div>
        ))}
      </div>

      {data.kind === "equity" ? (
        <p className="text-xs text-ink-muted mt-2 font-mono">
          Verdict: {data.verdict} · corr to 60/40: {fmt(data.corr_bench)} · noise floor:{" "}
          {fmt(data.null_p95)} · rebalance {data.freq}
        </p>
      ) : (
        <p className="text-xs text-ink-muted mt-2 font-mono">
          Net yield: {fmt(data.carry_meta?.net_yield, "pct")} · % days positive:{" "}
          {fmt(data.carry_meta?.pct_days_positive, "pct")}
        </p>
      )}

      <div className="mt-6 pt-6 border-t border-white/5">
        <div className="flex items-center justify-between">
          <span className="text-sm text-ink">Live paper equity</span>
          <RangeControl options={data.available_windows} value={window} onChange={setWindow} />
        </div>
        <PlotlyChart figure={data.live_equity_chart} />
      </div>

      <details className="mt-6 pt-6 border-t border-white/5">
        <summary className="text-sm text-ink cursor-pointer">
          Backtest history & live tracking check
        </summary>
        <PlotlyChart figure={data.backtest_chart} />
        <p className="text-xs text-ink-muted mt-2">
          {data.divergence_state}: {data.divergence_detail}
        </p>
      </details>
    </motion.div>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: all `DetailPanel` tests pass, and the full suite (`RowList` + `DetailPanel` +
`plotlyDarkTheme`) passes together.

- [ ] **Step 6: Run `npm run build` to confirm the app compiles end to end**

Run: `cd frontend && npm run build`
Expected: builds cleanly (this is the first point `App.tsx`'s references to `RowList`
and `DetailPanel` from Task 5 actually resolve).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/DetailPanel.tsx frontend/src/components/DetailPanel.test.tsx \
        frontend/src/components/RangeControl.tsx
git commit -m "$(cat <<'EOF'
frontend: DetailPanel + RangeControl -- core detail panel for every book kind

Blurb, 6 stat metrics, verdict/carry-meta caption, live-equity chart
with a real range control (refetches /detail?window=X per the
confirmed "charts are API responses" model), backtest-history +
divergence-status expander. Forks display (not fetch shape) on
data.kind for the equity/carry caption difference. Positions/trade-log/
carry-risk panel are 2b, not here -- the API response already excludes
them. Stats render in the shared mono face with hairline section
dividers, the mount transition uses the shared spring config, and
range-control clicks / a book's first-landed data play the shared UI
sounds, per the visual-language amendment.
EOF
)"
```

---

### Task 8: CI — frontend test step

**Files:**
- Modify: `.github/workflows/tests.yml`

**Interfaces:** none (process step).

- [ ] **Step 1: Add a `frontend-tests` job**

In `.github/workflows/tests.yml`, add a second job after `pytest`:

```yaml
  frontend-tests:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - name: Install
        run: npm ci
      - name: Run tests
        run: npm test
```

- [ ] **Step 2: Verify locally that the exact commands the job runs succeed**

Run: `cd frontend && npm ci && npm test`
Expected: clean install, all tests pass (this mirrors what CI will do; the job itself
can only be verified for real once the PR is pushed in Task 9).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "$(cat <<'EOF'
ci: add a frontend-tests job (npm ci && npm test)

First sub-project with real frontend logic to gate on -- sub-project
1's spec deliberately deferred this until there was something worth
testing. Separate job from pytest (different runtime, own cache key),
not a step tacked onto the existing one.
EOF
)"
```

---

### Task 9: Manual full-stack smoke test, then open the PR

**Files:** none (process step).

- [ ] **Step 1: Run both dev servers**

Terminal 1: `.venv/bin/tradefabe-api`
Terminal 2: `cd frontend && npm run dev`

- [ ] **Step 2: Walk the golden path in a browser**

Open `http://localhost:5173`. Confirm:
- `/books` redirects to a real book's `/books/:name`.
- The row list shows family-grouped rows with sparklines; switching each of the 4 sort
  modes changes the ordering/grouping; unchecking "Show monitor-only" hides
  backtest-DEAD books (if any exist in local state) and re-selects a still-visible book
  if the previously-selected one was hidden.
- Clicking a different row updates the URL and the detail panel, for at least one
  equity book, one retired book (if any), and the carry book (`carry_btc_eth`).
- The 6 stat metrics and verdict/carry-meta caption render.
- Every available range-window option renders a chart with the dark theme applied (no
  white background) — this is the mechanism the pre-plan spike validated; confirm it
  holds for the real integrated app, not just the spike's throwaway harness.
- The backtest-history expander opens and shows a divergence status badge/caption.
- "Up for review" expander appears only if there are eligible books, and lists them.
- Visual-language amendment: the ambient dither texture is visible (subtle, not
  distracting) across the whole canvas; $ figures and stat values render in the mono
  face; row selection and range-control clicks feel snappy/springy rather than a smooth
  fade; clicking a row and clicking a range option each produce a short, quiet sound;
  the "Sound: on/off" toggle in the nav actually mutes them and the choice survives a
  page reload (persisted via `localStorage`).

- [ ] **Step 3: Stop both servers**

Ctrl+C in each terminal.

- [ ] **Step 4: Push the branch and open the PR**

```bash
git push -u origin feat/dashboard-paper-books-2a
gh pr create --title "Dashboard rebuild, sub-project 2a: Paper Books row list + core detail panel" \
  --body-file - <<'EOF'
## Summary
- `dashboard.py` gains the seven remaining `@st.cache_data` loaders `app.py` still held
  (moved undecorated, same precedent as `load_carry_backtest`), plus `book_colors()`,
  `latest_verdicts()`, `available_windows()` extracted from inline duplication, plus a
  `compute_positions=True` flag on `book_panel_data()`.
- `GET /api/books/summary` gains `sort`/`show_monitor_only` query params and a breaking
  (deliberate, per spec) response-shape change: family-grouped by default, flat for the
  other 3 sort modes. New `GET /api/books/up_for_review` and
  `GET /api/books/{name}/detail?window=...`.
- New frontend: `react-router-dom` (`/books/:name`), `RowList` (full parity with
  today's Streamlit card grid — sort/filter/up-for-review/sparklines), `DetailPanel` +
  `RangeControl` (blurb/stats/verdict/live-equity+backtest charts/divergence), a
  `PlotlyChart` wrapper applying a dark-theme layout override validated by a pre-plan
  spike. First Vitest+RTL tests for this repo's frontend, now gated in CI.
- Visual-language amendment (2026-08-06, reverses the Foundation spec's "no audio/
  haptic feedback" line — see spec): mono data typography (IBM Plex Mono, already used
  by the Plotly chart theme), an ambient static dither-texture overlay, a shared
  Framer Motion spring config for tactile motion, and synthesized (no audio files) Web
  Audio UI sounds with a persisted mute toggle.
- Positions/trade-log/carry-risk-panel are explicitly out of scope — slice 2b.

Spec: `docs/superpowers/specs/2026-08-06-dashboard-paper-books-2a-design.md`
Plan: `docs/superpowers/plans/2026-08-06-dashboard-paper-books-2a.md`

## Test plan
- [ ] `.venv/bin/pytest tests/ -n0` — full backend suite green
- [ ] `cd frontend && npm test` — full frontend suite green
- [ ] `.venv/bin/streamlit run app.py` — both views still load, unchanged behavior
- [ ] `.venv/bin/tradefabe-api` + `cd frontend && npm run dev` — manual walkthrough per
      Task 9 of the plan (sort modes, filter, up-for-review, book selection across
      kinds, every range window, dark-theme charts, divergence badge)
EOF
```

- [ ] **Step 5: Wait for CI, then merge**

Run: `gh pr checks <PR-number> --watch`

Once green, verify the head SHA matches:
```bash
gh pr view <PR-number> --json headSha -q .headSha
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
git branch -D feat/dashboard-paper-books-2a
git push origin --delete feat/dashboard-paper-books-2a
```

- [ ] **Step 6: File the issue this PR closes, if one wasn't filed yet, and confirm it closes**

If no issue was filed before starting (per the spec's Process section, one should be
filed for this slice), file it now referencing the spec, then confirm via:
```bash
gh issue view <issue-number> --json state -q .state
```
Expected: `CLOSED` (auto-closed by the PR's `Closes #<N>` if the PR body referenced it
before merge; otherwise close it by hand).
