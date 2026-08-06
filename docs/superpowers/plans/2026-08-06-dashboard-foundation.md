# Dashboard Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up sub-project 1 of the dashboard rebuild — extract `app.py`'s Streamlit-free
data/chart layer into `src/tradefabe/dashboard.py`, add a FastAPI skeleton that reads from it,
and scaffold a Vite/React/TS/Tailwind/Framer Motion frontend with the validated dark theme,
proven end-to-end by one placeholder screen that fetches live book data.

**Architecture:** `src/tradefabe/dashboard.py` becomes the single Streamlit-free owner of every
data-shaping/chart-building function currently living in `app.py`. `app.py` imports from it
(unchanged behavior, still the live dashboard). A new `src/tradefabe/api/` FastAPI app imports
from the same module. A new `frontend/` Vite app talks to the API over HTTP. `app.py` is not
retired in this plan — that's sub-project 4.

**Tech Stack:** Python (FastAPI, uvicorn) for the API; Vite + React + TypeScript + Tailwind CSS
+ Framer Motion for the frontend; `plotly.graph_objects` figures serialized to JSON for charts
(same library both sides — Python builds them, Plotly.js renders them, no rewrite).

## Global Constraints

- Never touch `state/`, `engine.py`, doctrine logic, or anything the paper-engine GitHub
  Action owns.
- `app.py` must keep working, unmodified in behavior, through every task in this plan —
  it's the live dashboard until sub-project 4 retires it. (Task 1 below lands the
  extraction, the import rewire, AND the test-monkeypatch fixes together as one task for
  exactly this reason — splitting them would leave `app.py` or the suite broken at a task
  boundary.)
- No Streamlit import (`streamlit`, `st.*`) anywhere in `src/tradefabe/dashboard.py` or
  `src/tradefabe/api/` — that's the entire point of the split.
- Theme tokens (from the approved spec): `--bg:#0d0f0c`, `--surface:#181c15`,
  `--accent:#9fe870`, `--ink:#f2f5ef`, `--ink-muted:#7d8877`, `--radius-card:26px`, flat
  surfaces, no `box-shadow` anywhere, Space Grotesk display font (weights 500/600/700/900).
- Branch: `feat/dashboard-foundation` (already created, holds the approved spec commit).
- Full test suite (`pytest tests/`) must pass at the end of every task.

---

### Task 1: Extract the dashboard layer, rewire `app.py`, fix test monkeypatches

**Files:**
- Create: `src/tradefabe/dashboard.py`
- Modify: `app.py` (functions/constants extracted, then imports rewired)
- Modify: `tests/test_book_family_grouping.py`, `tests/test_dead_strategy_detail.py`
- Test: full existing suite must pass at the end of this task

**Interfaces:**
- Produces: `src/tradefabe/dashboard.py` exporting 34 functions and 20 module constants,
  importable as `from tradefabe import dashboard` or `from tradefabe.dashboard import X`.

This is one task in three parts — extraction, rewire, test fixes — landed together
because the suite can't go green with only one or two of the three done (the rewire
needs the extraction to exist; the test fixes are needed for the suite the rewire's own
verification step runs). Commit as many or as few times internally as makes sense, but
the task isn't done until Step 9 (full suite) passes.

`app.py` currently has two layers tangled together: Streamlit rendering/caching, and pure
data-shaping/Plotly-figure-building code with zero Streamlit calls. Three of the "pure"
functions are decorated with `@st.cache_data` purely for Streamlit's rerun-caching
(`load_carry_backtest`, `_load_generated_ledger`, `_load_pipeline_ledger`) — moving them
means dropping that decorator (their reads are small CSV/JSON files, same cost class as
`load_paper_state()`, which is already deliberately uncached).

#### Part A — extraction

- [ ] **Step 1: Run the extraction script**

Write this to a scratch file and run it once from the repo root. It uses Python's `ast`
module to find each function/constant by name — robust against manual line-number
mistakes, and it self-verifies (asserts every name is found, asserts no `st.` call
survives in what gets written to `dashboard.py`).

