# Paper Books Sort Redesign + Research Lab Stale-Cache Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Paper Books' `Family` sort with `Sharpe`, collapse the view to a permanent flat list, and remove three `@functools.cache`-forever bugs in `dashboard.py` that silently freeze the Research Lab's growth chart/correlation table and strategy naming at whatever the universe looked like when the serving process started.

**Architecture:** Backend changes are confined to `src/tradefabe/dashboard.py` (one new sort column, three removed cache decorators) and `src/tradefabe/api/main.py` (drop the `family` branch, change the default). Frontend changes are confined to `frontend/src/components/RowList.tsx` and its test file. No new files, no schema changes, no `state/`/doctrine involvement.

**Tech Stack:** Python 3.14 / FastAPI / pandas (backend), React 18 / TypeScript / Vitest + Testing Library (frontend). Existing pytest (`pyproject.toml` `pythonpath=[".", "research"]`) and `npm test -- --run` suites.

## Global Constraints

- Never use the em dash "—"; use a plain dash "-".
- `dashboard.group_books_by_family()` is NOT touched or removed — `app.py` (Streamlit) calls it directly and stays on the family-grouped view.
- No caching strategy other than "recompute every call" for the three functions in Task 5 (spec explicitly declined mtime/TTL alternatives).
- Branch `paper-books-sort-and-research-lab-cache` already exists and already has the spec commit (`docs/superpowers/specs/2026-08-15-paper-books-sort-and-research-lab-cache-design.md`) — work continues on it, do not create a new branch.
- Full `pytest tests/` and `npm test -- --run` must stay green at the end of every task; `npx tsc --noEmit` clean after any frontend task.

---

### Task 1: Backend — add `sharpe` as a `sort_books_flat` key

**Files:**
- Modify: `src/tradefabe/dashboard.py:1048-1074` (`sort_books_flat`)
- Test: `tests/test_dashboard_helpers.py`

