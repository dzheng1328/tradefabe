# Dashboard rebuild — Research Lab view + auto-add verification, design spec

Status: draft, pending Dave's review
Date: 2026-08-13
Related: sub-project 3 of the four-part rebuild decomposed in
`docs/superpowers/specs/2026-08-05-dashboard-foundation-design.md` (sub-project 1, Foundation,
merged via #204). Slice 2a merged via #206/#209/#210/#211. Slice 2b (positions/trade-log/
carry-risk) merged via #215. Explicitly deferred by 2b's own spec: "Research Lab view (sub-project
3 ... — separate spec)."

## Why this, why now

Dave asked whether the research pipeline was still adding strategies — it is (`pipeline daily`
has run every day through 2026-08-13, appending real verdicts to `graveyard.csv`), but the new
dashboard has no surface to show that. `app.py`'s Streamlit `render_research_lab` is the only
place that activity is visible today. This sub-project ports it, and closes the loop Dave named
as the actual priority: **a newly-promoted or pipeline-ALIVE strategy must show up in the new
dashboard with no hand-wiring per strategy.**

Streamlit stays running as a fallback per Dave's explicit call (not retired, not the desktop
app's target changing) — this sub-project makes the new dashboard the one used day-to-day, it
does not remove the old one.

## Scope

### In this sub-project

1. **Research Lab page**, full functional parity with `render_research_lab` +
   `render_strategy_detail`: eyebrow stats, OOS growth-of-$1 chart, verdicts ledger table,
   per-strategy detail (any graveyard entry, alive or dead), luck-floor null distribution,
   drawdown/underwater chart, correlation heatmap, and the interactive piggyback-sleeve
   simulator. Same underlying data and chart math (`dashboard.py`), new frontend surface.
2. **Auto-add verification.** Prove, not assert, that a newly-promoted book requires zero
   frontend/API code changes to appear in Paper Books + Research Lab. `book_panel_data()` already
   resolves any book generically (cascades through `full_returns.csv` →
   `piggyback_returns.csv` → `factory_returns.csv` → `hourly_returns.csv` → `kronos_returns.csv`
   → `pipeline_returns.csv`, none of it keyed by a hardcoded name list), and `books_summary`
   reads `load_paper_state()` dynamically — so this is expected to already work. This
   sub-project adds the regression test that pins it down, and closes any gap the test finds.

### Explicitly out of scope

- Retiring or modifying `app.py` / Streamlit in any way.
- Changing the desktop app's target (stays on `localhost:8501`).
- Any change to `state/`, `engine.py`, doctrine logic, or anything the paper-engine/pipeline
  GitHub Actions own.
- A **new category** of persisted-curve source (an 8th CSV) — out of scope unless the factory/
  pipeline actually grows one; not needed to satisfy "no hand-wiring per strategy" today.
- Auth, non-localhost deployment, mobile responsiveness (unchanged from prior sub-projects).

## Frontend layout (decided via Lavish review, 2026-08-13)

- **Page structure: tabbed sections** at `/research` — Overview / Verdicts / Strategy Detail /
  Diagnostics / Piggyback Lab. Each tab lazy-fetches its own endpoint on first activation, not
  on page mount — the correlation heatmap and piggyback lab in particular have no reason to load
  before a user clicks into them.
- **Strategy selector: one global, sticky selection** shared by the Strategy Detail and
  Diagnostics tabs (luck-floor + drawdown pickers). Selecting a strategy in the Verdicts table
  sets it too. Matches how the Paper Books detail panel already works — one selected entity
  drives everything on the right — rather than Streamlit's three independent selectboxes.
- **Verdicts table: dense, sortable, all 9 columns** (strategy, freq, Sharpe, Sortino, Calmar,
  MaxDD, corr_bench, null_p95, verdict), matching Streamlit's dataframe. `tf-badge`-style
  colored verdict cells (accent green ALIVE / red DEAD). Row click sets the shared selector.
- **Piggyback Lab: controls in a left column (1/3 width), chart + stat deltas in a right column
  (2/3 width)** — matches Streamlit's existing `lc`/`rc` split. Slider (0–50%) + sleeve
  multiselect stay visible while reading the comparison chart.