```python
# scratch_extract_dashboard.py -- run once, then delete
import ast
import re

FUNC_NAMES = [
    "load_carry_backtest", "load_paper_state", "load_book_json", "ann_stats", "fmt",
    "signals_cost_bps", "money", "_rgba", "themed_layout", "book_panel_data",
    "trades_frame", "window_slice", "padded_range", "live_equity_chart",
    "backtest_chart", "divergence_status", "luck_floor_chart", "drawdown_chart",
    "correlation_heatmap", "growth_chart", "fmt_full_dollars", "book_family",
    "factory_owned_names", "books_up_for_review", "_is_monitor_only",
    "group_books_by_family", "book_introduced_dates", "book_return_today",
    "sort_books_flat", "strategy_description", "retirement_note",
    "_dead_strategy_returns", "_load_generated_ledger", "_load_pipeline_ledger",
]
CONST_NAMES = [
    "ANN", "SURF", "PAGE", "INK", "INK2", "MUTED", "GRID", "SLOTS", "GOOD", "CRIT",
    "BENCH_C", "SPY_C", "DIV", "RANGE_WINDOWS", "MIN_CHART_POINTS", "Y_PAD",
    "REVIEW_AGE_DAYS", "BOOK_FAMILIES", "BOOK_FAMILY", "STRATEGY_DESCRIPTIONS",
]

with open("app.py") as f:
    src = f.read()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)

# ---- locate functions (body span excludes decorators; decorators stripped by design) ----
func_nodes = {}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in FUNC_NAMES:
        func_nodes[node.name] = node
missing = set(FUNC_NAMES) - set(func_nodes)
assert not missing, f"functions not found: {missing}"

# ---- locate top-level constant assignments ----
name_to_span = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        target_names = set()
        for t in node.targets:
            if isinstance(t, ast.Name):
                target_names.add(t.id)
            elif isinstance(t, ast.Tuple):
                target_names.update(e.id for e in t.elts if isinstance(e, ast.Name))
        for n in target_names & set(CONST_NAMES):
            name_to_span[n] = (node.lineno, node.end_lineno)
missing_c = set(CONST_NAMES) - set(name_to_span)
assert not missing_c, f"constants not found: {missing_c}"
uniq_const_spans = sorted(set(name_to_span.values()))

# ---- build dashboard.py body (constants first in source order, then functions) ----
body_parts = []
for (s, e) in uniq_const_spans:
    block = "".join(lines[s - 1:e]).rstrip("\n")
    body_parts.append((s, block))
for name, node in func_nodes.items():
    block = "".join(lines[node.lineno - 1:node.end_lineno]).rstrip("\n")
    assert not re.search(r"\bst\.[a-zA-Z_]", block), f"{name}: still references streamlit"
    body_parts.append((node.lineno, block))
body_parts.sort(key=lambda t: t[0])
dashboard_body = "\n\n\n".join(p[1] for p in body_parts) + "\n"

header = '''"""tradefabe.dashboard -- Streamlit-free data-shaping and chart-building layer for
the lab dashboard. app.py's render_* functions and the FastAPI layer (src/tradefabe/api/)
both import from here; this module has no Streamlit calls, mirroring how harness.py
imports engine.py rather than keeping a private copy of doctrine math.
"""
import json
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from tradefabe import factory
from tradefabe.kronos import KRONOS_OOS_START
from tradefabe.pricing import NON_PRICED as ACCRUAL_ONLY_BOOKS
from tradefabe.paths import REPO_ROOT, ARTIFACTS

BASE = str(REPO_ROOT)
ART = str(ARTIFACTS)

'''
with open("src/tradefabe/dashboard.py", "w") as f:
    f.write(header + dashboard_body)

# ---- remove the same content from app.py (decorator-inclusive for the 3 that had one) ----
removals = list(uniq_const_spans)
for name, node in func_nodes.items():
    start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    removals.append((start, node.end_lineno))
for (s, e) in sorted(removals, reverse=True):
    del lines[s - 1:e]
with open("app.py", "w") as f:
    f.writelines(lines)

print(f"moved {len(func_nodes)} functions, {len(uniq_const_spans)} constant blocks")
```

Run: `python3 scratch_extract_dashboard.py`
Expected output: `moved 34 functions, 20 constant blocks`

- [ ] **Step 2: Delete the scratch script**

```bash
rm scratch_extract_dashboard.py
```

- [ ] **Step 3: Verify `dashboard.py` is syntactically valid and Streamlit-free**

Run: `python3 -c "import ast; ast.parse(open('src/tradefabe/dashboard.py').read())" && grep -c streamlit src/tradefabe/dashboard.py`
Expected: no syntax error, and the grep prints `0` (no match — `grep -c` prints the
count; its own exit code 1 on zero matches is fine here, just confirm the printed count
is `0`).

