# Paper Books sort redesign + Research Lab stale-cache fix, design spec

Status: draft, pending Dave's review
Date: 2026-08-15
Related: builds on `2026-08-13-dashboard-research-lab-design.md`'s auto-add work in the
Research Lab; this spec closes a gap in it (see "Why this, why now" below).

## Why this, why now

Two independent, small requests, bundled into one spec since both landed in the same
conversation and both touch `dashboard.py`.

**1. Paper Books sort categories.** Dave wants `Family` removed as a sort option and `Sharpe`
added, keeping `Recently added` / `Return today` / `Total return`. He also wants the chance to
name other sorters before committing — asked, and the answer was none for now.

**2. Research Lab auto-inclusion.** Dave asked whether new strategies land in the verdicts table
and the overview growth chart/correlation table automatically as research produces them.
Investigation found:

- The verdicts table already lists every strategy in `gy_last` with no cap — this already works,
  no change needed.
- The growth chart and correlation table are *supposed* to be dynamic the same way
  (`unique_strategy_universe()` re-ranks/dedupes from whatever `_all_candidate_returns()`
  returns), but `_all_candidate_returns()` is wrapped in `@functools.cache` with no
  invalidation. Once the serving process (the FastAPI dev server, or a long-running Streamlit
  process) has been up for a while, newly-committed factory/pipeline curves are invisible until
  the process restarts — the chart is frozen at whatever the universe looked like at process
  start. This directly explains why "only a few" strategies show up and the set doesn't appear
  to grow.
- Two more caches share the identical defect: `_load_generated_ledger()` and
  `_load_pipeline_ledger()`, both `@functools.cache`, both reading CSVs
  (`generated_templates.csv` / `pipeline_ideas.csv`) that gain new rows daily from the same
  crons. A brand-new factory/pipeline candidate can show up with a missing family/rationale
  until restart — same bug class, same feature area, so it's in scope here too.

## Scope

### In this change

