# Dashboard rebuild — Foundation (sub-project 1) design spec

Status: draft, awaiting Dave's review
Date: 2026-08-05
Related: supersedes the incremental "reskin app.py with dark CSS" plan discussed earlier
this session; visual direction validated via the brainstorming visual-companion tool.

## Why this, why now

`app.py`'s `render_book_status()` renders paper books as a family-grouped grid of
`st.metric` cards, 4 per row. At the current roster size that grid — plus the "up for
review" expander above it — consumes roughly half the page before the actual
per-strategy detail panel (`render_strategy_panel()`) even starts, and it only gets worse
as the roster grows. Fixing that started as a CSS reskin (dark canvas, one accent color,
big rounded cards, a compact row list instead of the card grid — all validated via mocked
comparisons this session). But Streamlit re-renders the whole page on every interaction,
which puts a hard ceiling on how tactile the UI can feel — no true per-component
animation, just CSS transitions on a full rerun. Dave chose to go further: move off
Streamlit entirely for a real frontend, rather than fight the framework's ceiling.

**Validated visual direction** (mocked up and picked from side-by-side comparisons):
- Dark canvas, "Wise Lime" accent (`#9fe870`) — closest of three style directions tried
  to the literal Wise-app reference, versus a warmer "Ink & Ember" copper-accent option
  and a cooler "Deep Lab" slate option that were rejected.
- Bold 26px card radius, flat color fields, no shadows anywhere — Wise's own system
  actually uses 24–40px radii and pill buttons, so heavy rounding is on-brand here; a
  tighter 8px alternative was tried and rejected in favor of the bold one.
- Compact row list (one line per book: name, family tag, sparkline, $, delta — ~56px/row)
  replaces the card grid. A horizontal scrollable card-strip alternative was mocked,
  liked, but shelved for a different surface later rather than used here.
- Space Grotesk stays as the display typeface (already used in the current `LAB_CSS`) —
  no third font introduced.
- Motion: Framer Motion for hover/press/select-transition states only. No WebGL, no
  audio/haptic feedback, no scrollytelling — those were explicitly reference-only, not
  requirements, per Dave.

## Sub-project decomposition

The full rebuild is too large for one spec. It's four sub-projects, each with its own
spec → plan → branch → PR, built one at a time:

1. **Foundation** (this spec) — API skeleton + frontend scaffold + theme tokens, one
   proof-of-connection endpoint, no real page yet.
2. **Paper Books view** — the row list + strategy detail panel, real data, real charts.
3. **Research Lab view.**
4. **Desktop app cutover** — repoint `pywebview` at the new frontend's build output
   instead of the Streamlit server, retire `app.py`.

Only #1 is specced in detail here. Issues for #2–4 get filed when their sub-project
starts, not now — CLAUDE.md already flags that hand-maintaining a roadmap ahead of actual
work is how it drifts stale.

## Core architectural decision: extracting dashboard logic out of `app.py`

`app.py` mixes Streamlit rendering (`render_*`, plus `load_*` functions decorated with
`@st.cache_data`) with a second layer of pure data-shaping and chart-building functions
that have **zero** Streamlit calls: `book_panel_data`, `book_family`,
`group_books_by_family`, `sort_books_flat`, `books_up_for_review`,
`book_introduced_dates`, `book_return_today`, `strategy_description`, `retirement_note`,
`_dead_strategy_returns`, `divergence_status`, `trades_frame`, `ann_stats`, `fmt`,
`money`, `fmt_full_dollars`, `signals_cost_bps`, `window_slice`, `padded_range`, plus the
Plotly figure builders `themed_layout`, `live_equity_chart`, `backtest_chart`,
`luck_floor_chart`, `drawdown_chart`, `correlation_heatmap`, `growth_chart`. Six existing
test files (`test_book_panel_data.py`, `test_book_family_grouping.py`,
`test_live_equity_chart.py`, `test_dead_strategy_detail.py`, `test_retirement.py`,
`test_kronos_live.py`) call these directly via `import app`.

CLAUDE.md already requires `engine.py` be the single source of truth for data/sizing/
returns, with `harness.py` importing rather than duplicating it. The same discipline has
to extend to this presentation-data layer, or the new API either reimplements this logic
as a second copy that drifts from `app.py`'s, or the rebuild can't start without first
breaking the still-live Streamlit dashboard.

**Decision:** move the Streamlit-free functions listed above, verbatim, into a new
module `src/tradefabe/dashboard.py`. `app.py` imports them from there (a real import, not
a re-export shim — `app.py` keeps running with unchanged behavior all the way through
sub-projects 1–3). The six test files switch their import from `app` to
`tradefabe.dashboard`, call sites updated to match, no logic changes — this is the one
piece of sub-project 1 that touches existing code, and the PR should read as a pure move.
The new `src/tradefabe/api/` package imports from the same module, so both the legacy UI
and the new one read from one place.