**Interfaces:**
- Consumes: nothing new — `gy_last` (a DataFrame indexed by strategy name with an `oos_sharpe` column, or `None`) is already a parameter.
- Produces: `sort_books_flat(psum, phist, gy_last=None, show_monitor_only=True, sort_key="sharpe")` now a valid call; later tasks (Task 2) rely on `"sharpe"` being an accepted `sort_key`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_dashboard_helpers.py` (near the other `sort_books_flat`-adjacent tests; there are none yet in this file, so add after `test_unique_strategy_universe_excludes_stale_one_time_snapshots`):

```python
def test_sort_books_flat_sharpe_sorts_descending_by_backtest_oos_sharpe():
    psum = pd.DataFrame({
        "book": ["low_sharpe_book", "high_sharpe_book", "no_verdict_book"],
        "equity": [100_000.0, 100_000.0, 100_000.0],
        "return": [0.0, 0.0, 0.0],
        "last_run": ["2026-08-14"] * 3,
        "retired_at": [None, None, None],
    })
    phist = pd.DataFrame({
        "book": ["low_sharpe_book", "high_sharpe_book", "no_verdict_book"],
        "date": pd.to_datetime(["2026-08-14"] * 3),
        "equity": [100_000.0, 100_000.0, 100_000.0],
    })
    gy_last = pd.DataFrame(
        {"oos_sharpe": [0.2, 1.5], "verdict": ["DEAD", "DEAD"]},
        index=["low_sharpe_book", "high_sharpe_book"],
    )
    rows = dashboard.sort_books_flat(psum, phist, gy_last, sort_key="sharpe")
    assert [r["book"] for r in rows] == ["high_sharpe_book", "low_sharpe_book", "no_verdict_book"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dashboard_helpers.py::test_sort_books_flat_sharpe_sorts_descending_by_backtest_oos_sharpe -v -n0`
Expected: FAIL with `KeyError: 'sharpe'`

- [ ] **Step 3: Implement**

In `src/tradefabe/dashboard.py`, replace the body of `sort_books_flat` (currently lines 1048-1074) with:

```python
def sort_books_flat(psum, phist, gy_last=None, show_monitor_only=True, sort_key="recent"):
    """Flat (ungrouped) alternative to group_books_by_family(), for the non-"Family" sort
    modes -- same monitor-only filter, same row shape (dicts, drop-in for the Series
    group_books_by_family's rows already are: both support `r["book"]` / `r.get(...)`),
    just one list sorted descending instead of family-bucketed tuples.

    sort_key: "recent" (book_introduced_dates), "return_today" (book_return_today),
    "total_return" (psum's own `return` column), or "sharpe" (gy_last's own `oos_sharpe`
    -- the pre-registered doctrine backtest number, the same one shown on each book's own
    Verdict line; a book with no graveyard row sorts last, same as any other NaN here).
    Sorted via pandas sort_values, NOT a hand-rolled sorted() -- comparing None to a
    Timestamp, or NaN to a float, raises under plain Python sort but
    sort_values(na_position="last") handles both cleanly."""
    monitor_only = {r["book"]: _is_monitor_only(r["book"], gy_last) for _, r in psum.iterrows()}
    rows = [r for _, r in psum.iterrows() if show_monitor_only or not monitor_only[r["book"]]]
    if not rows:
        return []
    introduced = book_introduced_dates(phist)
    return_today = book_return_today(phist)
    df = pd.DataFrame(rows)
    df["_introduced"] = df["book"].map(lambda n: introduced.get(n, pd.NaT))
    df["_return_today"] = df["book"].map(lambda n: return_today.get(n, float("nan")))
    df["_sharpe"] = df["book"].map(
        lambda n: float(gy_last.loc[n, "oos_sharpe"])
        if gy_last is not None and n in gy_last.index and pd.notna(gy_last.loc[n, "oos_sharpe"])
        else float("nan")
    )
    # Retired sorts last no matter which sort_key is active -- primary key, ascending
    # (False=0 before True=1), so it wins ties over the secondary chosen-sort column
    # without disturbing that column's own ordering within either group.
    df["_retired"] = df.apply(_row_is_retired, axis=1)
    sort_col = {"recent": "_introduced", "return_today": "_return_today",
                "total_return": "return", "sharpe": "_sharpe"}[sort_key]
    df = df.sort_values(["_retired", sort_col], ascending=[True, False], na_position="last")
    return list(df.to_dict("records"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_dashboard_helpers.py::test_sort_books_flat_sharpe_sorts_descending_by_backtest_oos_sharpe -v -n0`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass (this change is additive to `sort_books_flat`'s dict output -- new `_sharpe`/`_introduced`/`_return_today`/`_retired` keys were already present except `_sharpe`, and nothing downstream asserts an exact key set on the raw dict before `_row_json` reshapes it).

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/dashboard.py tests/test_dashboard_helpers.py
git commit -m "dashboard: add sharpe as a sort_books_flat key"
```

---

### Task 2: Backend — remove `family` from `/api/books/summary`, default to `total_return`

**Files:**
- Modify: `src/tradefabe/api/main.py:84-113` (`books_summary`)
- Modify: `tests/test_api_books_summary.py`

**Interfaces:**
- Consumes: `dashboard.sort_books_flat(..., sort_key="sharpe")` from Task 1.
- Produces: `GET /api/books/summary` now only ever returns `{"books": [...]}` (never `{"families": [...]}`); valid `sort` values are `recent | return_today | total_return | sharpe`; default `sort` is `total_return`.

- [ ] **Step 1: Update the tests first**

Replace `tests/test_api_books_summary.py` in full with:

```python
import math

from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_summary_default_sort_is_total_return_and_flat():
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "books" in body
    assert "families" not in body
    default_body = client.get("/api/books/summary?sort=total_return").json()
    assert body == default_body


def test_summary_flat_sort_modes_return_a_flat_books_list():
    client = TestClient(app)
    for sort in ("recent", "return_today", "total_return", "sharpe"):
        resp = client.get(f"/api/books/summary?sort={sort}")
        assert resp.status_code == 200
        body = resp.json()
        assert "books" in body
        assert "families" not in body


def test_summary_family_sort_is_no_longer_accepted():
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=family")
    assert resp.status_code == 400


def test_summary_unknown_sort_is_a_400():
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=bogus")
    assert resp.status_code == 400


def test_summary_unknown_sort_is_a_400_even_with_no_paper_state(monkeypatch):
    """The sort-validity check must run before the psum-is-None early return, or an
    unknown sort silently succeeds (200 with an empty list) whenever no local paper
    state exists -- inconsistent with the same request against a populated state."""
    monkeypatch.setattr(dashboard, "load_paper_state", lambda: (None, None))
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

(`pd` was already dead in the original file -- nothing used it even before this rewrite --
so it's dropped above; `math` stays since `test_summary_nan_fields_become_json_null_not_nan_token`
still uses it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_books_summary.py -v -n0`
Expected: `test_summary_default_sort_is_total_return_and_flat` and
`test_summary_family_sort_is_no_longer_accepted` FAIL (endpoint still defaults to
`"family"` and still accepts it); `test_summary_flat_sort_modes_return_a_flat_books_list`
FAILs on the `"sharpe"` iteration with a 400.

- [ ] **Step 3: Implement**

In `src/tradefabe/api/main.py`, replace the whole `books_summary` function (currently
lines 84-113) with:

```python
@app.get("/api/books/summary")
def books_summary(sort: str = "total_return", show_monitor_only: bool = True):
    if sort not in ("recent", "return_today", "total_return", "sharpe"):
        raise HTTPException(status_code=400, detail=f"unknown sort: {sort}")

    psum, phist = dashboard.load_paper_state()
    if psum is None:
        return {"books": []}

    gy_last = _load_gy_last()
    names = psum["book"].tolist()
    colors = dashboard.book_colors(names)
    introduced = dashboard.book_introduced_dates(phist)
    return_today = dashboard.book_return_today(phist)
    monitor_only = {n: dashboard._is_monitor_only(n, gy_last) for n in names}

    def row_kwargs():
        return dict(colors=colors, introduced=introduced, return_today=return_today,
                   monitor_only=monitor_only, phist=phist)

    rows = dashboard.sort_books_flat(psum, phist, gy_last, show_monitor_only, sort)
    return {"books": [_row_json(r, **row_kwargs()) for r in rows]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_books_summary.py -v -n0`
Expected: all PASS

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass. In particular check `test_api_research_autoadd.py::test_books_summary_has_no_hardcoded_book_names`
(uses `?sort=recent`, unaffected) still passes.

- [ ] **Step 6: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_books_summary.py
git commit -m "api: drop family sort from books_summary, default to total_return"
```

---

### Task 3: Frontend — `RowList.tsx` becomes a permanent flat list

**Files:**
- Modify: `frontend/src/components/RowList.tsx`

**Interfaces:**
- Consumes: `GET /api/books/summary?sort=...` now always returns `{books: BookRow[]}` (Task 2).
- Produces: `RowList` renders with no family grouping under any circumstance; `SORT_OPTIONS` exposes exactly `Recently added | Return today | Total return | Sharpe`; default `sortLabel` state is `"Total return"`.

- [ ] **Step 1: Update the type definitions and constants**

In `frontend/src/components/RowList.tsx`, replace:

```ts
type FamilyGroup = { family: string; label: string; books: BookRow[] };
type SummaryResponse = { families: FamilyGroup[] } | { books: BookRow[] };

type ReviewRow = { book: string; days_live: number; verdict: string };

const SORT_OPTIONS: Record<string, string> = {
  Family: "family",
  "Recently added": "recent",
  "Return today": "return_today",
  "Total return": "total_return",
};
```

with:

```ts
type SummaryResponse = { books: BookRow[] };

type ReviewRow = { book: string; days_live: number; verdict: string };

const SORT_OPTIONS: Record<string, string> = {
  "Recently added": "recent",
  "Return today": "return_today",
  "Total return": "total_return",
  Sharpe: "sharpe",
};
```

- [ ] **Step 2: Change the default sort state**

Replace:

```ts
  const [sortLabel, setSortLabel] = useState("Family");
```

with:

```ts
  const [sortLabel, setSortLabel] = useState("Total return");
```

- [ ] **Step 3: Simplify the `allBooks` derivation in the fetch effect**

Replace:

```ts
        setData(body);
        const allBooks = "families" in body ? body.families.flatMap((f) => f.books) : body.books;
        const seen = readSeenBooks();
```

with:

```ts
        setData(body);
        const allBooks = body.books;
        const seen = readSeenBooks();
```

- [ ] **Step 4: Remove the family-grouped render branch**

Replace the whole conditional render block:

```tsx
      {"families" in data
        ? data.families.map((fam, i) => (
            <div key={fam.family}>
              <div className="px-4 pt-2 pb-1 flex items-center justify-between gap-4">
                <span className="relative text-xs uppercase text-ink-muted">
                  {fam.label}
                  <span className="family-underline absolute -bottom-1 left-0 h-px w-6 bg-accent origin-left animate-underline-draw" />
                </span>
                {i === 0 && sortControl}
              </div>
              {clusterRows(fam.books).map((group) => (
                <ClusterRow
                  key={group[0].book}
                  group={group}
                  selectedName={selectedName}
                  newBooks={newBooks}
                  deltaMode={deltaMode}
                />
              ))}
            </div>
          ))
        : (
            <>
              <div className="px-4 pt-2 pb-1 flex items-center justify-end">{sortControl}</div>
              {(() => {
                // Backend already sorts retired last regardless of sort_key (see
                // dashboard.sort_books_flat's own "_retired" primary sort key) -- this
                // just draws the same "Retired" divider the family view gets for free
                // from its own trailing group, so retired books read as a distinct
                // section here too instead of trailing off silently.
                const active = data.books.filter((b) => b.retired_at === null);
                const retired = data.books.filter((b) => b.retired_at !== null);
                return (
                  <>
                    {clusterRows(active).map((group) => (
                      <ClusterRow
                        key={group[0].book}
                        group={group}
                        selectedName={selectedName}
                        newBooks={newBooks}
                        deltaMode={deltaMode}
                      />
                    ))}
                    {retired.length > 0 && (
                      <div>
                        <div className="px-4 pt-2 pb-1">
                          <span className="relative text-xs uppercase text-ink-muted">
                            Retired
                            <span className="family-underline absolute -bottom-1 left-0 h-px w-6 bg-accent origin-left animate-underline-draw" />
                          </span>
                        </div>
                        {clusterRows(retired).map((group) => (
                          <ClusterRow
                            key={group[0].book}
                            group={group}
                            selectedName={selectedName}
                            newBooks={newBooks}
                            deltaMode={deltaMode}
                          />
                        ))}
                      </div>
                    )}
                  </>
                );
              })()}
            </>
          )}
```

with just the (already-existing) flat branch's contents, unconditionally:

```tsx
      <div className="px-4 pt-2 pb-1 flex items-center justify-end">{sortControl}</div>
      {(() => {
        // Backend already sorts retired last regardless of sort_key (see
        // dashboard.sort_books_flat's own "_retired" primary sort key) -- this draws a
        // "Retired" divider so retired books read as a distinct trailing section
        // instead of trailing off silently.
        const active = data.books.filter((b) => b.retired_at === null);
        const retired = data.books.filter((b) => b.retired_at !== null);
        return (
          <>
            {clusterRows(active).map((group) => (
              <ClusterRow
                key={group[0].book}
                group={group}
                selectedName={selectedName}
                newBooks={newBooks}
                deltaMode={deltaMode}
              />
            ))}
            {retired.length > 0 && (
              <div>
                <div className="px-4 pt-2 pb-1">
                  <span className="relative text-xs uppercase text-ink-muted">
                    Retired
                    <span className="family-underline absolute -bottom-1 left-0 h-px w-6 bg-accent origin-left animate-underline-draw" />
                  </span>
                </div>
                {clusterRows(retired).map((group) => (
                  <ClusterRow
                    key={group[0].book}
                    group={group}
                    selectedName={selectedName}
                    newBooks={newBooks}
                    deltaMode={deltaMode}
                  />
                ))}
              </div>
            )}
          </>
        );
      })()}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean (this will currently show errors from `RowList.test.tsx` still using the
old `{families: [...]}` shape -- that's expected until Task 4; if `tsc` errors originate
from `RowList.tsx` itself, fix them before moving on).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/RowList.tsx
git commit -m "RowList: drop Family sort and family grouping, add Sharpe"
```

(The test suite will not compile/pass yet -- that's Task 4, next.)

---

### Task 4: Frontend — rewrite `RowList.test.tsx` for the flat-only view

**Files:**
- Modify: `frontend/src/components/RowList.test.tsx`

**Interfaces:**
- Consumes: `RowList` from Task 3 (flat-only, `SORT_OPTIONS` without `Family`, default `"Total return"`).
- Produces: nothing consumed by later tasks -- this is the terminal frontend task for this subsystem.

- [ ] **Step 1: Replace the whole file**

Replace `frontend/src/components/RowList.test.tsx` in full with:

```tsx
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RowList from "./RowList";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const FLAT_RESPONSE = {
  books: [
    { book: "tsmom_12m", equity: 103241, return: 0.032, last_run: "2026-08-06",
      retired_at: null, family: "A", color: "#2a78d6", introduced: "2026-01-01",
      return_today: 0.012, monitor_only: false, sparkline: [100000, 100500, 101000] },
    { book: "carry_btc_eth", equity: 112003, return: 0.12, last_run: "2026-08-06",
      retired_at: null, family: "D", color: "#1baf7a", introduced: "2025-05-01",
      return_today: 0.001, monitor_only: false, sparkline: [110000, 111500, 112003] },
  ],
};

const UP_FOR_REVIEW_RESPONSE = { books: [] };

function mockFetchSequence() {
  return vi.fn((url: string) => {
    if (url.includes("up_for_review")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(FLAT_RESPONSE) });
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  globalThis.fetch = mockFetchSequence();
  navigateMock.mockClear();
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

vi.mock("../lib/sound", () => ({ playSelect: vi.fn() }));

// jsdom never runs framer-motion's real layout-projection engine, so the only
// observable proxy for idea #24's shared-element handoff is which prop each
// motion.* element actually received -- stub motion.span/motion.div down to plain
// DOM elements that surface `layoutId` as a `data-layoutid` attribute.
vi.mock("framer-motion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("framer-motion")>();
  type StubProps = { layoutId?: string; children?: ReactNode; className?: string };
  const Span = ({ layoutId, children, className }: StubProps) => (
    <span className={className} data-layoutid={layoutId}>{children}</span>
  );
  const Div = ({ layoutId, children, className }: StubProps) => (
    <div className={className} data-layoutid={layoutId}>{children}</div>
  );
  return { ...actual, motion: { ...actual.motion, span: Span, div: Div } };
});

function mockFetchWithBooks(books: unknown[]) {
  return vi.fn((url: string) => {
    if (url.includes("up_for_review")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ books }) });
  }) as unknown as typeof fetch;
}

describe("RowList", () => {
  it("renders the flat book list with no family grouping", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText("carry_btc_eth")).toBeInTheDocument();
    // No retired books in FLAT_RESPONSE -- no "Retired" divider, no underline at all.
    expect(screen.queryByText("Retired")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".family-underline")).toHaveLength(0);
  });

  it("never offers Family as a sort option", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const select = screen.getByLabelText(/sort by/i) as HTMLSelectElement;
    const optionLabels = [...select.options].map((o) => o.value);
    expect(optionLabels).not.toContain("Family");
    expect(optionLabels).toEqual(["Recently added", "Return today", "Total return", "Sharpe"]);
    expect(select.value).toBe("Total return");
  });

  it("draws a divider with an underline above the Retired section when a retired book is present", async () => {
    globalThis.fetch = mockFetchWithBooks([
      ...FLAT_RESPONSE.books,
      { book: "old_dead_book", equity: 98000, return: -0.02, last_run: "2026-08-06",
        retired_at: "2026-07-01T00:00:00", family: "A", color: "#eda100",
        introduced: "2025-01-01", return_today: 0, monitor_only: false,
        sparkline: [99000, 98500, 98000] },
    ]);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("old_dead_book")).toBeInTheDocument());
    expect(screen.getByText("Retired")).toBeInTheDocument();
    expect(container.querySelectorAll(".family-underline")).toHaveLength(1);
  });

  it("refetches with the new sort key when a different sort option is chosen", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const select = screen.getByLabelText(/sort by/i);
    await userEvent.selectOptions(select, "Sharpe");
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("sort=sharpe"))).toBe(true);
    });
  });

  it("fetches with the default total_return sort on first load", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
    expect(calls.some((u) => String(u).includes("sort=total_return"))).toBe(true);
  });

  it("never sends show_monitor_only -- the monitor-only filter was removed", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
    expect(calls.some((u) => String(u).includes("show_monitor_only"))).toBe(false);
  });

  it("redirects to a still-visible book when the selected one is filtered out", async () => {
    globalThis.fetch = mockFetchWithBooks(
      // tsmom_12m (the currently-selected book) is absent -- as if a sort/data
      // change server-side made it drop out of the list.
      [FLAT_RESPONSE.books[1]]
    );

    render(
      <MemoryRouter>
        <RowList selectedName="tsmom_12m" />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    expect(navigateMock).toHaveBeenCalledWith("/books/carry_btc_eth", { replace: true });
  });

  it("shows each book's introduced date, formatted m.d.yy to match the Streamlit dashboard", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText("1.1.26")).toBeInTheDocument();
    expect(screen.getByText("5.1.25")).toBeInTheDocument();
  });

  it("gives rows a hover-lift treatment", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const row = container.querySelector(".tf-row");
    expect(row?.className).toMatch(/hover:-translate-y-px/);
  });

  function mockFetchWithReview(reviewBooks: unknown[]) {
    return vi.fn((url: string) => {
      if (url.includes("up_for_review")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ books: reviewBooks }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(FLAT_RESPONSE) });
    }) as unknown as typeof fetch;
  }

  const REVIEW_BOOKS = [{ book: "tsmom_12m", days_live: 40, verdict: "DEAD" }, { book: "carry_btc_eth", days_live: 90, verdict: "ALIVE" }];

  it("does not pulse the up-for-review badge on a first-ever visit (nothing to compare)", async () => {
    localStorage.clear();
    globalThis.fetch = mockFetchWithReview(REVIEW_BOOKS);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Up for review/)).toBeInTheDocument());
    expect(container.querySelector(".review-badge-pulse")).toBeNull();
  });

  it("pulses the up-for-review badge when the count changed since the last visit", async () => {
    localStorage.setItem("tradefabe.reviewCount", "0");
    globalThis.fetch = mockFetchWithReview(REVIEW_BOOKS);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Up for review/)).toBeInTheDocument());
    expect(container.querySelector(".review-badge-pulse")).not.toBeNull();
  });

  it("does not pulse the up-for-review badge when the count matches the last visit", async () => {
    localStorage.setItem("tradefabe.reviewCount", String(REVIEW_BOOKS.length));
    globalThis.fetch = mockFetchWithReview(REVIEW_BOOKS);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Up for review/)).toBeInTheDocument());
    expect(container.querySelector(".review-badge-pulse")).toBeNull();
  });

  it("re-renders rows in the server's new order after a sort switch, for FLIP to animate", async () => {
    let sort = "total_return";
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("up_for_review")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
      }
      sort = new URL(url).searchParams.get("sort") ?? sort;
      const books =
        sort === "recent"
          ? [FLAT_RESPONSE.books[1], FLAT_RESPONSE.books[0]]
          : [FLAT_RESPONSE.books[0], FLAT_RESPONSE.books[1]];
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ books }) });
    }) as unknown as typeof fetch;

    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const namesBefore = [...container.querySelectorAll("[data-book]")].map((el) => el.getAttribute("data-book"));
    expect(namesBefore).toEqual(["tsmom_12m", "carry_btc_eth"]);

    await userEvent.selectOptions(screen.getByLabelText(/sort by/i), "Recently added");
    await waitFor(() => {
      const namesAfter = [...container.querySelectorAll("[data-book]")].map((el) => el.getAttribute("data-book"));
      expect(namesAfter).toEqual(["carry_btc_eth", "tsmom_12m"]);
    });
  });

  it("gives carry_btc_eth a featured chip, the one strategy cleared by doctrine", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    const carryRow = screen.getByText("carry_btc_eth").closest(".tf-row");
    expect(carryRow?.querySelector(".tf-featured-chip")).not.toBeNull();
    const tsmomRow = screen.getByText("tsmom_12m").closest(".tf-row");
    expect(tsmomRow?.querySelector(".tf-featured-chip")).toBeNull();
  });

  it("shows ghost skeleton rows while loading, not a plain Loading… flash", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    expect(container.querySelectorAll(".tf-skeleton-row").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".tf-skeleton-row")).toHaveLength(0);
  });

  it("marks the sparkline's last point with an end-dot", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const row = screen.getByText("tsmom_12m").closest(".tf-row");
    expect(row?.querySelector("svg circle")).not.toBeNull();
  });

  it("bursts a book that has never been seen before, tracked via localStorage", async () => {
    localStorage.clear();
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".tf-book-burst")).toHaveLength(2);
  });

  it("does not burst a book already recorded as seen in localStorage", async () => {
    localStorage.setItem("tradefabe.seenBooks", JSON.stringify(["tsmom_12m", "carry_btc_eth"]));
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".tf-book-burst")).toHaveLength(0);
  });

  it("idea #24: gives only the selected row's sparkline a shared layoutId, for the morph into DetailPanel's chart", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName="tsmom_12m" />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const selectedRow = screen.getByText("tsmom_12m").closest(".tf-row");
    const otherRow = screen.getByText("carry_btc_eth").closest(".tf-row");
    await waitFor(() =>
      expect(selectedRow?.querySelector("[data-layoutid]")?.getAttribute("data-layoutid")).toBe(
        "sparkline-tsmom_12m"
      )
    );
    expect(otherRow?.querySelector("[data-layoutid]")).toBeNull();
  });

  it("idea #24: releases the row's claim on the shared layoutId once the morph window passes, so the sparkline doesn't stay a permanently-hidden framer-motion duplicate", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName="tsmom_12m" />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const selectedRow = screen.getByText("tsmom_12m").closest(".tf-row");
    await waitFor(() =>
      expect(selectedRow?.querySelector("[data-layoutid]")?.getAttribute("data-layoutid")).toBe(
        "sparkline-tsmom_12m"
      )
    );
    await new Promise((resolve) => setTimeout(resolve, 600));
    await waitFor(() => expect(selectedRow?.querySelector("[data-layoutid]")).toBeNull());
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

  const DUPLICATE_BOOK = (name: string) => ({
    book: name, equity: 100627.66, return: 0.0063, last_run: "2026-08-06",
    retired_at: null, family: "C", color: "#7d8877", introduced: "2026-07-23",
    return_today: -0.0007, monitor_only: false,
    sparkline: [100600, 100610, 100627.66],
  });

  it("collapses books with an identical equity/return/sparkline curve into one row with a badge", async () => {
    globalThis.fetch = mockFetchWithBooks([
      DUPLICATE_BOOK("turn_of_month_gen_5_7"),
      DUPLICATE_BOOK("turn_of_month_gen_7_2"),
      DUPLICATE_BOOK("turn_of_month_gen_1_6"),
    ]);
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("turn_of_month_gen_5_7")).toBeInTheDocument());
    expect(screen.getByText("+2 identical")).toBeInTheDocument();
    expect(screen.queryByText("turn_of_month_gen_7_2")).not.toBeInTheDocument();
    expect(screen.queryByText("turn_of_month_gen_1_6")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("+2 identical"));
    expect(screen.getByText("turn_of_month_gen_7_2")).toBeInTheDocument();
    expect(screen.getByText("turn_of_month_gen_1_6")).toBeInTheDocument();
    expect(screen.getByText("hide")).toBeInTheDocument();
  });

  it("does not cluster books whose sparklines diverge even if today's equity happens to match", async () => {
    globalThis.fetch = mockFetchWithBooks([
      { ...DUPLICATE_BOOK("turn_of_month_gen_5_7"), sparkline: [100600, 100610, 100627.66] },
      { ...DUPLICATE_BOOK("turn_of_month_gen_9_9"), sparkline: [100000, 100300, 100627.66] },
    ]);
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("turn_of_month_gen_5_7")).toBeInTheDocument());
    expect(screen.getByText("turn_of_month_gen_9_9")).toBeInTheDocument();
    expect(screen.queryByText(/identical/)).not.toBeInTheDocument();
  });

  it("shows total return (not today's return) for the default Total return sort", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    // tsmom_12m: return 0.032 (3.2%), return_today 0.012 (1.2%) -- must show total, not today.
    const row = screen.getByText("tsmom_12m").closest(".tf-row");
    expect(row?.textContent).toContain("3.2%");
    expect(row?.textContent).not.toContain("1.2%");
  });

  it("shows return_today once the user explicitly sorts by Return today", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText(/sort by/i), "Return today");
    await waitFor(() => {
      const row = screen.getByText("tsmom_12m").closest(".tf-row");
      expect(row?.textContent).toContain("1.2%");
    });
  });
});
```

- [ ] **Step 2: Run the test file**

Run: `cd frontend && npx vitest run src/components/RowList.test.tsx`
Expected: all tests PASS.

- [ ] **Step 3: Full frontend suite + typecheck**

Run: `cd frontend && npm test -- --run && npx tsc --noEmit`
Expected: all pass, clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/RowList.test.tsx
git commit -m "RowList: rewrite tests for the flat-only view"
```