## Backend — new endpoints in `src/tradefabe/api/main.py`

All five reuse `dashboard.py`'s existing chart/stat functions as the single source of truth —
no chart math gets duplicated in TypeScript, following the same pattern `book_detail` already
established (`json.loads(chart.to_json())`).

- **`GET /api/research/overview`** — one-shot payload: eyebrow meta (`meta['source']`,
  `meta['start']`/`meta['end']`, `meta['oos_start']`, `meta['n_assets']`), summary stats (tested/
  alive/dead counts, `null_bars['M']` luck-floor p95, best strategy + its Sharpe, 60/40 bench
  Sharpe), the growth-of-$1 chart (all strategies + `bench_6040` + `spy`, via `growth_chart`),
  and the correlation heatmap (via `correlation_heatmap`). Built from `load_backtest()` +
  `latest_verdicts(gy)`, same as Streamlit's entry point.
- **`GET /api/research/verdicts`** — the full ledger table rows (`gy_last.reset_index()[[...]]`
  columns already selected in `render_research_lab`), for the Verdicts tab.
- **`GET /api/research/strategy/{name}`** — per-strategy detail: blurb (`strategy_description`),
  verdict badge, 6-stat row (or the 4-stat fallback when `_dead_strategy_returns` returns `None`
  — mirrors the existing `else` branch in `render_strategy_detail` verbatim, including its
  caption pointing at `research/insider_backtest.py`), backtest chart. Reuses
  `_dead_strategy_returns(name, oos, piggy, factory_bt, hourly_bt, kronos_bt, pairs_bt,
  pipeline_bt)` so any graveyard entry works, not just live books. `404` for an unknown name,
  matching `book_detail`'s existing convention.
- **`GET /api/research/luck_floor?strategy=...`** — null-distribution chart for one strategy.
  `dashboard.py` already detects which artifact shape is on disk (per-strategy vs. legacy
  per-frequency `{M,W,D}`); the endpoint takes an optional `freq=...` alternative for the legacy
  shape, mirroring the Streamlit branch precisely rather than dropping old-artifact support.
