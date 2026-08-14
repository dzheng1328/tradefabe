# Dashboard rebuild — Paper Books view, slice 2b (positions, trade log, carry risk) design spec

Status: approved by Dave
Date: 2026-08-13
Related: sub-project 2 of the four-part rebuild decomposed in
`docs/superpowers/specs/2026-08-05-dashboard-foundation-design.md` (sub-project 1, Foundation,
merged via #204). Slice 2a (row list + core detail panel) merged via #206, #209, #210, #211.
This spec covers slice 2b, explicitly deferred by 2a: "Positions/trade-log/carry-risk-panel are
explicitly out of scope -- slice 2b."

## Why this, why now

2a shipped the row list and the "is this book behaving as expected" half of the detail panel:
blurb, stats, verdict, live-equity chart, backtest-history/divergence. It deliberately left out
the "what does this book actually hold right now" half, which forks by book kind and needed 2a's
positions-pricing plumbing (`book_panel_data(compute_positions=...)`) proven inert first. That
plumbing already exists and is already exercised by `app.py`'s live Streamlit rendering — 2b
ports it to the API/frontend, it does not design new backend math.

## Scope

### In slice 2b

- **Equity books:** capital-deployed stats (cash / gross / net / total equity, each as a $ and
  a % of equity), the unpriced-positions warning, the short-funded/vol-targeting caption, a
  current-positions table (ticker/units/last price/value/weight), and a trade log (fill-by-fill:
  when/ticker/side/Δunits/fill price/notional/position-after) with its footer caption (fill
  count, cost bps, "capped at 500" note).
- **Delta-neutral carry books** (`ACCRUAL_ONLY_BOOKS`, currently `carry_btc_eth`): the "no
  cash/gross/net breakdown, no discrete trades" caption in place of the equity sections above.
- **The carry book specifically** (`kind == "carry"`, i.e. `carry_btc_eth`): book-state line
  (equity, last run), the risk-monitor panel (BTC/ETH 7-day funding + funding-flip badges,
  leverage/liquidation-distance table across the four posture tiers, the high-risk warning), and
  the risk register (expandable entries: category/measured-or-cited badges, likelihood, impact,
  detail, source).

Full functional parity with `app.py`'s `render_strategy_panel` / `render_trade_log` /
`render_carry_risk_panel` / `render_risk_register` — same tables, same captions and warnings,
same risk-register entries. This is a port to the new stack, not a redesign of what's shown.

### Explicitly out of scope for 2b

- Research Lab view (sub-project 3 in the original 4-part decomposition — separate spec).
- Any change to `state/`, `engine.py`, doctrine logic, `risk_register.py`'s own entries, or
  anything the paper-engine GitHub Action owns.
- Auth, non-localhost deployment, mobile responsiveness (unchanged from sub-projects 1-2a).
- New sound cues. The existing three interaction moments (row selection, range-control click,
  first-data-landed) already cover this slice's real "something changed" events; a positions
  table finishing its fetch is not a new one — see Visual & motion language below.

## Backend — `src/tradefabe/dashboard.py`, `src/tradefabe/api/main.py`

### `dashboard.py` changes

- **`load_carry_risk()` moves from `app.py` to `dashboard.py`, undecorated.** Same reasoning and
  same shape as the seven loaders 2a already moved (`load_backtest`, `load_piggyback_backtest`,
  etc.): `src/tradefabe/api/` cannot import from `app.py`, and the risk-monitor panel needs this
  reachable from the API. `app.py` is updated to call `dashboard.load_carry_risk()` — pure
  extraction, no behavior change, same shape as every prior loader move.

### `GET /api/books/{name}/detail?window=...`

Same endpoint 2a built, extended (per that spec's own note: "2b extends this same response ...
no new endpoint, no versioning scheme needed for that transition").

- **`compute_positions=False` becomes `compute_positions=True`** (the default) in the
  `book_panel_data(...)` call — this is the one-line flip that turns the positions/deployment
  math back on for the API, mirroring what `app.py` has always passed.
- **New response fields, equity books (`kind == "equity"`):**
  - `accrual_only: bool` — `name in ACCRUAL_ONLY_BOOKS`. Drives the frontend's caption branch
    instead of a server-rendered string, matching how `divergence_state`/`verdict` are already
    plain enums the frontend renders copy around.
  - `deployment: {cash, gross, net, equity, cash_pct, gross_pct, net_pct, n_unpriced, n_held,
    priced_at, is_short_funded} | null` — `null` when `accrual_only` is true (mirrors
    `book_panel_data()`'s own `None` in that case). Every numeric field routed through
    `_finite_or_none`.
  - `positions: [{ticker, units, last_price, value, weight}] | null` — `positions_df` records,
    same `null`-when-accrual-only rule. `last_price`/`value`/`weight` individually nullable
    (unpriced positions).
  - `positions_asof: string | null` — ISO date, from `data["positions_asof"]`.
  - `trades: [{ts, ticker, side, shares, price, notional, position_after}]` — `trades_df`
    records, `ts` serialized as ISO-8601 (`Timestamp.isoformat()`), always an array (empty, not
    null, per `trades_frame()`'s own "empty frame, not None" contract).
- **New response fields, the carry book (`kind == "carry"`):**
  - `carry_risk: {...} | null` — `dashboard.load_carry_risk()`'s dict as-is (already
    JSON-shaped: nested `coins.BTC/ETH.postures.*`, no DataFrames), `null` if the file doesn't
    exist yet (mirrors `load_carry_risk()`'s own `None`-on-missing-file contract). Passed through
    a small recursive NaN-guard (`_finite_or_none` only walks flat dicts today; this data nests
    two levels).
  - `risk_register: [{key, title, category, likelihood, impact, detail, source, url, measured}]`
    — `risk_register.build(curve, carry_risk_dict)`'s own list of plain-JSON-safe dicts, no
    transformation needed.
- `404` behavior on an unknown book name is unchanged from 2a.

## Frontend — `frontend/src/`

New components, each independently testable against mock JSON (matching 2a's component
boundaries — `RowList`/`DetailPanel`/`RangeControl`/`PlotlyChart` each own one clear piece):

- **`DeploymentStats.tsx`** — the 4-stat row (cash/gross/net/total equity), reusing the existing
  `StatTile` component. Renders the unpriced-positions warning and the
  short-funded-vs-vol-targeting caption text based on `deployment.is_short_funded` /
  `deployment.n_unpriced`.
- **`PositionsTable.tsx`** — ticker/units/last price/value/weight. Empty state: "No open
  positions (book hasn't rebalanced yet)." Footer caption with the `positions_asof` date and the
  "weight is % of total equity" note.
- **`TradeLog.tsx`** — the fill table. Three states: accrual-only caption, "no fills yet"
  caption, or the populated table + footer caption (fill count, last fill timestamp, cost bps —
  reads the same `signals_cost_bps()`-derived constant already available via `dashboard.py`, so
  a fifth API round-trip isn't needed: pass it as a field on the detail response, e.g.
  `cost_bps: number`).
- **`CarryRiskPanel.tsx`** — BTC/ETH 7-day funding metrics + flip badges, the leverage/
  liq-distance table pivoted the same way `render_carry_risk_panel()` does (posture rows ×
  coin columns), the blended-funding-flip warning, the high-risk-alert error banner.
- **`RiskRegister.tsx`** — one `<details>` per entry (same expander shape as `DetailPanel`'s
  existing backtest-history section), severity badge (color-mapped from `category`, matching
  `SEVERITY_BADGE`) + measured/cited badge, likelihood/impact/detail lines, source link when
  present.

**`DetailPanel.tsx` changes:** the `DetailResponse` type gains the new optional fields above.
After the existing backtest-history `<details>` block, branch on `data.kind`:
- `equity`: render `DeploymentStats` + `PositionsTable` (skipped entirely, replaced by the
  existing accrual-only caption, when `data.accrual_only`) then `TradeLog`.
- `carry`: render a book-state line (equity + last run — already available via `book_json`,
  which 2a's response doesn't currently expose; add `book_state: {equity, last_run} | null`)
  then `CarryRiskPanel` then `RiskRegister`.

`DetailPanel.tsx` itself stays a thin composer passing data down — it does not grow new
rendering logic beyond the branch above, keeping the file from becoming the "one giant
component" 2a's own component boundaries were designed to avoid.

**Styling:** hairline `border-white/5` dividers between sections (2a's own visual-language
amendment), `font-mono tabular-nums` for numeric table columns (ties to the same IBM Plex Mono
2a already wired in for stat values and Plotly chart fonts), native `<table>` elements styled to
match the surface/card language — no new table-component dependency.

## Visual & motion language

No amendment needed — 2b inherits 2a's already-approved language (spring-physics section
mounts via the existing `SPRING` config and `SectionHeader` treatment, hairline dividers, mono
numerics, static dither overlay). The one explicit decision specific to this slice: **no new
sound cues.** 2a's rule was "three real interaction moments only" specifically to avoid an
unmutable tool getting tiresome; a positions table or risk register finishing its fetch is the
same class of event as the stat grid or verdict badge already rendering silently today, not a
new *interaction*. Revisit only if Dave asks for it directly.

## Testing

- **Backend:** extend `tests/test_api_book_detail.py` — equity book response includes
  `positions`/`deployment`/`trades`/`accrual_only`/`cost_bps`; an `ACCRUAL_ONLY_BOOKS` member
  has `deployment`/`positions` both `null` and `accrual_only: true`; the carry book response
  includes `carry_risk`/`risk_register`/`book_state`; a missing `carry_risk.json` yields
  `carry_risk: null` without a 500. New test for `dashboard.load_carry_risk()`'s post-move
  import path (`from tradefabe import dashboard; dashboard.load_carry_risk()`), mirroring the
  existing `load_carry_backtest()` test precedent.
- **Frontend (Vitest + RTL):** one test file per new component — `DeploymentStats` (short-funded
  vs. normal captions, unpriced warning), `PositionsTable` (populated + empty), `TradeLog`
  (accrual-only, empty, populated), `CarryRiskPanel` (flip-alert badge, high-risk banner),
  `RiskRegister` (expander open/closed, measured vs. cited badge) — each fed mock JSON shaped
  like the real API response, per 2a's existing pattern for `RowList`/`DetailPanel`.
- **CI:** unchanged (`tests.yml` already runs both `pytest tests/` and `npm test` since 2a).
- **Manual:** both dev servers running; select an equity book with open positions (confirm
  table + deployment stats), an accrual-only equity book if one exists (confirm the caption
  path), and the carry book (confirm risk-monitor numbers match `state/paper/carry_risk.json`
  and the risk register entries render); confirm a missing/stale `carry_risk.json` doesn't
  crash the panel.

## Process

- Branch: `feat/dashboard-paper-books-2b`, off `main`.
- One GitHub issue filed for this slice before implementation starts.
- PR body: change + test plan, via quoted heredoc, per repo convention.
- `/ship` isn't available to Dave for this project — branch → PR → CI-wait → merge → verify →
  cleanup run by hand, following CLAUDE.md's documented sequence exactly.
- `doctrine-auditor` not needed — no changes to `STRATEGIES.md` or `graveyard.csv`.