---

### Task 5: Backend — remove the three stale-forever caches

**Files:**
- Modify: `src/tradefabe/dashboard.py:590` (`_all_candidate_returns`), `:812` (`_load_generated_ledger`), `:836` (`_load_pipeline_ledger`)
- Modify: `tests/test_dashboard_helpers.py` (drop now-invalid `.cache_clear()` calls added in the prior PR)
- Modify: `tests/test_api_research_autoadd.py` (add the freshness regression tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_all_candidate_returns()`, `_load_generated_ledger()`, `_load_pipeline_ledger()` are plain functions (no `.cache_clear()` method) that re-read their source file(s) on every call.

- [ ] **Step 1: Fix the existing test that calls `.cache_clear()`**

In `tests/test_dashboard_helpers.py`, `test_all_candidate_returns_sorts_the_index_after_concat`
currently reads:

```python
    monkeypatch.setattr(dashboard, "load_backtest", lambda: (full, meta, None, None))
    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pipeline_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_hourly_backtest", lambda: hourly)
    monkeypatch.setattr(dashboard, "load_kronos_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pairs_backtest", lambda: None)
    dashboard._all_candidate_returns.cache_clear()

    combined, _bench = dashboard._all_candidate_returns()
    assert combined.index.is_monotonic_increasing
    dashboard._all_candidate_returns.cache_clear()
```

Remove both `.cache_clear()` lines (the function will no longer have that method once
Step 2 below removes its `@functools.cache` decorator):

```python
    monkeypatch.setattr(dashboard, "load_backtest", lambda: (full, meta, None, None))
    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pipeline_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_hourly_backtest", lambda: hourly)
    monkeypatch.setattr(dashboard, "load_kronos_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pairs_backtest", lambda: None)

    combined, _bench = dashboard._all_candidate_returns()
    assert combined.index.is_monotonic_increasing
```

- [ ] **Step 2: Write the failing freshness tests**

Add to `tests/test_api_research_autoadd.py` (this file already exists specifically for
the auto-add guarantee, so the cache-freshness bug belongs here):

```python
def test_all_candidate_returns_is_not_cached_across_calls(monkeypatch):
    """2026-08-15: _all_candidate_returns() was wrapped in @functools.cache with no
    invalidation -- once a long-lived process (the FastAPI dev server, or app.py's
    Streamlit process) called it once, a newly-committed factory/pipeline curve stayed
    invisible on the Research Lab overview growth chart/correlation table until the
    process restarted. This proves a SECOND call sees data that changed after the
    FIRST call."""
    idx = pd.date_range("2018-01-01", periods=5, freq="D")
    full = pd.DataFrame(
        {"a": [0.001] * 5, "bench_6040": [0.0005] * 5, "spy": [0.0004] * 5}, index=idx
    )
    meta = {"oos_start": idx[0].isoformat()}
    monkeypatch.setattr(dashboard, "load_backtest", lambda: (full, meta, None, None))
    monkeypatch.setattr(dashboard, "load_pipeline_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_hourly_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_kronos_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pairs_backtest", lambda: None)

    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: None)
    combined_before, _bench = dashboard._all_candidate_returns()
    assert "brand_new_factory_candidate" not in combined_before.columns

    new_curve = pd.DataFrame({"brand_new_factory_candidate": [0.002] * 5}, index=idx)
    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: new_curve)
    combined_after, _bench = dashboard._all_candidate_returns()
    assert "brand_new_factory_candidate" in combined_after.columns