At this point `app.py` will NOT run (its imports are stale) — that's expected and fixed
in Part B below, within this same task, before anything is committed.

#### Part B — rewire `app.py`'s imports

- [ ] **Step 4: Replace the import block**

Find the import lines (originally):
```python
import json
import os
import numpy as np
import pandas as pd
import streamlit as st
from tradefabe import risk_register, factory
# Constant only -- kronos.py imports torch LAZILY (inside predictor()), so this costs the
# dashboard nothing and does not require the [kronos] extra to be installed.
from tradefabe.kronos import KRONOS_OOS_START
from tradefabe.pricing import NON_PRICED as ACCRUAL_ONLY_BOOKS
import plotly.graph_objects as go
```

Replace with:
```python
import json
import os
import numpy as np
import pandas as pd
import streamlit as st
from tradefabe import risk_register, factory
from tradefabe.pricing import NON_PRICED as ACCRUAL_ONLY_BOOKS
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
)
```

`KRONOS_OOS_START` and `plotly.graph_objects as go` are dropped — nothing left in
`app.py` calls either directly (both only appeared inside functions that just moved).
`factory` stays imported directly (a test fixture reaches `app.factory` to monkeypatch
promotion-registry paths — `tradefabe.factory` is a singleton module object, so patching
it through `app.factory` and through `dashboard.factory` mutates the same object; no
change needed there).

- [ ] **Step 5: Confirm no leftover blank-block artifacts**

Step 1's deletions may have left 2-3 consecutive blank lines where a constant block used
to sit between imports and `st.set_page_config(...)`. Run: `sed -n '1,25p' app.py` and
collapse any run of 3+ blank lines down to 2 (standard PEP 8 spacing), by hand.

#### Part C — fix the test files whose monkeypatches moved

`app.book_family` and `app.strategy_description` work unchanged after Parts A/B —
`app.py` imports the real function objects from `dashboard.py`, so calling them via
`app.book_family(...)` calls the exact same code as `dashboard.book_family(...)`. But four
tests monkeypatch `_load_generated_ledger`/`_load_pipeline_ledger` — the loaders
`book_family`/`strategy_description` call *internally* — expecting the patch to take
effect. A patched name only affects lookups in the module it was patched *on*:
`monkeypatch.setattr(app, "_load_generated_ledger", ...)` rebinds `app`'s own copy of that
name, but `book_family` now lives in `dashboard.py` and resolves `_load_generated_ledger`
via `dashboard`'s namespace, not `app`'s — so the patch silently stops working. These four
call sites need to target `dashboard` instead. (This is different from the `app.factory`
case in Step 4 above — `factory` is a shared *module object*, and patching one of its
attributes mutates the object everyone holds a reference to; `_load_generated_ledger` is a
*function name binding*, which is per-module and does not propagate.) Without this part,
Step 9's full-suite run below fails on exactly these four tests.

- [ ] **Step 6: Add the `tradefabe.dashboard` import to `tests/test_book_family_grouping.py`**

Find the existing `import app` near the top of the file and add directly below it:
```python
import tradefabe.dashboard as dashboard
```

Then find:
```python
def test_book_family_resolves_a_generated_name_via_the_ledger_fallback(monkeypatch):
    # ...
    # parameter is drawn fresh each cycle) -- must resolve via generated_templates.csv.
    monkeypatch.setattr(app, "_load_generated_ledger",
                        lambda: {"tsmom_gen_147d": {"family": "A", "rationale": "..."}})
    assert app.book_family("tsmom_gen_147d") == "A"
```

Replace `monkeypatch.setattr(app, ...)` with `monkeypatch.setattr(dashboard, ...)`,
leaving the assertion on `app.book_family(...)` as-is (it's still the same function
object):
```python
    monkeypatch.setattr(dashboard, "_load_generated_ledger",
                        lambda: {"tsmom_gen_147d": {"family": "A", "rationale": "..."}})
    assert app.book_family("tsmom_gen_147d") == "A"
```

- [ ] **Step 7: Add the same import to `tests/test_dead_strategy_detail.py`**

Find the existing `import app` near the top and add:
```python
import tradefabe.dashboard as dashboard
```

Then find each of these three tests and change `monkeypatch.setattr(app, ...)` to
`monkeypatch.setattr(dashboard, ...)`, leaving every assertion unchanged. Use `Read` on
the actual file first to get each test's exact current body — only the
`monkeypatch.setattr` target changes, nothing else:

```python
def test_strategy_description_resolves_a_generated_name_via_the_ledger_fallback(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_generated_ledger", lambda: {...})
    assert app.strategy_description("tsmom_gen_147d") == "Trend (generated): sign of the trailing 147-day return."


def test_book_family_resolves_a_pipeline_name_via_the_ledger_fallback(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_pipeline_ledger", lambda: {...})
    assert app.book_family("rp_pair_zscore_GLD_SLV_60_2p0_4p0") == "O"


def test_strategy_description_resolves_a_pipeline_name_via_the_ledger_fallback(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_pipeline_ledger", lambda: {...})
    assert app.strategy_description("rp_pair_zscore_GLD_SLV_60_2p0_4p0") == "some rationale text"
```

(`{...}` above stands for each test's existing lambda body, unchanged — copy it verbatim
from the file, only swap `app` → `dashboard` in the `monkeypatch.setattr` call itself.)

#### Part D — verify and commit

- [ ] **Step 8: Manual smoke test**

Run: `.venv/bin/streamlit run app.py` and confirm the dashboard loads both views (Paper
Books, Research Lab) without a traceback in the terminal. Stop the server (Ctrl+C) once
confirmed — this is a manual check, not part of CI.

- [ ] **Step 9: Run the full test suite**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all tests pass, same as before this task started. This is the real
verification gate for the whole task — if anything in Parts A-C was missed, an
`ImportError`, `AttributeError`, or test failure surfaces here.

- [ ] **Step 10: Commit**

One commit is fine, since the task isn't independently valid until all three parts land
together:

```bash
git add src/tradefabe/dashboard.py app.py tests/test_book_family_grouping.py tests/test_dead_strategy_detail.py
git commit -m "$(cat <<'EOF'
dashboard.py: extract Streamlit-free data/chart layer from app.py

Mechanical move via an AST-based script (functions + constants list
recoverable from git show on this commit). app.py rewired to import
everything back -- same behavior, still the live dashboard. Two test
files' monkeypatches retargeted from app to tradefabe.dashboard, since
book_family()/strategy_description() now resolve _load_generated_ledger/
_load_pipeline_ledger in dashboard's namespace, not app's. Full suite
green, dashboard manually smoke-tested.
EOF
)"
```

---

### Task 2: Add the `api` extra and FastAPI skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/tradefabe/api/__init__.py`
- Create: `src/tradefabe/api/main.py`
- Test: `tests/test_api_books_summary.py`

**Interfaces:**
- Consumes: `tradefabe.dashboard.load_paper_state()` (Task 1).
- Produces: `GET /api/books/summary` — JSON list of
  `{book, equity, return, last_run, retired_at}`.

- [ ] **Step 1: Add the `api` optional-dependency group**

In `pyproject.toml`, find:
```toml
[project.optional-dependencies]
desktop = ["pywebview"]
dev = ["pytest", "pytest-xdist", "pyyaml"]
```

Add a new line directly after `dev`:
```toml
api = ["fastapi", "uvicorn[standard]"]
```

- [ ] **Step 2: Add the `tradefabe-api` script entry**

Find:
```toml
[project.scripts]
tradefabe = "tradefabe.cli:main"
tradefabe-app = "tradefabe.desktop:main"
```

Add a third line:
```toml
tradefabe-api = "tradefabe.api.main:run"
```

- [ ] **Step 3: Install the new extra**

Run: `.venv/bin/pip install -e ".[dev,desktop,api]"`
Expected: fastapi and uvicorn install cleanly.

- [ ] **Step 4: Create `src/tradefabe/api/__init__.py`**

```python
"""tradefabe.api -- thin FastAPI read layer over tradefabe.dashboard.

No business logic lives here: every response is built from tradefabe.dashboard /
tradefabe.engine data, so the API and the (still-live) Streamlit app read from one
place. Local-only -- binds to localhost, no auth, same trust boundary the paper-only
hard rule already gives the Streamlit app.
"""
```

- [ ] **Step 5: Create `src/tradefabe/api/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradefabe import dashboard

app = FastAPI(title="tradefabe dashboard API")

# Vite's dev server -- the only origin that ever calls this locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/books/summary")
def books_summary():
    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        return []
    return psum.to_dict(orient="records")


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
```

- [ ] **Step 6: Write the test**

Create `tests/test_api_books_summary.py`:

```python
from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_books_summary_matches_load_paper_state():
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200

    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        assert resp.json() == []
    else:
        assert resp.json() == psum.to_dict(orient="records")


def test_books_summary_is_a_list_of_dicts_with_expected_keys():
    client = TestClient(app)
    body = client.get("/api/books/summary").json()
    if not body:
        return  # no paper state in this environment -- nothing more to assert
    row = body[0]
    for key in ("book", "equity", "return", "last_run"):
        assert key in row
```

- [ ] **Step 7: Run the test**

Run: `.venv/bin/pytest tests/test_api_books_summary.py -v`
Expected: both tests pass (the first test is a tautology by construction — it's a
regression guard, not proof the endpoint is "correct" in isolation, since it calls the
same function it's asserting against; the second test's key-presence check is the one
that would catch a real shape regression).

- [ ] **Step 8: Run the full suite once more**

Run: `.venv/bin/pytest tests/ -n0`
Expected: all pass, including the two new API tests.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src/tradefabe/api/ tests/test_api_books_summary.py
git commit -m "$(cat <<'EOF'
api: FastAPI skeleton with one endpoint, GET /api/books/summary

New optional `api` extra (fastapi, uvicorn) and `tradefabe-api` console
script. The one endpoint wraps tradefabe.dashboard.load_paper_state() --
proof the API/dashboard-layer split works end to end before the frontend
scaffold lands.
EOF
)"
```

---

### Task 3: Scaffold the `frontend/` Vite + React + TS + Tailwind app

**Files:**
- Create: `frontend/` (Vite scaffold — package.json, tsconfig, index.html, src/)
- Create: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`
- Modify: `.gitignore`

**Interfaces:**
- Produces: a themed, empty Vite app running at `http://localhost:5173`.

- [ ] **Step 1: Scaffold Vite**

Run from the repo root:
```bash
npm create vite@latest frontend -- --template react-ts
```

- [ ] **Step 2: Install dependencies, including Tailwind and Framer Motion**

```bash
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npm install framer-motion
npx tailwindcss init -p
cd ..
```

- [ ] **Step 3: Configure Tailwind's content globs**

In `frontend/tailwind.config.js`, replace the generated file's `content` array:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d0f0c",
        surface: "#181c15",
        accent: "#9fe870",
        ink: "#f2f5ef",
        "ink-muted": "#7d8877",
      },
      borderRadius: {
        card: "26px",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
      },
      boxShadow: {
        none: "none",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: Wire Tailwind into the CSS entry point**

Replace the full contents of `frontend/src/index.css` with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;900&display=swap');

body {
  background-color: #0d0f0c;
  color: #f2f5ef;
  font-family: 'Space Grotesk', sans-serif;
}
```

- [ ] **Step 5: Verify the dev server boots with the theme applied**

Run: `cd frontend && npm run dev` (leave running), then in a browser confirm
`http://localhost:5173` shows the default Vite template on a dark (`#0d0f0c`) background
in the Space Grotesk font. Stop the server (Ctrl+C) once confirmed.

- [ ] **Step 6: Gitignore frontend build artifacts**

In `.gitignore`, add a new section:
```
# frontend (Vite/React) -- build output and deps, not source
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 7: Commit**

```bash
git add frontend/ .gitignore
git commit -m "$(cat <<'EOF'
frontend: scaffold Vite + React + TS + Tailwind + Framer Motion

Theme tokens wired into tailwind.config.js and index.css match the
approved spec (near-black bg, Wise-lime accent, 26px card radius, flat
surfaces, Space Grotesk). No real UI yet -- next commit adds the one
placeholder screen that proves the API connection.
EOF
)"
```

*(`frontend/node_modules/` and `frontend/dist/` are gitignored — the `git add frontend/`
above only picks up source files: `package.json`, `tailwind.config.js`, `src/`, etc.)*

---

### Task 4: Placeholder screen wired to `/api/books/summary`

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET http://localhost:8000/api/books/summary` (Task 2).

- [ ] **Step 1: Replace `frontend/src/App.tsx`**

