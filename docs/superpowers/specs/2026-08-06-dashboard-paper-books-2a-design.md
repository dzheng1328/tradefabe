# Dashboard rebuild — Paper Books view, slice 2a (row list + core detail panel) design spec

Status: draft, awaiting Dave's review
Date: 2026-08-06
Related: sub-project 2 of the four-part rebuild decomposed in
`docs/superpowers/specs/2026-08-05-dashboard-foundation-design.md` (sub-project 1,
Foundation, merged via #204). This spec covers only slice 2a; slice 2b (positions,
trade log, carry risk/register panel) is specced separately once 2a lands.

## Why this, why now

Sub-project 1 proved the pipe end to end — theme tokens, `dashboard.py` extraction,
FastAPI skeleton, one placeholder screen fetching `/api/books/summary`. Nothing in it
is a real page yet. Sub-project 2 replaces the placeholder with the actual Paper Books
view: the row list (today's card grid in `render_book_status`) and the strategy detail
panel (`render_strategy_panel`) that appears when a book is selected.

That detail panel is too large for one slice — stats/verdict/live-chart/backtest-chart
is one coherent "is this book behaving as expected" story; positions/trade-log/carry-risk
is a second "what does this book actually hold right now" story that only applies to a
subset of books and forks by kind. Splitting keeps each PR reviewable and lets the
riskiest new mechanism (serializing Plotly figures through a real HTTP boundary into
`react-plotly.js`) get proven before the more complex, book-kind-forked slice is built
on top of it.

**A pre-implementation spike (this session, see below) already de-risked the core
mechanism** — see "Validated via spike" below.

## Scope

### In slice 2a

- **Row list**, full parity with today's `render_book_status`: 4 sort modes (Family /
  Recently added / Return today / Total return), the monitor-only-books filter
  checkbox, the "Up for review" expander, per-book sparkline. Compact row style (not
  the card grid) per the Foundation spec's validated visual direction — one line per
  book: name, family tag, sparkline, $, delta, ~56px/row.
- **Core detail panel**, for every book including the carry book: name + blurb,
  retirement note (if retired), the 6 stat metrics (Sharpe/Sortino/Calmar/MaxDD/
  CAGR/Vol), verdict badge + corr/null-floor/freq caption (equity books) or the 3 carry
  metrics (carry book), live-equity chart with the range-window control (5H/1D/1W/1M/
  3M/1Y/ALL), backtest-history chart + divergence-tracking status inside an expander.
- Book selection is URL-based (`/books/:name`), so a specific book's detail view is
  shareable/bookmarkable and back/forward navigates between books.

### Explicitly out of scope for 2a (deferred to 2b)

- Capital-deployed metrics, positions table, trade log (equity books).
- Risk-monitor panel + risk register (carry book).
- Any change to `state/`, `engine.py`, doctrine logic, or anything the paper-engine
  GitHub Action owns.
- Auth, non-localhost deployment, mobile responsiveness (unchanged from sub-project 1).

`book_panel_data()`'s response shape is designed so 2b is additive to the same
`/api/books/{name}/detail` endpoint, not a new one — see Backend below.

## Validated via spike

Before finalizing this spec, a throwaway spike (not committed — added, tested in a
browser, then reverted) confirmed the sub-project-1 spec's assumption that Plotly
figures "carry over directly... become an API response, not new code." One hardcoded
book's `live_equity_chart()` output was returned via `fig.to_json()` from a temporary
endpoint and rendered with `react-plotly.js` in the existing placeholder screen against
the real dark theme.

**Confirmed:** trace data (line, fill, markers, hover) renders correctly with zero JS
rewrite — the data layer of the "no rewrite" bet holds.