Plotly figure builders carry over directly rather than needing a JS rewrite: a
`go.Figure`'s `.to_dict()` / `.to_json()` is the same trace+layout shape Plotly.js
consumes, so `live_equity_chart()` etc. become an API response, not new code.

`@st.cache_data`-decorated `load_*` functions (e.g. `load_backtest`,
`load_kronos_backtest`) stay in `app.py` — the decorator is Streamlit-specific. The parts
of those functions that just parse a CSV/JSON file are already Streamlit-free bodies
wrapped in a decorator; sub-project 1 only needs `load_paper_state()` (undecorated
already) moved alongside the rest. The API layer adds its own lightweight in-memory TTL
cache where needed later — not required for sub-project 1's one endpoint.

## Sub-project 1 scope

### Backend — `src/tradefabe/api/`

- FastAPI app at `src/tradefabe/api/main.py`. New optional dependency group in
  `pyproject.toml`: `api = ["fastapi", "uvicorn[standard]"]`, mirroring the existing
  `desktop`/`dev` extras pattern. New `[project.scripts]` entry `tradefabe-api` alongside
  the existing `tradefabe-app`.
- One real endpoint: `GET /api/books/summary` — calls `dashboard.load_paper_state()` and
  returns the book list as JSON (name, equity, return, last_run, retired_at). This is the
  proof-of-connection endpoint for this sub-project; the full row-list data contract
  (family tags, sparkline series, etc.) gets specced in sub-project 2, not guessed here.
- CORS allowed for `http://localhost:5173` (Vite dev server) during local dev.
- No auth. This repo's hard rule is paper/local-only — the API only ever binds to
  `localhost`, same trust boundary the Streamlit app already has.

### Frontend — `frontend/`

- Vite + React + TypeScript scaffold (`npm create vite@latest -- --template react-ts`).
- Tailwind CSS configured with the validated tokens as a custom theme (not Tailwind's
  default slate/gray palette):
  - `--bg:#0d0f0c` (near-black, faint olive warmth) / `--surface:#181c15`
  - `--accent:#9fe870` (Wise lime) / `--ink:#f2f5ef` / `--ink-muted:#7d8877`
  - `--radius-card:26px`, flat surfaces, no `box-shadow` anywhere
  - Display font: Space Grotesk, weights 500/600/700/900
- Framer Motion installed; used only for hover/press states and a select-transition on
  this sub-project's one interactive element — nothing more until sub-project 2 needs it.
- One placeholder screen: a shell with a non-functional left-nav stub ("Paper Books" /
  "Research Lab") and a single tile that fetches `/api/books/summary` and renders book
  count + total equity, styled with the theme tokens. This proves the whole pipe — theme,
  fetch, API, data — works; it is not a real page.
- `frontend/package.json`, `tailwind.config`, etc. committed. `frontend/node_modules/`
  and `frontend/dist/` gitignored.

### Explicitly out of scope for sub-project 1

- The real row-list / detail-panel UI (sub-project 2) and Research Lab view (sub-project 3).
- Desktop app repointing / retiring `app.py` (sub-project 4) — `ops/build_app.sh` and the
  `pywebview` entrypoint are untouched; `app.py` keeps serving the live dashboard exactly
  as today throughout sub-projects 1–3.
- Any change to `state/`, `engine.py`, doctrine logic, or anything the paper-engine
  GitHub Action owns.
- Auth, non-localhost deployment, mobile responsiveness.

## Testing

- New: `tests/test_api_books_summary.py` using FastAPI's `TestClient`, asserting the
  endpoint's JSON matches what `dashboard.load_paper_state()` returns directly.
- Existing: the six test files above switch `import app` → `import tradefabe.dashboard as
  dashboard` (or the equivalent direct imports) with call sites updated. No behavior
  change expected — this refactor's only real regression risk, so the PR diff should show
  functions moved, not rewritten.
- Frontend: no test framework yet (Vitest/RTL) — YAGNI for a static proof screen with no
  real interactive logic; add it in sub-project 2 when there's real logic to test.
- CI (`tests.yml`) stays as `pytest tests/` for this sub-project — the frontend has
  nothing worth gating on yet. Revisit adding a frontend build/lint CI step once
  sub-project 2 lands real frontend logic.

## Process

- Branch: `feat/dashboard-foundation` off `main`.
- One GitHub issue filed for this sub-project (not #2–4 yet — see decomposition above),
  added to the roadmap project board.
- PR body: change + test plan, per repo convention, via quoted heredoc.
- `/ship` isn't available to Dave for this project, so the branch → PR → CI-wait → merge
  → verify → cleanup sequence gets run by hand, following CLAUDE.md's documented gotchas
  exactly: verify `state=MERGED` as its own step before any cleanup, never chain the
  branch delete onto the merge command, quoted heredoc (`<<'EOF'`) for the PR body.
- `doctrine-auditor` not needed for this PR — no changes to `STRATEGIES.md` or
  `graveyard.csv`.