1. **Paper Books sort**: drop `Family`, add `Sharpe` (backtest OOS Sharpe from
   `gy_last["oos_sharpe"]`, the same number already shown on each book's own Verdict line).
   Default sort changes from `Family` to `Total return`.
2. **Paper Books becomes a flat list, permanently.** Family-grouped headers
   ("TREND / MOMENTUM", etc.) go away from this view along with the `Family` sort option.
3. **Drop three stale-forever caches** in `dashboard.py`: `_all_candidate_returns()`,
   `_load_generated_ledger()`, `_load_pipeline_ledger()`. Each becomes a plain function,
   re-reading its source file(s) on every call.

### Explicitly out of scope

- Any additional sorter beyond the four named (verdict, drawdown, corr-to-bench — all
  considered and declined for now).
- `dashboard.group_books_by_family()` itself — **not removed**. `app.py` (the still-live
  Streamlit dashboard) calls it directly, independent of this API, and stays untouched.
- Any caching strategy other than "recompute every call" (e.g. mtime-based invalidation,
  TTL) — considered and declined; a human-facing dashboard isn't hit often enough for the
  re-read+re-correlate cost to matter, so the simplest correct option wins.
- Any change to `state/`, `engine.py`, doctrine logic, or anything the paper-engine/pipeline
  GitHub Actions own.
- The Verdicts table itself — already correct, confirmed by reading `research_verdicts()`,
  no code change.

## Design

### Paper Books sort

**Frontend (`frontend/src/components/RowList.tsx`):**
- `SORT_OPTIONS` becomes:
  ```ts
  const SORT_OPTIONS: Record<string, string> = {
    "Recently added": "recent",
    "Return today": "return_today",
    "Total return": "total_return",
    "Sharpe": "sharpe",
  };
  ```
- `useState("Family")` for `sortLabel` becomes `useState("Total return")`.
- The `SummaryResponse` union type (`{families: FamilyGroup[]} | {books: BookRow[]}`) collapses
  to just `{books: BookRow[]}`. `FamilyGroup` type is removed.
- The `"families" in data ? ... : ...` branch in the render body is removed; only the flat-list
  branch remains (the `else` arm already exists and already renders the sort control + retired
  divider, so this is a deletion, not new code).
- No other row-rendering logic changes — `Row`, `ClusterRow`, `clusterRows`, sparkline handling,
  `rowDelta`/`deltaMode` are untouched.

**Backend (`src/tradefabe/api/main.py`):**
- `books_summary`'s valid-sort tuple becomes
  `("recent", "return_today", "total_return", "sharpe")` — `"family"` removed, the
  `if sort == "family": groups = ...` branch removed entirely, so this endpoint always calls
  `dashboard.sort_books_flat(...)`.

**Backend (`src/tradefabe/dashboard.py`):**
- `sort_books_flat()` gains a `_sharpe` column:
  ```python
  df["_sharpe"] = df["book"].map(
      lambda n: float(gy_last.loc[n, "oos_sharpe"])
      if gy_last is not None and n in gy_last.index and pd.notna(gy_last.loc[n, "oos_sharpe"])
      else float("nan")
  )
  ```
  and `sort_col` mapping gains `"sharpe": "_sharpe"`. Sorted descending with
  `na_position="last"`, same as every other key here — a book with no graveyard row (shouldn't
  happen for any live book, but the paper engine's own `run_hourly()`/`run_kronos()` docstrings
  are explicit that live code must never raise on a data gap) sorts to the bottom rather than
  crashing.
- `group_books_by_family()` is untouched — still used by `app.py`.

### Research Lab cache fix

Remove `@functools.cache` from three functions in `dashboard.py`, no other code inside them
changes:

- `_all_candidate_returns()` (currently decorated at its definition, reads
  `full_returns.csv`/`factory_returns.csv`/`pipeline_returns.csv`/`hourly_returns.csv`/
  `kronos_returns.csv`/`pairs_returns.csv`)
- `_load_generated_ledger()` (reads `generated_templates.csv`)
- `_load_pipeline_ledger()` (reads `pipeline_ideas.csv`)

Each function's docstring currently justifies the cache in terms of avoiding redundant re-reads
**within a single request/render** (e.g. "called once per Research Lab overview/piggyback
request" for `_all_candidate_returns`, "book_family()/strategy_description() call this per
name" for the ledgers). That reasoning doesn't require caching *across* requests forever — it's
solved just as well by reading fresh every top-level call, since none of these are called in a
tight per-row loop from outside `dashboard.py` itself. Docstrings get updated to explain why
there's no cache (the staleness this spec fixes) instead of why there is one.

No caller changes: `unique_strategy_universe()`, `book_family()`, `strategy_description()`,
`research_overview()`, `research_piggyback()` all already call these functions expecting fresh
data: removing the cache makes that expectation true.

## Testing

- **`sort_books_flat` sharpe sort**: new test in `tests/test_dashboard_helpers.py` — build a
  small `psum`/`gy_last` fixture where sharpe order differs from every other sort key, assert
  `sort_key="sharpe"` produces that order, and assert a book missing from `gy_last` sorts last
  rather than raising.
- **Cache-freshness regression**: new test(s) proving each of the three functions reflects a
  file change made *after* an initial call — e.g. call `_all_candidate_returns()` once, mutate
  the underlying CSV fixture, call it again, assert the second call sees the mutation. Mirrors
  the shape of the existing `test_all_candidate_returns_sorts_the_index_after_concat` test (same
  file), which already monkeypatches the loader functions rather than touching real artifacts.
- **Frontend**: existing `RowList` tests (if any) updated for the removed `Family` option and
  default; new/updated test asserting the sort `<select>` never renders a `Family` option and
  defaults to `Total return`.
- Full `pytest tests/` and `npm test -- --run` must stay green; `npx tsc --noEmit` clean given
  the `SummaryResponse` type collapse.

## Rollout

Single PR, both parts together (small enough not to warrant separate PRs) — squash-merged
through the normal branch+PR workflow, `doctrine-auditor` not required (no `STRATEGIES.md`/
`graveyard.csv` changes).