**Found:** the chart's *layout* colors (`paper_bgcolor`, `plot_bgcolor`, gridlines, font
color) come from `dashboard.themed_layout()`, which hardcodes the **old Streamlit
theme's light palette** (`SURF`/`PAGE` = `#fcfcfb`/`#f9f9f7`) — a different, older
palette than the new frontend's dark tokens. Unstyled, the chart rendered as a jarring
white box on the dark canvas. `themed_layout()` cannot simply be recolored dark,
because `app.py` still renders these same charts live with the light theme throughout
sub-projects 1–3 (per CLAUDE.md's dashboard-rebuild note) and must keep working
unmodified.

**Fix, confirmed working in the spike:** override the color-bearing layout keys
client-side, on top of whatever layout the API returns, rather than touching
`dashboard.py`. This becomes a small frontend utility (see Frontend below) — no Python
changes, no risk to `app.py`'s still-live rendering.

## Backend — `src/tradefabe/api/`, `src/tradefabe/dashboard.py`

### `GET /api/books/summary?sort=family|recent|return_today|total_return&show_monitor_only=true|false`

Extends the sub-project-1 endpoint (same route, new query params) rather than adding a
parallel one.
- `sort=family` (default): `{"families": [{"family": str, "label": str, "books": [...]}]}`,
  built from `dashboard.group_books_by_family()`.
- Other three values: `{"books": [...]}` flat, built from `dashboard.sort_books_flat()`.
- Each book row carries what the row list needs beyond today's summary shape: `family`,
  `color` (hex, from the new `book_colors()` helper below), `introduced` (ISO date),
  `return_today`, `monitor_only` (bool), `sparkline` (the last 20 marks' equity
  floats — enough for a compact inline sparkline shape without shipping full history
  in every list paint).

### `GET /api/books/up_for_review`

New. Wraps `dashboard.books_up_for_review()` directly. Separate endpoint (not folded
into `summary`) because it's conditionally rendered — the row list only shows the
expander when the list is non-empty — and has no reason to share a refresh cadence with
the main list.

### `GET /api/books/{name}/detail?window=ALL`

New. Calls `dashboard.book_panel_data(name, ..., compute_positions=False)` (see the
`dashboard.py` change below) and serializes the 2a-relevant subset into JSON:
`blurb`, `retirement_note`, `stats` (6 metrics), verdict fields (`verdict`,
`corr_bench`, `null_p95`, `freq`) or `carry_meta` depending on `kind`,
`live_equity_chart(...).to_json()` (windowed server-side per the confirmed spike
mechanism — a new fetch per window change, not client-side re-slicing), `available_windows`
(the `RANGE_WINDOWS`-derived list valid for this book's live-history span),
`backtest_chart(...).to_json()`, divergence `state`/`detail`, `bt_start`, `live_start`.
`404` if `name` isn't a live book (`psum["book"]` lookup miss).

2b extends this same response with `positions`/`deployment`/`trades`/carry-risk fields
once built — no new endpoint, no versioning scheme needed for that transition.

### `dashboard.py` changes

- **New `book_colors(names: list[str]) -> dict[str, str]`**, extracting the
  `{name: SLOTS[i % len(SLOTS)] for i, name in enumerate(names)}` line currently
  inlined in `app.py`'s `render_paper_books`. Both the row list and the detail-panel
  chart need the same color for the same book — this makes that guarantee explicit
  instead of two call sites independently re-deriving it. `app.py` is updated to call
  this instead of its inline version (no behavior change, pure extraction, same shape
  as sub-project 1's Task 1).
- **`book_panel_data()` gains `compute_positions: bool = True`.** When `False`, skips
  the entire positions-pricing/deployment-math block (the `if kind == "equity" and name
  not in ACCRUAL_ONLY_BOOKS:` block) — `positions_df`/`deployment` come back `None`.
  Default `True` preserves existing behavior for every current caller (`app.py`, the six
  existing test files) with no changes required there. The 2a API endpoint is the only
  caller that passes `False`.

## Frontend — `frontend/src/`

- **Routing:** `react-router-dom` added. `/books` redirects to `/books/:name` for the
  first book in the default (Family-sorted) order — matching today's Streamlit behavior
  where `st.session_state.selected_book` always defaults to `names[0]`, never an empty
  selection. `/books/:name` is list + detail panel, nested under the existing
  "Paper Books" nav stub from sub-project 1.
- **Components:**
  - `RowList` — fetches `/api/books/summary`, owns the sort-mode selector and
    monitor-only checkbox as local state (query params on the fetch), renders the
    family-grouped or flat rows, each row a `<Link to="/books/:name">`. Fetches
    `/api/books/up_for_review` separately and renders the expander only if non-empty.
    Each row renders its `sparkline` array as a tiny inline SVG polyline (no charting
    library needed for a ~40px sparkline).
  - `DetailPanel` — reads `:name` from the route, fetches `/api/books/{name}/detail`,
    re-fetches on window-control change (`?window=X`) or route change. Renders blurb,
    retirement banner, stat grid, verdict/carry-meta row.
  - `RangeControl` — the 5H/1D/.../ALL segmented control, drives `DetailPanel`'s window
    query param. Disabled/hidden options outside the book's live-history span (mirrors
    today's `options = [w for w in (...) if w == "ALL" or span >= RANGE_WINDOWS[w]]`
    logic — server-provided via `available_windows` in the detail response, not
    recomputed in JS).
  - `PlotlyChart` — thin wrapper around `react-plotly.js`. Applies the dark-theme layout
    override confirmed in the spike (`paper_bgcolor`/`plot_bgcolor`/font color/gridline
    color merged on top of the fetched layout) via a small `lib/plotlyDarkTheme.ts`
    helper, so every chart consumer gets the override automatically rather than
    reimplementing it per call site.
  - Backtest-history + divergence status renders inside a collapsible section
    (native `<details>`, styled — no new dependency for the expander behavior itself).
- **New dependencies:** `react-router-dom`, `react-plotly.js` + `plotly.js` (+
  `@types/react-plotly.js`, `@types/plotly.js` as dev deps), `vitest` + `@testing-library/react`
  + `@testing-library/jest-dom` (+ `jsdom` as the test environment) as dev deps.
- Framer Motion (already installed) drives the selected-row highlight transition and the
  detail-panel's mount transition, matching the Foundation spec's plan for this
  sub-project's interactive elements.

## Testing

- **Backend:** extend `tests/test_api_books_summary.py` for the new query params;
  new `tests/test_api_books_up_for_review.py`; new `tests/test_api_book_detail.py`
  (asserts 404 on unknown name, asserts the response shape/keys, asserts
  `compute_positions=False` is actually passed through — e.g. `positions`/`deployment`
  absent from the response); new test for `dashboard.book_colors()`; existing
  `book_panel_data()` tests gain a case for `compute_positions=False`.
- **Frontend (Vitest + RTL, new for this repo's frontend):** `RowList` sort-mode
  switching and monitor-only filtering (mocking `fetch`), `DetailPanel`/`RangeControl`
  window-refetch behavior (mocking `fetch`, asserting the query param changes),
  `plotlyDarkTheme.ts`'s merge function (pure function, easy unit test — asserts it
  overrides the light-theme keys and leaves trace-level `data` untouched).
- **CI:** `tests.yml` gains a frontend step (`npm ci && npm test` in `frontend/`)
  alongside the existing `pytest tests/` — first sub-project with real frontend logic to
  gate on, per sub-project 1's spec noting this was deferred exactly until now.
- **Manual:** both dev servers running, click through sort modes, the monitor-only
  filter, up-for-review expander, select several books of different kinds (equity,
  carry, a retired book if one exists), exercise every range-window option, confirm the
  backtest-history expander and divergence badge render correctly for at least one
  `ALIVE` and one `DEAD` book.

## Process

- Branch: `feat/dashboard-paper-books-2a` off `main`.
- One GitHub issue filed for this slice (2b gets its own issue when it starts).
- PR body: change + test plan, via quoted heredoc, per repo convention.
- `/ship` isn't available to Dave for this project — branch → PR → CI-wait → merge →
  verify → cleanup run by hand, following CLAUDE.md's documented sequence exactly.
- `doctrine-auditor` not needed — no changes to `STRATEGIES.md` or `graveyard.csv`.