- **`GET /api/research/drawdown?pick=...`** — underwater chart for one strategy, `"60/40"`, or
  `"SPY"` (same three choices `render_research_lab`'s selectbox offers).
- **`GET /api/research/piggyback?sleeve=x,y&weight=30`** — recomputes the blended stats (Sharpe/
  Calmar/MaxDD deltas vs. 60/40 alone) + growth chart server-side per request, same shape as the
  Streamlit slider's live recompute. `sleeve` is a comma-separated strategy list; `weight` an
  integer 0–50.

All numeric fields routed through the existing `_finite_or_none` / `_deep_finite` NaN-safety
helpers, same discipline as every other endpoint in `main.py`.

## Frontend — `frontend/src/`

New route `/research`, added to `App.tsx`'s `<Routes>` alongside the existing `/books/*` routes.
Nav already has a "Research Lab" link (`Nav.tsx`) that currently points nowhere real — this
sub-project wires it to the new route.

New components, one per tab, each independently testable against mock JSON:

- **`ResearchOverview.tsx`** — eyebrow stat row (reuses `StatTile`) + growth chart
  (`PlotlyChart`, already generic) + correlation heatmap.
- **`VerdictsTable.tsx`** — the dense sortable table. Column sort is client-side (data is a
  single small payload, no pagination needed at 139-ish rows — same order of magnitude
  Streamlit already renders with `st.dataframe` without a server-side sort). Row click calls a
  shared-selection setter passed down from the page.
- **`StrategyDetail.tsx`** — blurb, verdict badge + corr/null-floor/freq caption line, stat row,
  backtest chart. Reads the shared selected-strategy state; renders an empty state ("pick a
  strategy from Verdicts") when nothing is selected yet.
- **`Diagnostics.tsx`** — luck-floor chart + drawdown chart (both driven by the shared
  selection, drawdown additionally offering "60/40"/"SPY").
- **`PiggybackLab.tsx`** — left column: `<input type="range">` (0–50, matches Streamlit's
  5-step slider) + a strategy multiselect (checkboxes, matching the existing `RowList` sort
  control's native-select styling rather than introducing a new multiselect dependency); right
  column: 3 `StatTile`s (Sharpe/Calmar/MaxDD deltas) + comparison growth chart. Debounced
  fetch on slider drag (250ms), matching the responsiveness of Streamlit's own recompute-on-
  release feel without a request per pixel of drag.
- **`ResearchLab.tsx`** — the page shell: tab bar (native styling matching `RowList`'s existing
  `Sort by` control language, not a new tab-component dependency) + shared selected-strategy
  state + lazy per-tab fetch-on-activation.

**Styling:** same tokens as every prior slice — `bg`/`surface`/`accent`/`ink`/`ink-muted` from
`tailwind.config.js`, Space Grotesk display + IBM Plex Mono numerics, `tf-badge`-equivalent
verdict pills (`text-accent`/`text-red-400` on `bg-accent/10`-style backgrounds, matching
`RowList.tsx`'s existing `delta >= 0` accent/red-400 split rather than inventing new colors).

## Auto-add verification

- **New backend test** (`tests/test_api_research_autoadd.py` or extending an existing API test
  file): write a synthetic row into a scratch copy of `factory_returns.csv` /
  `state/paper/summary.csv` for a strategy name that does not otherwise exist in the fixture
  data, call `books_summary()` and `book_detail(name)`, assert the new name appears with no
  code path treating it specially. This is a regression test for the *existing* generic
  resolution, not new production code — if it fails, the fix (not this spec) determines what's
  actually missing.
- **Manual check**: after the Research Lab page ships, trigger `gh workflow run "paper engine"
  -f job=factory` (with Dave's confirmation per `workflow-watch`'s trigger rule) and confirm any
  newly-promoted book appears in both Paper Books and Research Lab without a restart or deploy —
  the FastAPI dev server's `reload=True` and Vite's HMR mean a running dev session should pick
  it up from disk on the next fetch, not even a page reload's worth of staleness beyond normal
  polling.

## Testing

- **Backend:** one test per new endpoint in `tests/test_api_research.py` — `overview` (stats +
  chart JSON shape), `verdicts` (row count matches `gy_last`, colors/verdict field present),
  `strategy/{name}` (found alive book, found dead-only graveyard entry, 404 on unknown),
  `luck_floor` (per-strategy shape and legacy per-frequency shape both handled), `drawdown`
  (strategy pick + "60/40" + "SPY"), `piggyback` (weight/sleeve recompute matches a hand-computed
  expected blend for a fixed fixture). Plus the auto-add regression test above.
- **Frontend (Vitest + RTL):** one test file per new component, mock-JSON-fed per the existing
  2a/2b pattern — `ResearchOverview`, `VerdictsTable` (sort + row-click-sets-selection),
  `StrategyDetail` (populated + empty-selection state), `Diagnostics`, `PiggybackLab` (slider
  debounce, multiselect), `ResearchLab` (tab switch triggers lazy fetch, not eager).
- **CI:** unchanged (`tests.yml` already runs both `pytest tests/` and `npm test`).
- **Manual:** both dev servers running; walk all five tabs, confirm chart parity against
  `localhost:8501`'s Research Lab for the same data (same Sharpe numbers, same verdict colors),
  exercise the piggyback slider end to end, then the auto-add manual check above.

## Process

- Branch: `feat/dashboard-research-lab`, off `main`.
- One GitHub issue filed for this sub-project before implementation starts.
- PR body: change + test plan, via quoted heredoc, per repo convention. Likely two PRs given
  scope (backend endpoints, then frontend page) or one — decided at planning time based on how
  cleanly they split; either way each PR gets its own test plan and green CI before merge.
- `/ship` isn't available to Dave for this project — branch → PR → CI-wait → merge → verify →
  cleanup run by hand, following CLAUDE.md's documented sequence exactly.
- `doctrine-auditor` not needed — no changes to `STRATEGIES.md` or `graveyard.csv`; this is a
  read-only view of data those files already contain.