```tsx
import { useEffect, useState } from "react";
import { motion } from "framer-motion";

type Book = {
  book: string;
  equity: number;
  return: number;
  last_run: string;
  retired_at: string | null;
};

export default function App() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/books/summary")
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then(setBooks)
      .catch((err) => setError(String(err)));
  }, []);

  const totalEquity = books?.reduce((sum, b) => sum + b.equity, 0) ?? 0;

  return (
    <div className="min-h-screen flex">
      <nav className="w-56 border-r border-white/5 p-6 text-sm text-ink-muted">
        <div className="text-ink font-bold mb-6">tradefabe</div>
        <div className="mb-2">Paper Books</div>
        <div>Research Lab</div>
      </nav>
      <main className="flex-1 p-10">
        {error && <p className="text-red-400">Failed to load: {error}</p>}
        {!books && !error && <p className="text-ink-muted">Loading…</p>}
        {books && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="bg-surface rounded-card p-8 max-w-sm"
          >
            <div className="text-ink-muted text-xs uppercase tracking-wide mb-2">
              Books live
            </div>
            <div className="text-3xl font-black mb-4">{books.length}</div>
            <div className="text-ink-muted text-xs uppercase tracking-wide mb-2">
              Total equity
            </div>
            <div className="text-3xl font-black">
              ${totalEquity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </motion.div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Run both servers and verify the full pipe end to end**

Terminal 1: `.venv/bin/tradefabe-api` (or `.venv/bin/python -m tradefabe.api.main` if the
console script isn't picked up — the `run()` function starts uvicorn on port 8000).

Terminal 2: `cd frontend && npm run dev`

Open `http://localhost:5173` in a browser. Expected: a dark page with a nav stub on the
left and, on the right, a lime-radius card showing "Books live" (a real count) and "Total
equity" (a real dollar figure), sourced from `state/paper/summary.csv` through the FastAPI
endpoint. If `state/paper/` is empty in this environment, expect the "Books live" count to
be `0` and equity `$0` rather than an error — that's `load_paper_state()`'s existing
`(None, None)` empty-state path, handled by the `books ?? []` fallback above.

Stop both servers (Ctrl+C in each terminal) once confirmed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "$(cat <<'EOF'
frontend: placeholder screen proving the API/theme/fetch pipe works

Nav stub + one themed card fetching GET /api/books/summary, rendering
book count and total equity. Not a real page -- sub-project 2 replaces
this with the actual row-list + detail-panel view. Manually verified
against a running tradefabe-api + npm run dev.
EOF
)"
```

---

### Task 5: Open the PR

**Files:** none (process step)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/dashboard-foundation
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "Dashboard rebuild, sub-project 1: Foundation (React/FastAPI scaffold)" \
  --body-file - <<'EOF'
Closes #203.

## Summary
- Extracts `app.py`'s Streamlit-free data/chart layer into `src/tradefabe/dashboard.py`
  (34 functions + 20 constants, mechanical move via an AST-based script — see individual
  commits). `app.py` imports from it and keeps working unmodified as the live dashboard.
- New `src/tradefabe/api/` — FastAPI skeleton, one endpoint (`GET /api/books/summary`),
  new `api` optional-dependency group, `tradefabe-api` console script.
- New `frontend/` — Vite + React + TS + Tailwind (dark/lime/26px-radius theme tokens from
  the approved spec) + Framer Motion, one placeholder screen proving the fetch → API →
  `tradefabe.dashboard` pipe works end to end.

Spec: `docs/superpowers/specs/2026-08-05-dashboard-foundation-design.md`

## Test plan
- [ ] `.venv/bin/pytest tests/ -n0` — full suite green, including the two new API tests
- [ ] `.venv/bin/streamlit run app.py` — both views (Paper Books, Research Lab) still load
- [ ] `.venv/bin/tradefabe-api` + `cd frontend && npm run dev` — placeholder screen shows a
      real book count and total equity from `state/paper/summary.csv`
EOF
```

- [ ] **Step 3: Wait for CI, then merge**

Run: `gh pr checks <PR-number> --watch`

Once green, verify the head SHA matches:
```bash
gh pr view <PR-number> --json headSha -q .headSha
git rev-parse HEAD
```

Then, per this repo's documented merge sequence (never chain the branch delete onto the
merge command):
```bash
gh pr merge <PR-number> --squash
gh pr view <PR-number> --json state,mergedAt   # must print MERGED before anything below
```

Once `state` prints `MERGED` as its own step:
```bash
git checkout main
git pull
git branch -D feat/dashboard-foundation
git push origin --delete feat/dashboard-foundation
```

- [ ] **Step 4: Update the issue and project board**

Issue #203 closes automatically via the PR's `Closes #203`. Confirm:
```bash
gh issue view 203 --json state -q .state
```
Expected: `CLOSED`.