def test_load_generated_ledger_is_not_cached_across_calls(tmp_path, monkeypatch):
    """Same bug, same fix, for the factory's own name/family/rationale ledger -- a
    freshly-generated candidate's family/rationale must resolve without a restart."""
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    ledger_before = dashboard._load_generated_ledger()
    assert "tsmom_gen_999d" not in ledger_before

    pd.DataFrame([{"name": "tsmom_gen_999d", "family": "A", "rationale": "..."}]).to_csv(
        tmp_path / "generated_templates.csv", index=False
    )
    ledger_after = dashboard._load_generated_ledger()
    assert "tsmom_gen_999d" in ledger_after


def test_load_pipeline_ledger_is_not_cached_across_calls(tmp_path, monkeypatch):
    """Same bug, same fix, for the research pipeline's own rp_-prefixed ledger."""
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    ledger_before = dashboard._load_pipeline_ledger()
    assert "rp_new_idea_999" not in ledger_before

    pd.DataFrame([{"name": "rp_new_idea_999", "rationale": "..."}]).to_csv(
        tmp_path / "pipeline_ideas.csv", index=False
    )
    ledger_after = dashboard._load_pipeline_ledger()
    assert "rp_new_idea_999" in ledger_after
```

`tests/test_api_research_autoadd.py` already imports both `pandas as pd` and
`from tradefabe import dashboard` at module level -- drop the inline
`import pandas as pd` from `test_load_generated_ledger_is_not_cached_across_calls`
above too (shown inline there only because that test was drafted standalone); both new
tests should rely on the existing top-level imports, no new imports needed.

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_research_autoadd.py -v -n0`
Expected: all three new tests FAIL (the `_before` assertion passes but the `_after`
assertion fails, since the cached first call's result is returned again).

- [ ] **Step 4: Remove the three cache decorators**

In `src/tradefabe/dashboard.py`:

Replace (line 590-591 and the docstring's caching justification, lines 614-616):

```python
@functools.cache
def _all_candidate_returns():
    """Unions every backtest curve source that's actually been PERSISTED to disk --
    full_returns.csv (the original hand-picked roster) plus factory/pipeline/hourly/
    kronos/pairs (#28/#174/#86/#105/#172's own studies) -- into one returns DataFrame,
    plus the 60/40 bench column separately (piggyback_blend() needs it attached to
    `oos`, callers building a correlation/growth chart don't).

    Deliberately excludes piggyback_returns.csv: those 4 columns are COMPOSITE blends
    of strategies already in the union above, not raw candidates, so including them
    would just add trivially-correlated near-duplicates of things already here.

    This is NOT "every strategy ever tested" -- research/factory_run.py's own
    _persist_backtest_curve() docstring is explicit that it only saves a curve for
    the single candidate that wins EACH cycle's promotion, not all ~20/day tested (see
    CLAUDE.md's graveyard.csv note: verdicts are permanent, curves are not, by design,
    to avoid ~20x the disk cost for candidates nobody kept). So this universe is
    bounded by "has a live or once-live paper book," not by graveyard.csv's full count.

    full_returns.csv and pairs_returns.csv carry pre-OOS history (like `full` does
    everywhere else in this module) and get sliced to OOS_START here; factory/pipeline/
    hourly/kronos are already OOS-only at persist time (see each load_*_backtest()'s
    own docstring), so they're used as-is.

    @functools.cache for the same reason _load_generated_ledger() is: called once per
    Research Lab overview/piggyback request, and reads+concats 6 CSVs each time
    otherwise."""
```

with:

```python
def _all_candidate_returns():
    """Unions every backtest curve source that's actually been PERSISTED to disk --
    full_returns.csv (the original hand-picked roster) plus factory/pipeline/hourly/
    kronos/pairs (#28/#174/#86/#105/#172's own studies) -- into one returns DataFrame,
    plus the 60/40 bench column separately (piggyback_blend() needs it attached to
    `oos`, callers building a correlation/growth chart don't).

    Deliberately excludes piggyback_returns.csv: those 4 columns are COMPOSITE blends
    of strategies already in the union above, not raw candidates, so including them
    would just add trivially-correlated near-duplicates of things already here.

    This is NOT "every strategy ever tested" -- research/factory_run.py's own
    _persist_backtest_curve() docstring is explicit that it only saves a curve for
    the single candidate that wins EACH cycle's promotion, not all ~20/day tested (see
    CLAUDE.md's graveyard.csv note: verdicts are permanent, curves are not, by design,
    to avoid ~20x the disk cost for candidates nobody kept). So this universe is
    bounded by "has a live or once-live paper book," not by graveyard.csv's full count.

    full_returns.csv and pairs_returns.csv carry pre-OOS history (like `full` does
    everywhere else in this module) and get sliced to OOS_START here; factory/pipeline/
    hourly/kronos are already OOS-only at persist time (see each load_*_backtest()'s
    own docstring), so they're used as-is.

    Deliberately UNCACHED (2026-08-15) -- this used to be @functools.cache, which never
    invalidates. A long-lived process (the FastAPI dev server, or app.py's Streamlit
    process) that called this once would keep serving that snapshot forever, even after
    the daily factory/pipeline crons committed new curves -- the Research Lab overview's
    growth chart and correlation table froze at whatever the universe looked like at
    process start. Re-reading 6 CSVs per call costs well under a second, which a
    human-facing dashboard's request volume doesn't come close to making a problem."""
```

Replace (line 812-813 and lines 822-827):

```python
@functools.cache
def _load_generated_ledger():
    """Cached lookup of every LIVE-GENERATED candidate ever tested (#28b) -- name ->
    {"family", "rationale"} -- so book_family()/strategy_description() can resolve a
    generated candidate's name (e.g. "tsmom_gen_147d") without a static per-name dict
    entry, which is impossible here: the parameter is drawn fresh each cycle, not fixed
    at review time like TEMPLATES. generated_templates.csv is factory.py's own
    git-tracked audit ledger (every draw logged at generation time, before its verdict
    is known), so this is reading the SAME record the doctrine itself relies on.

    `@functools.cache` (not `@st.cache_data`, which required Streamlit and lived here
    before this module was extracted from app.py) -- book_family()/strategy_description()
    call this per name, so an uncached version turns one loop over graveyard.csv's ~140
    strategies into ~140 redundant CSV re-reads. Caught by CI (#204): a regression test
    that resolves every graveyard name blew a 5s per-test budget on a shared runner,
    passing locally only because local disk was fast enough to hide it."""
```

with:

```python
def _load_generated_ledger():
    """Lookup of every LIVE-GENERATED candidate ever tested (#28b) -- name ->
    {"family", "rationale"} -- so book_family()/strategy_description() can resolve a
    generated candidate's name (e.g. "tsmom_gen_147d") without a static per-name dict
    entry, which is impossible here: the parameter is drawn fresh each cycle, not fixed
    at review time like TEMPLATES. generated_templates.csv is factory.py's own
    git-tracked audit ledger (every draw logged at generation time, before its verdict
    is known), so this is reading the SAME record the doctrine itself relies on.

    Deliberately UNCACHED (2026-08-15) -- this was `@functools.cache` (never invalidated,
    caught alongside the identical bug in _all_candidate_returns()): a freshly-generated
    candidate's family/rationale stayed unresolvable in a long-lived process until
    restart. Re-reading one small CSV per call is cheap enough not to need caching."""
```

Replace (line 836-837 and the last two sentences of the docstring, lines 842-843):

```python
@functools.cache
def _load_pipeline_ledger():
    """Same role as _load_generated_ledger(), for the research pipeline's rp_-prefixed
    names (#174) instead of the factory's _gen_/combo ones. pipeline_ideas.csv has no
    per-row family column (unlike generated_templates.csv) because every pipeline
    proposal -- whichever PRIMITIVES shape it used -- shares the same origin, family "O",
    not a mechanism-specific one; see BOOK_FAMILIES's comment for why. Cached for the
    same reason _load_generated_ledger() is -- see its docstring."""
```

with:

```python
def _load_pipeline_ledger():
    """Same role as _load_generated_ledger(), for the research pipeline's rp_-prefixed
    names (#174) instead of the factory's _gen_/combo ones. pipeline_ideas.csv has no
    per-row family column (unlike generated_templates.csv) because every pipeline
    proposal -- whichever PRIMITIVES shape it used -- shares the same origin, family "O",
    not a mechanism-specific one; see BOOK_FAMILIES's comment for why. Deliberately
    uncached, same reason and same date as _load_generated_ledger() -- see its
    docstring."""
```

- [ ] **Step 5: Run the freshness tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_research_autoadd.py -v -n0`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass. In particular re-check `tests/test_dashboard_helpers.py` (Step 1's
edit) and `tests/test_book_family_grouping.py::test_book_family_resolves_a_generated_name_via_the_ledger_fallback`
(monkeypatches the whole function via `setattr`, unaffected by decorator removal) both
still pass.

- [ ] **Step 7: Commit**

```bash
git add src/tradefabe/dashboard.py tests/test_dashboard_helpers.py tests/test_api_research_autoadd.py
git commit -m "dashboard: remove stale-forever caches on candidate returns and ledgers"
```

---

### Task 6: Full verification, live check, and PR

**Files:** none (verification only)

- [ ] **Step 1: Full backend and frontend suites**

Run: `.venv/bin/pytest tests/ -q && cd frontend && npm test -- --run && npx tsc --noEmit`
Expected: all green, clean.

- [ ] **Step 2: Live check in the browser**

With `tradefabe-api` and `npm run dev` both running (restart `tradefabe-api` first, since
Task 5 changed non-`.py`-adjacent cache *behavior* but the module code itself changed too,
so `reload=True` will pick it up on save -- verify no stale-process artifact from the prior
session lingers by confirming the response shape below):
- Navigate to `/` (Paper Books). Confirm: no family headers, a "Sort by" control with
  exactly `Recently added / Return today / Total return / Sharpe`, defaulting to
  `Total return`. Switch to `Sharpe` and confirm the list reorders and the network request
  is `?sort=sharpe`.
- Navigate to `/research` (Overview tab). Confirm the growth chart and correlation table
  still render (this task doesn't change what they show, only whether they can ever pick
  up new data without a restart -- there is no NEW strategy to demonstrate this with in
  the current dev environment, so this step only confirms no regression).

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin paper-books-sort-and-research-lab-cache
gh pr create --title "Paper Books: sort redesign + Research Lab stale-cache fix" --body-file - <<'EOF'
## Summary
- Paper Books: dropped the Family sort/grouping, added Sharpe (backtest OOS Sharpe), default sort is now Total return.
- Fixed three `@functools.cache`-forever bugs in `dashboard.py` (`_all_candidate_returns`, `_load_generated_ledger`, `_load_pipeline_ledger`) that silently froze the Research Lab overview's growth chart, correlation table, and new-strategy family/rationale resolution at whatever the universe looked like when the serving process started.
- Spec: `docs/superpowers/specs/2026-08-15-paper-books-sort-and-research-lab-cache-design.md`

## Test plan
- [x] `.venv/bin/pytest tests/` -- full suite green, including new sharpe-sort and cache-freshness regression tests.
- [x] `cd frontend && npm test -- --run` -- full suite green, `RowList.test.tsx` rewritten for the flat-only view.
- [x] `cd frontend && npx tsc --noEmit` -- clean.
- [x] Verified live in the browser: Paper Books shows no family grouping, sort options are exactly the four named, default is Total return, switching to Sharpe reorders and requests `sort=sharpe`.
EOF
```

- [ ] **Step 4: Watch CI and merge**

Follow this repo's exact merge protocol (CLAUDE.md): wait for `gh pr checks <N>` to show
both `pytest` and `frontend-tests` as `pass`, then:

```bash
gh pr merge <N> --squash
gh pr view <N> --json state,mergedAt   # must print MERGED before anything below
```

Only after `state` prints `MERGED`, as separate commands (never chained):

```bash
git checkout main && git pull
git branch -D paper-books-sort-and-research-lab-cache
git push origin --delete paper-books-sort-and-research-lab-cache
```
