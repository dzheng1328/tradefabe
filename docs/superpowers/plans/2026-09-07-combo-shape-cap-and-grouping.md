# Combo Shape Cap + Paper Books Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the strategy factory from promoting more near-duplicate combo books once a
leg-family shape already has 3 live ones, and make the Paper Books default view group books
so the redundancy that's already live (17 of 35 books are just two combo shapes
reparameterized by lookback window) is visible at a glance instead of scattered through a
flat 35-row list.

**Architecture:** A single pure function, `factory.combo_shape(legs)`, becomes the shared
source of truth for "what shape is this combo" — `research/factory_run.py`'s promotion
ranking uses it to cap live books per shape at `MAX_PER_COMBO_SHAPE = 3` (forward-looking
only; DOCTRINE v1.6 keeps retirement manual, so nothing existing is touched), and
`dashboard.py` uses the identical function to compute a `(group_key, group_label)` per book
that `api/main.py` exposes on every `/api/books/summary` row. The frontend groups by
`group_key` client-side, reusing the row-list's existing "Retired" section-header pattern
under a new class so the two visual treatments don't collide in tests.

**Tech Stack:** Python (pytest), FastAPI, React/TypeScript (Vitest + Testing Library).

**Spec:** No separate spec doc — the design was worked out directly in conversation with
Dave (session `019cCLVvv3jnjazU8dLQ1UAj`, 2026-09-07) after he flagged that live paper books
were dominated by near-duplicate factory combos. Investigation found: 35 active
(non-retired) live books, 19 factory-owned, 17 of those are two leg-family pairings —
`tsmom+tsmom` (family `A`+`A`, 8 books) and `tsmom+low_vol_xsec` (family `A`+`D`, 9 books) —
reparameterized only by lookback window. Root cause: `research/factory_run.py`'s promotion
ranking (`rank_for_promotion()`) picks the single best CPCV/OOS-Sharpe candidate each cycle
with no check against what's already live, and `factory.complementary_pairs()` keeps
re-picking the same low-correlation family pairing regardless of the specific windows drawn
that cycle. Dave's explicit direction: **"max 3 books per combo shape and group them
together on default view."**

## Global Constraints

- **Forward-only, never auto-retires.** DOCTRINE v1.6: retiring a book is Dave's manual
  decision alone, no automatic path (`tests/test_retirement.py` guards this from two
  directions). `MAX_PER_COMBO_SHAPE` only blocks a *new* promotion once a shape is at 3 live
  books — it must never touch, hide, or freeze an existing book. Same non-retirement
  guarantee `MAX_FACTORY_PROMOTED` (#147) already gives; do not weaken it.
- **A capped combo is still fully evaluated and logged to `graveyard.csv`.** Only promotion
  eligibility is affected — same behavior `MAX_FACTORY_PROMOTED` already has when the pool
  is full (`research/factory_run.py`'s own comment on this).
- **`factory.combo_shape()` is the single source of truth for "what shape is this combo."**
  Both the backend cap and the dashboard grouping must call it — never reimplement the
  sorted-family-pair logic a second time in `dashboard.py` or `factory_run.py`.
- **Additive API contract only.** `group_key`/`group_label` are new fields on
  `/api/books/summary` rows; every existing field (`family`, `color`, etc.) stays exactly as
  it is today. Nothing consuming the old shape should break.
- **Never stage `state/paper/`** — it's Action-owned (`CLAUDE.md`'s Automations section).
  This plan touches no `state/` files at all; if `git status` shows any, that's unrelated
  drift from the paper-engine Action, not this change — leave it alone.
- **Test commands:** `.venv/bin/pytest tests/ -q` (backend, ~13s parallel) and
  `cd frontend && npm test` (frontend). Run only the touched test file(s) per-task per Dave's
  stated preference (targeted, not the full suite after every step); run the full suite once
  at the end (see the final task).
- **No DOCTRINE.md amendment.** `MAX_PER_COMBO_SHAPE` is book-opening plumbing, not a
  verdict/gate change — same category as `MAX_FACTORY_PROMOTED`, which lives in `CLAUDE.md`'s
  "Strategy factory" section, not `DOCTRINE.md`'s amendment history. Document it there, in
  the same style.

---

## Task 1: `factory.combo_shape()` — the shared shape function

**Files:**
- Modify: `src/tradefabe/factory.py` (add function after `promote_combo()`, before
  `_leg_signal()` — currently around line 413)
- Test: `tests/test_factory_combo.py` (append at end of file)

**Interfaces:**
- Produces: `factory.combo_shape(legs: list[dict]) -> tuple[str, str]` — `legs` is a list of
  `{"name", "family", "params"}` dicts (the same shape `promote_combo()`'s `spec["legs"]`
  already uses, see `_combo_spec()` in `research/factory_run.py`). Returns the two leg
  families as a **sorted 2-tuple**, e.g. `("A", "D")` for a tsmom+low_vol_xsec pairing,
  `("A", "A")` for a same-family pairing. Order-independent: `combo_shape([{"family":"D"},
  {"family":"A"}])` and `combo_shape([{"family":"A"}, {"family":"D"}])` both return
  `("A", "D")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_factory_combo.py`:

```python
# ---------------------------------------------------------------- shape (2026-09-07)
# Single source of truth for "what shape is this combo" -- shared by the live promotion
# cap (research/factory_run.py's MAX_PER_COMBO_SHAPE) and the dashboard's grouping
# (dashboard.book_group()) so the two can never silently disagree on what counts as a
# duplicate.
def test_combo_shape_is_the_sorted_pair_of_leg_families():
    assert factory.combo_shape([{"family": "D"}, {"family": "A"}]) == ("A", "D")


def test_combo_shape_keeps_a_same_family_pair_as_a_two_tuple():
    assert factory.combo_shape([{"family": "A"}, {"family": "A"}]) == ("A", "A")


def test_combo_shape_is_independent_of_leg_order():
    a_first = factory.combo_shape([{"family": "A"}, {"family": "D"}])
    d_first = factory.combo_shape([{"family": "D"}, {"family": "A"}])
    assert a_first == d_first == ("A", "D")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_combo.py -k combo_shape -v`
Expected: FAIL with `AttributeError: module 'tradefabe.factory' has no attribute 'combo_shape'`

- [ ] **Step 3: Implement `combo_shape()`**

In `src/tradefabe/factory.py`, insert immediately after `promote_combo()` (right before the
`def _leg_signal(leg):` line):

```python
def combo_shape(legs):
    """The unordered pair of primitive families making up a combo, e.g. ("A", "D") for
    a tsmom+low_vol_xsec pairing -- identity only, independent of which leg is which or
    either leg's own parameter window. A same-family combo (tsmom+tsmom) still returns
    a 2-tuple, ("A", "A"). Single source of truth for "what shape is this combo",
    shared by the live promotion cap (research/factory_run.py's MAX_PER_COMBO_SHAPE)
    and the dashboard's grouping (dashboard.book_group()) so the two can never
    silently disagree on what counts as a duplicate."""
    return tuple(sorted(leg["family"] for leg in legs))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_factory_combo.py -v`
Expected: PASS (all tests in the file, not just the new ones — confirms nothing else broke)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/factory.py tests/test_factory_combo.py
git commit -m "factory: add combo_shape(), the shared leg-family-pair identity for a combo"
```

---

## Task 2: `MAX_PER_COMBO_SHAPE` promotion cap

**Files:**
- Modify: `research/factory_run.py` (add constant + `live_combo_shape_counts()` near
  `MAX_FACTORY_PROMOTED`/`factory_owned_count()`; wire into `run_cycle()`)
- Test: `tests/test_factory_run.py` (append)

**Interfaces:**
- Consumes: `factory.combo_shape(legs)` from Task 1; `factory.load_promoted_combos()`,
  `books.is_retired()`, `books.load()` (all pre-existing, same pattern
  `factory_owned_count()` already uses).
- Produces: `factory_run.MAX_PER_COMBO_SHAPE: int` (3); `factory_run.live_combo_shape_counts()
  -> dict[tuple[str,str], int]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_factory_run.py` (after `test_combo_promotion_does_not_also_promote_an_individual`,
before the `_all_promoted_names()` helper — keep that helper and everything below it where it
is):

```python
# ---------------------------------------------------------------- per-shape cap (2026-09-07)
# 17 of 35 real live books turned out to be just two leg-family pairings (tsmom+tsmom,
# tsmom+low_vol_xsec) reparameterized by lookback window -- complementary_pairs() keeps
# re-picking the same low-correlation families regardless of which specific windows got
# drawn that cycle. This caps how many LIVE (non-retired) combo books of the same SHAPE
# (factory.combo_shape()) may exist; a cycle whose combo wins the ranking but is already
# at its shape's cap must fall back to the best individual candidate instead. Explicitly
# NOT a retirement mechanism, same guarantee as MAX_FACTORY_PROMOTED (#147) -- nothing
# existing is ever closed, frozen, or hidden by this cap.
def _seed_combo_pool(shape, count, prefix="preexisting_combo"):
    """Pre-populates the promoted-combos registry with `count` non-retired books,
    monkeypatched (by the caller) to all report the given `shape` via factory.combo_shape
    -- decouples a cap test from which real pair complementary_pairs() happens to draw
    this cycle (that pairing logic is factory.combo_shape()'s own concern, covered in
    test_factory_combo.py)."""
    names = []
    for i in range(count):
        name = f"{prefix}_{i}"
        factory_run.factory.promote_combo({
            "name": name, "freq": "D",
            "legs": [{"name": f"leg_a_{i}", "family": shape[0], "params": {}},
                     {"name": f"leg_b_{i}", "family": shape[1], "params": {}}],
        })
        factory_run.books.save(factory_run.books.load(name))
        names.append(name)
    return names


def _force_combo_to_win(monkeypatch):
    real_rows_for = factory_run.rows_for

    def fake_rows_for(names):
        rows = real_rows_for(names).copy()
        combo = [n for n in names if n.startswith("factory_combo_")]
        assert combo, "the combo must be in the ranking pool for this test to be meaningful"
        rows.loc[rows["strategy"].isin(combo), "cpcv_sharpe_mean"] = 99.0
        rows.loc[~rows["strategy"].isin(combo), "cpcv_sharpe_mean"] = 0.0
        return rows
    monkeypatch.setattr(factory_run, "rows_for", fake_rows_for)


def test_run_cycle_falls_back_to_an_individual_when_the_winning_combos_shape_is_at_cap(
        scratch_graveyard, monkeypatch):
    monkeypatch.setattr(factory_run, "MAX_PER_COMBO_SHAPE", 3)
    _seed_combo_pool(("A", "A"), 3)
    # every combo built this cycle reports shape ("A", "A") regardless of its real legs.
    monkeypatch.setattr(factory_run.factory, "combo_shape", lambda legs: ("A", "A"))
    _force_combo_to_win(monkeypatch)

    evaluated = factory_run.run_cycle(n=4, seed=42, verbose=False)
    combo_names_this_cycle = [n for n in evaluated if n.startswith("factory_combo_")]
    assert combo_names_this_cycle, "a combo must still have been built and evaluated"

    promoted_after = {c["name"] for c in factory_run.factory.load_promoted_combos()}
    assert not (promoted_after & set(combo_names_this_cycle)), (
        "the shape is already at MAX_PER_COMBO_SHAPE -- this cycle's combo must not be "
        "added to the registry despite topping the ranking")
    individuals = set(factory_run.factory.load_promoted()) | \
        {g["name"] for g in factory_run.factory.load_promoted_generated()}
    assert individuals, "promotion must fall back to the best INDIVIDUAL instead"


def test_run_cycle_promotes_the_combo_normally_when_its_shape_is_under_cap(
        scratch_graveyard, monkeypatch):
    monkeypatch.setattr(factory_run, "MAX_PER_COMBO_SHAPE", 3)
    _seed_combo_pool(("A", "A"), 2)   # under the cap of 3
    monkeypatch.setattr(factory_run.factory, "combo_shape", lambda legs: ("A", "A"))
    _force_combo_to_win(monkeypatch)

    evaluated = factory_run.run_cycle(n=4, seed=42, verbose=False)
    combo_names_this_cycle = [n for n in evaluated if n.startswith("factory_combo_")]
    assert combo_names_this_cycle

    promoted_after = {c["name"] for c in factory_run.factory.load_promoted_combos()}
    assert promoted_after & set(combo_names_this_cycle), (
        "under the cap, the winning combo must be promoted exactly like before")


def test_run_cycle_still_evaluates_and_logs_a_capped_combo_to_the_graveyard(
        scratch_graveyard, monkeypatch):
    monkeypatch.setattr(factory_run, "MAX_PER_COMBO_SHAPE", 3)
    _seed_combo_pool(("A", "A"), 3)
    monkeypatch.setattr(factory_run.factory, "combo_shape", lambda legs: ("A", "A"))
    _force_combo_to_win(monkeypatch)

    evaluated = factory_run.run_cycle(n=4, seed=42, verbose=False)
    combo_names_this_cycle = [n for n in evaluated if n.startswith("factory_combo_")]
    gy = pd.read_csv(scratch_graveyard)
    assert set(combo_names_this_cycle) <= set(gy["strategy"]), (
        "a capped combo is still fully evaluated and logged -- only promotion is blocked")


def test_live_combo_shape_counts_excludes_a_manually_retired_book(scratch_graveyard):
    names = _seed_combo_pool(("A", "D"), 2)
    assert factory_run.live_combo_shape_counts() == {("A", "D"): 2}

    factory_run.books.retire(names[0], reason="test: freeing a shape slot")
    assert factory_run.live_combo_shape_counts() == {("A", "D"): 1}


def test_live_combo_shape_counts_keys_by_shape_not_by_individual_combo_name(scratch_graveyard):
    _seed_combo_pool(("A", "A"), 2)
    _seed_combo_pool(("A", "D"), 1)
    assert factory_run.live_combo_shape_counts() == {("A", "A"): 2, ("A", "D"): 1}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_run.py -k "combo_shape_is_at_cap or shape_is_under_cap or logs_the_capped_combo or live_combo_shape_counts" -v`
Expected: FAIL — `AttributeError: module 'factory_run' has no attribute 'MAX_PER_COMBO_SHAPE'` (or `live_combo_shape_counts`)

- [ ] **Step 3: Implement the cap**

In `research/factory_run.py`, right after `factory_owned_count()`'s closing line (currently
line 81, `return sum(1 for n in names if not books.is_retired(books.load(n)))`), insert:

```python


# Per-shape cap (2026-09-07): MAX_FACTORY_PROMOTED alone let the pool concentrate --
# factory.complementary_pairs() keeps picking whichever pair is least-correlated THIS
# cycle, and the same 1-2 leg-family pairings (tsmom+tsmom, tsmom+low_vol_xsec) turn out
# to be structurally the least-correlated pairing most days regardless of the specific
# lookback windows drawn, so the combo pool filled with near-duplicate
# reparameterizations of the same couple of shapes rather than genuinely distinct
# strategies (17 of 35 real live books, 2026-09-07 finding). This caps how many LIVE
# (non-retired) combo books of the same shape (factory.combo_shape() -- the sorted pair
# of leg families) may exist at once; a cycle whose combo wins the ranking but is
# already at its shape's cap falls back to the best individual candidate instead of
# promoting a 4th near-duplicate. The combo is still fully evaluated and logged to
# graveyard.csv either way -- this only affects PROMOTION eligibility, same
# non-retirement guarantee MAX_FACTORY_PROMOTED itself gives (see its own comment).
MAX_PER_COMBO_SHAPE = 3


def live_combo_shape_counts():
    """How many non-retired combo books currently exist per shape (factory.combo_shape())
    -- the live-book side of MAX_PER_COMBO_SHAPE, filtered by books.is_retired() the same
    way factory_owned_count() is, so a manually retired book frees its shape's slot
    immediately even though promote_combo()'s registry entry is never removed."""
    counts = {}
    for c in factory.load_promoted_combos():
        if books.is_retired(books.load(c["name"])):
            continue
        shape = factory.combo_shape(c["legs"])
        counts[shape] = counts.get(shape, 0) + 1
    return counts
```

Then, in `run_cycle()`, find this existing block (currently around line 249-251):

```python
    pool = names_this_cycle + ([combo_name] if combo_spec else [])
    rows = rows_for(pool)
    owned = factory_owned_count()
```

Replace it with:

```python
    pool = names_this_cycle + ([combo_name] if combo_spec else [])
    rows = rows_for(pool)

    if combo_spec:
        shape = factory.combo_shape(combo_spec["legs"])
        shape_count = live_combo_shape_counts().get(shape, 0)
        if shape_count >= MAX_PER_COMBO_SHAPE:
            if verbose:
                print(f"\ncombo shape {shape} already has {shape_count}/{MAX_PER_COMBO_SHAPE} "
                      f"live books -- {combo_name} stays evaluated/logged (graveyard.csv "
                      f"already has its row) but is not eligible to win promotion this "
                      f"cycle; the ranking falls back to the best individual candidate.")
            rows = rows[rows["strategy"] != combo_name]

    owned = factory_owned_count()
```

(The rest of `run_cycle()` — the `if owned >= MAX_FACTORY_PROMOTED:` / `elif len(rows):`
block — is unchanged; it now just sees a `rows` that's already had an over-cap combo
filtered out.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_factory_run.py -v`
Expected: PASS (whole file — confirms the existing combo/promotion tests still pass
unmodified alongside the new ones)

- [ ] **Step 5: Document in CLAUDE.md**

In `CLAUDE.md`'s "Strategy factory" section, immediately after the existing
`MAX_FACTORY_PROMOTED` bullet (the one starting "**Capped at `MAX_FACTORY_PROMOTED`
(#147).**"), add:

```markdown
- **Capped per combo SHAPE too (`MAX_PER_COMBO_SHAPE=3`, 2026-09-07).**
  `MAX_FACTORY_PROMOTED` alone let the pool concentrate: 17 of 35 live books turned out
  to be just two leg-family pairings (tsmom+tsmom, tsmom+low_vol_xsec) reparameterized
  by lookback window, since `complementary_pairs()` keeps picking the same
  low-correlation families regardless of window. A combo's shape
  (`factory.combo_shape()`, the sorted pair of its legs' families) is capped at 3 LIVE
  (non-retired) books; a cycle whose combo wins the ranking but is already at its
  shape's cap falls back to the best individual candidate instead. Existing over-cap
  books are untouched (still v1.6: retirement stays Dave's manual call) -- this only
  stops the pool from getting MORE lopsided going forward.
```

- [ ] **Step 6: Commit**

```bash
git add research/factory_run.py tests/test_factory_run.py CLAUDE.md
git commit -m "factory_run: cap live combo books at 3 per leg-family shape"
```

---

## Task 3: `dashboard.book_group()` — grouping key/label for the Paper Books view

**Files:**
- Modify: `src/tradefabe/dashboard.py` (add `_load_promoted_combo_legs()` after
  `_load_pipeline_ledger()`, currently ending around line 844; add `book_group()`
  immediately after `book_family()`, currently ending around line 909)
- Test: `tests/test_book_family_grouping.py` (append after the existing `book_family`
  tests, before the `group_books_by_family` tests — i.e. after line 89's
  `test_book_family_uses_a_passed_in_generated_ledger_without_loading_its_own`)

**Interfaces:**
- Consumes: `factory.combo_shape(legs)` (Task 1), `factory.load_promoted_combos()`
  (pre-existing), `book_family()`/`BOOK_FAMILIES` (pre-existing, unchanged).
- Produces: `dashboard._load_promoted_combo_legs() -> dict[str, list[dict]]`;
  `dashboard.book_group(name, generated_ledger=None, pipeline_ledger=None,
  combo_legs=None) -> tuple[str, str]` (group_key, group_label).

- [ ] **Step 1: Write the failing tests**

Insert into `tests/test_book_family_grouping.py`, immediately after
`test_book_family_uses_a_passed_in_generated_ledger_without_loading_its_own` (line 89) and
before `test_research_kind_uses_a_passed_in_ledger_without_loading_its_own`:

```python
# ---------------------------------------------------------------- book_group (2026-09-07)
# Finer than book_family() for factory combos specifically: book_family() buckets EVERY
# combo (hand-picked piggyback or factory-discovered) into one "H" family, which hides
# the real redundancy -- most of the factory's combo pool is just two leg-family
# pairings (tsmom+tsmom, tsmom+low_vol_xsec) reparameterized by lookback window.
def test_book_group_returns_plain_family_for_a_non_combo_book():
    assert dashboard.book_group("tsmom_12m", combo_legs={}) == ("A", "Trend / momentum")


def test_book_group_returns_plain_family_h_for_a_hand_picked_piggyback():
    # no legs entry -- piggyback_2a/3/4 aren't factory combos, so they keep the plain
    # "H" bucket, unchanged from book_family().
    assert dashboard.book_group("piggyback_2a", combo_legs={}) == ("H", "Piggyback / combined")


def test_book_group_splits_a_factory_combo_by_its_leg_shape():
    legs = [{"name": "tsmom_gen_10d", "family": "A", "params": {}},
            {"name": "tsmom_gen_200d", "family": "A", "params": {}}]
    key, label = dashboard.book_group(
        "factory_combo_tsmom_gen_10d_tsmom_gen_200d",
        combo_legs={"factory_combo_tsmom_gen_10d_tsmom_gen_200d": legs})
    assert key == "H:A-A"
    assert label == "Combo: Trend / momentum + Trend / momentum"


def test_book_group_gives_a_different_key_to_a_different_leg_shape():
    tt_legs = [{"name": "a", "family": "A", "params": {}}, {"name": "b", "family": "A", "params": {}}]
    ad_legs = [{"name": "c", "family": "A", "params": {}}, {"name": "d", "family": "D", "params": {}}]
    tt_key, _ = dashboard.book_group("factory_combo_a_b", combo_legs={"factory_combo_a_b": tt_legs})
    ad_key, _ = dashboard.book_group("factory_combo_c_d", combo_legs={"factory_combo_c_d": ad_legs})
    assert tt_key != ad_key


def test_book_group_falls_back_to_plain_family_when_the_combo_has_no_legs_entry():
    # defensive: a factory_combo_* name with no matching registry entry (stale data,
    # registry gap) must not crash -- falls back to book_family()'s own pattern match.
    assert dashboard.book_group("factory_combo_something_missing", combo_legs={}) == \
        ("H", "Piggyback / combined")


def test_book_group_uses_a_passed_in_combo_legs_without_loading_its_own(monkeypatch):
    def boom():
        raise AssertionError("book_group() should not load its own combo registry when one is passed in")
    monkeypatch.setattr(dashboard, "_load_promoted_combo_legs", boom)
    assert dashboard.book_group(
        "tsmom_12m", generated_ledger={}, pipeline_ledger={}, combo_legs={},
    ) == ("A", "Trend / momentum")


def test_load_promoted_combo_legs_reads_the_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard.factory, "PROMOTED_COMBOS_PATH", tmp_path / "promoted_combos.json")
    legs = [{"name": "a", "family": "A", "params": {}}, {"name": "b", "family": "D", "params": {}}]
    dashboard.factory.promote_combo({"name": "factory_combo_a_b", "freq": "D", "legs": legs})
    assert dashboard._load_promoted_combo_legs() == {"factory_combo_a_b": legs}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_book_family_grouping.py -k book_group -v`
Expected: FAIL with `AttributeError: module 'tradefabe.dashboard' has no attribute 'book_group'`

- [ ] **Step 3: Implement `_load_promoted_combo_legs()` and `book_group()`**

In `src/tradefabe/dashboard.py`, insert immediately after `_load_pipeline_ledger()`'s closing
line (currently `for _, row in df.iterrows()}`, around line 844), before the
`research_kind()` function:

```python


def _load_promoted_combo_legs():
    """name -> legs (list of {"name","family","params"} dicts), for every combo the
    factory has ever promoted -- RETIRED ONES INCLUDED, since retiring a book never
    removes its promote_combo() registry entry (factory.load_promoted_combos()'s own
    docstring) and a retired book still needs a group to render into on the Paper
    Books "Retired" section. Same deliberately-uncached-per-call convention as
    _load_generated_ledger()/_load_pipeline_ledger() above -- a freshly-promoted combo
    must resolve correctly without a process restart."""
    return {c["name"]: c["legs"] for c in factory.load_promoted_combos()}
```

Then, immediately after `book_family()`'s closing line (currently `return "?"`, around line
909), insert:

```python


def book_group(name, generated_ledger=None, pipeline_ledger=None, combo_legs=None):
    """(group_key, group_label) for the Paper Books default view -- finer than
    book_family() for factory combos specifically. book_family() buckets EVERY combo
    (hand-picked piggyback or factory-discovered) into one "H" family, which hides the
    real redundancy: most of the factory's combo pool turned out to be just two
    leg-family pairings (tsmom+tsmom, tsmom+low_vol_xsec) reparameterized by lookback
    window (2026-09-07 finding -- 17 of 35 live books). A combo whose legs are known
    (via `combo_legs`, see _load_promoted_combo_legs()) groups by its shape
    (factory.combo_shape()); everything else -- including hand-picked piggybacks, which
    have no legs entry here -- falls back to the plain book_family() bucket, unchanged.

    `combo_legs` follows the same opt-in pre-loaded-dict convention as
    generated_ledger/pipeline_ledger: pass it from a per-row-loop caller
    (api/main.py's books_summary()) to load the registry once per request rather than
    once per row."""
    if combo_legs is None:
        combo_legs = _load_promoted_combo_legs()
    legs = combo_legs.get(name)
    if legs:
        shape = factory.combo_shape(legs)
        label = " + ".join(BOOK_FAMILIES.get(f, f) for f in shape)
        return f"H:{'-'.join(shape)}", f"Combo: {label}"
    fam = book_family(name, generated_ledger=generated_ledger, pipeline_ledger=pipeline_ledger)
    return fam, BOOK_FAMILIES.get(fam, "Other")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_book_family_grouping.py -v`
Expected: PASS (whole file)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/dashboard.py tests/test_book_family_grouping.py
git commit -m "dashboard: add book_group(), splitting combo grouping by leg shape"
```

---

## Task 4: Expose `group_key`/`group_label` on `/api/books/summary`

**Files:**
- Modify: `src/tradefabe/api/main.py` (`_row_json()`, `books_summary()`)
- Test: `tests/test_api_books_summary.py`

**Interfaces:**
- Consumes: `dashboard.book_group()` (Task 3), `dashboard._load_promoted_combo_legs()`
  (Task 3).
- Produces: two new fields, `group_key: str` and `group_label: str`, on every row of
  `/api/books/summary`'s `books` array.

- [ ] **Step 1: Write the failing tests**

In `tests/test_api_books_summary.py`, modify `test_summary_row_has_all_expected_keys`
(currently lines 52-60) — change the `for key in (...)` tuple to add the two new keys:

```python
def test_summary_row_has_all_expected_keys():
    client = TestClient(app)
    body = client.get("/api/books/summary?sort=recent").json()
    if not body["books"]:
        return  # no paper state in this environment
    row = body["books"][0]
    for key in ("book", "equity", "return", "last_run", "retired_at", "family",
                "group_key", "group_label", "color", "introduced", "return_today",
                "monitor_only", "sparkline"):
        assert key in row
```

Then append two new tests at the end of the file:

```python
def test_summary_combo_rows_get_a_shape_specific_group_key():
    client = TestClient(app)
    body = client.get("/api/books/summary?sort=recent").json()
    combo_legs = dashboard._load_promoted_combo_legs()
    for row in body["books"]:
        if row["book"] in combo_legs:
            expected_key, expected_label = dashboard.book_group(
                row["book"], combo_legs=combo_legs)
            assert row["group_key"] == expected_key
            assert row["group_label"] == expected_label


def test_summary_loads_the_combo_registry_at_most_once_per_request(monkeypatch):
    """Same regression class as the generated/pipeline ledger loaders (see
    test_summary_loads_each_ledger_at_most_once_per_request above) -- confirm
    _load_promoted_combo_legs() is hoisted to once per request, not once per row."""
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return  # no local paper state in this environment -- nothing to assert

    calls = {"n": 0}
    real = dashboard._load_promoted_combo_legs()

    def counting():
        calls["n"] += 1
        return real
    monkeypatch.setattr(dashboard, "_load_promoted_combo_legs", counting)

    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=recent")
    assert resp.status_code == 200
    assert calls["n"] <= 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_books_summary.py -v`
Expected: FAIL on `test_summary_row_has_all_expected_keys` (`KeyError`/`assert` on
`group_key`) and on `test_summary_combo_rows_get_a_shape_specific_group_key`
(`KeyError: 'group_key'`)

- [ ] **Step 3: Wire it into `_row_json()` and `books_summary()`**

In `src/tradefabe/api/main.py`, change `_row_json()`'s signature and body (currently lines
71-88):

```python
def _row_json(r, *, colors, introduced, return_today, monitor_only, phist,
              generated_ledger, pipeline_ledger, combo_legs):
    name = r["book"]
    intro = introduced.get(name, pd.NaT)
    group_key, group_label = dashboard.book_group(
        name, generated_ledger=generated_ledger, pipeline_ledger=pipeline_ledger,
        combo_legs=combo_legs)
    return {
        "book": name,
        "equity": _finite_or_none(r["equity"]),
        "return": _finite_or_none(r["return"]),
        "last_run": r["last_run"],
        "retired_at": r.get("retired_at") if pd.notna(r.get("retired_at")) else None,
        "family": dashboard.book_family(name, generated_ledger=generated_ledger,
                                        pipeline_ledger=pipeline_ledger),
        "group_key": group_key,
        "group_label": group_label,
        "color": colors.get(name),
        "introduced": intro.isoformat() if pd.notna(intro) else None,
        "return_today": _finite_or_none(return_today.get(name, float("nan"))),
        "monitor_only": monitor_only.get(name, False),
        "sparkline": _sparkline(phist, name),
    }
```

And in `books_summary()` (currently lines 91-115), add the loader call and thread it
through `row_kwargs()`:

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
    generated_ledger = dashboard._load_generated_ledger()
    pipeline_ledger = dashboard._load_pipeline_ledger()
    combo_legs = dashboard._load_promoted_combo_legs()

    def row_kwargs():
        return dict(colors=colors, introduced=introduced, return_today=return_today,
                   monitor_only=monitor_only, phist=phist,
                   generated_ledger=generated_ledger, pipeline_ledger=pipeline_ledger,
                   combo_legs=combo_legs)

    rows = dashboard.sort_books_flat(psum, phist, gy_last, show_monitor_only, sort)
    return {"books": [_row_json(r, **row_kwargs()) for r in rows]}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_books_summary.py tests/test_api_book_detail.py tests/test_api_books_up_for_review.py -v`
Expected: PASS (include the sibling API test files too — `_row_json` is small enough that a
signature typo would be easy to miss if only its own test file is run)

- [ ] **Step 5: Commit**

```bash
git add src/tradefabe/api/main.py tests/test_api_books_summary.py
git commit -m "api: expose group_key/group_label on /api/books/summary rows"
```

---

## Task 5: Frontend — group the Paper Books default view

**Files:**
- Modify: `frontend/src/components/RowList.tsx`
- Modify: `frontend/src/components/RowList.test.tsx` (full rewrite — every existing
  `BookRow`-shaped fixture needs the two new required fields; one test is renamed to match
  the new default behavior; two new tests are added)

**Interfaces:**
- Consumes: `group_key`/`group_label` fields on each row from `/api/books/summary` (Task 4).
- Produces: a `groupRows()` helper and a `SectionHeader` component local to `RowList.tsx`;
  no new exports.

- [ ] **Step 1: Update `RowList.tsx`**

In `frontend/src/components/RowList.tsx`:

1. Extend the `BookRow` type (currently lines 7-18) to add the two new required fields:

```ts
type BookRow = {
  book: string;
  equity: number | null;
  return: number | null;
  return_today: number | null;
  family: string;
  group_key: string;
  group_label: string;
  color: string;
  introduced: string | null;
  monitor_only: boolean;
  retired_at: string | null;
  sparkline: (number | null)[];
};
```

2. Immediately after `clusterRows()` (currently ending at line 232, `return
order.map((sig) => groups.get(sig)!);\n}`), add:

```ts
// Groups rows by group_key (the family, or a factory combo's specific leg-shape --
// see dashboard.book_group() server-side), preserving first-seen order across groups --
// the same "preserve the server's own sort order" convention clusterRows() already
// uses, just keyed on the API's grouping field instead of curve identity. Each
// section still runs its own clusterRows() pass, so identical-curve collapsing keeps
// working WITHIN a group.
function groupRows(rows: BookRow[]): { key: string; label: string; rows: BookRow[] }[] {
  const order: string[] = [];
  const groups = new Map<string, { label: string; rows: BookRow[] }>();
  for (const r of rows) {
    if (!groups.has(r.group_key)) {
      groups.set(r.group_key, { label: r.group_label, rows: [] });
      order.push(r.group_key);
    }
    groups.get(r.group_key)!.rows.push(r);
  }
  return order.map((key) => ({ key, ...groups.get(key)! }));
}

// Same header markup the "Retired" divider already used inline -- extracted so the new
// per-group headers reuse it exactly, but with their OWN underline class
// (`group-underline`, not `family-underline`) so the two are independently countable
// in tests and neither treatment silently absorbs the other's styling hook.
function SectionHeader({ label, underlineClass }: { label: string; underlineClass: string }) {
  return (
    <div className="px-4 pt-2 pb-1">
      <span className="relative text-xs uppercase text-ink-muted">
        {label}
        <span className={`${underlineClass} absolute -bottom-1 left-0 h-px w-6 bg-accent origin-left animate-underline-draw`} />
      </span>
    </div>
  );
}
```

3. Replace the render block (currently lines 379-418, the IIFE starting `{(() => {` through
its closing `})()}`) with:

```tsx
      {(() => {
        // Backend already sorts retired last regardless of sort_key (see
        // dashboard.sort_books_flat's own "_retired" primary sort key).
        const active = data.books.filter((b) => b.retired_at === null);
        const retired = data.books.filter((b) => b.retired_at !== null);
        return (
          <>
            {groupRows(active).map(({ key, label, rows }) => (
              <div key={key}>
                <SectionHeader label={label} underlineClass="group-underline" />
                {clusterRows(rows).map((group) => (
                  <ClusterRow
                    key={group[0].book}
                    group={group}
                    selectedName={selectedName}
                    newBooks={newBooks}
                    deltaMode={deltaMode}
                  />
                ))}
              </div>
            ))}
            {retired.length > 0 && (
              <div>
                <SectionHeader label="Retired" underlineClass="family-underline" />
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

- [ ] **Step 2: Rewrite `RowList.test.tsx`**

Replace the entire file with:

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
      retired_at: null, family: "A", group_key: "A", group_label: "Trend / momentum",
      color: "#2a78d6", introduced: "2026-01-01",
      return_today: 0.012, monitor_only: false, sparkline: [100000, 100500, 101000] },
    { book: "carry_btc_eth", equity: 112003, return: 0.12, last_run: "2026-08-06",
      retired_at: null, family: "D", group_key: "D", group_label: "Defensive anomaly",
      color: "#1baf7a", introduced: "2025-05-01",
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
  it("groups active books by group_key on the default view", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText("carry_btc_eth")).toBeInTheDocument();
    // FLAT_RESPONSE's two books are in different groups (A, D) -- two group headers.
    expect(screen.getByText("Trend / momentum")).toBeInTheDocument();
    expect(screen.getByText("Defensive anomaly")).toBeInTheDocument();
    expect(container.querySelectorAll(".group-underline")).toHaveLength(2);
    // No retired books in FLAT_RESPONSE -- no "Retired" divider, no family-underline at all.
    expect(screen.queryByText("Retired")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".family-underline")).toHaveLength(0);
  });

  it("puts multiple books that share a group_key under one header, not one each", async () => {
    globalThis.fetch = mockFetchWithBooks([
      { book: "factory_combo_tsmom_gen_10d_tsmom_gen_200d", equity: 100500, return: 0.005,
        last_run: "2026-09-06", retired_at: null, family: "H", group_key: "H:A-A",
        group_label: "Combo: Trend / momentum + Trend / momentum", color: "#2a78d6",
        introduced: "2026-08-01", return_today: 0.001, monitor_only: false,
        sparkline: [100000, 100200, 100500] },
      { book: "factory_combo_tsmom_gen_67d_tsmom_gen_300d", equity: 99800, return: -0.002,
        last_run: "2026-09-06", retired_at: null, family: "H", group_key: "H:A-A",
        group_label: "Combo: Trend / momentum + Trend / momentum", color: "#1baf7a",
        introduced: "2026-08-02", return_today: -0.001, monitor_only: false,
        sparkline: [100000, 99900, 99800] },
      { book: "carry_btc_eth", equity: 112003, return: 0.12, last_run: "2026-08-06",
        retired_at: null, family: "D", group_key: "D", group_label: "Defensive anomaly",
        color: "#1baf7a", introduced: "2025-05-01", return_today: 0.001, monitor_only: false,
        sparkline: [110000, 111500, 112003] },
    ]);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText("factory_combo_tsmom_gen_10d_tsmom_gen_200d")).toBeInTheDocument()
    );
    expect(screen.getByText("factory_combo_tsmom_gen_67d_tsmom_gen_300d")).toBeInTheDocument();
    expect(screen.getAllByText("Combo: Trend / momentum + Trend / momentum")).toHaveLength(1);
    // two group headers total: the shared "H:A-A" combo shape, and carry's "D" group.
    expect(container.querySelectorAll(".group-underline")).toHaveLength(2);
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
        retired_at: "2026-07-01T00:00:00", family: "A", group_key: "A",
        group_label: "Trend / momentum", color: "#eda100",
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

  it("shows a monitor-only badge for a backtest-DEAD book promoted anyway", async () => {
    globalThis.fetch = mockFetchWithBooks([
      { book: "factory_combo_tsmom_gen_26d_tsmom_gen_237d", equity: 99958, return: -0.0004,
        last_run: "2026-08-26", retired_at: null, family: "F", group_key: "F",
        group_label: "Volatility risk premium", color: "#e34948",
        introduced: "2026-08-25", return_today: 0, monitor_only: true,
        sparkline: [100000, 99980, 99958] },
    ]);
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText("factory_combo_tsmom_gen_26d_tsmom_gen_237d")).toBeInTheDocument()
    );
    expect(screen.getByText("monitor only")).toBeInTheDocument();
  });

  it("does not show a monitor-only badge for a real (non-monitor-only) book", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.queryByText("monitor only")).not.toBeInTheDocument();
  });

  it("prefers the retired badge over monitor-only when a book is both", async () => {
    globalThis.fetch = mockFetchWithBooks([
      { book: "old_monitor_book", equity: 98000, return: -0.02, last_run: "2026-08-06",
        retired_at: "2026-07-01T00:00:00", family: "A", group_key: "A",
        group_label: "Trend / momentum", color: "#eda100",
        introduced: "2025-01-01", return_today: 0, monitor_only: true,
        sparkline: [99000, 98500, 98000] },
    ]);
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("old_monitor_book")).toBeInTheDocument());
    expect(screen.getByText("retired")).toBeInTheDocument();
    expect(screen.queryByText("monitor only")).not.toBeInTheDocument();
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
    retired_at: null, family: "C", group_key: "C", group_label: "Calendar / seasonality",
    color: "#7d8877", introduced: "2026-07-23",
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

- [ ] **Step 3: Run the tests to verify they pass**

Run: `cd frontend && npm test -- RowList`
Expected: PASS (whole file — the renamed first test and the new clustering test alongside
every pre-existing test, now with `group_key`/`group_label` on their fixtures)

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (confirms the `BookRow` type change didn't break `DetailPanel.tsx` or
any other consumer — grep first: `grep -rn "BookRow" frontend/src/` to confirm `RowList.tsx`
is the only definition site, so no other file needs updating)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RowList.tsx frontend/src/components/RowList.test.tsx
git commit -m "frontend: group Paper Books default view by combo shape / family"
```

---

## Task 6: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: PASS, no new failures or new flakes vs. a run on `main` before this branch.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 3: Manual smoke check (optional but recommended given real live data)**

Run: `PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" .venv/bin/python research/factory_run.py --n 4 --seed 1`
against the REAL `state/paper/promoted_combos.json` (do not commit any resulting `state/`
changes — this is a read-mostly dry run to eyeball the new "combo shape already has N/3 live
books" message actually printing when it should; if it doesn't trigger with a small `--n`,
that's fine, the unit tests already cover the logic directly). Then `cd frontend && npm run
dev` and `tradefabe-api` in another terminal, open the Paper Books view, and confirm the 8
`tsmom+tsmom` and 9 `tsmom+low_vol_xsec` books now render under two distinct "Combo: ..."
headers instead of scattered through the flat list.

- [ ] **Step 4: Hand off for shipping**

This repo's branch/PR/CI-wait/merge/verify/cleanup sequence is encoded in the `ship` skill
(`.claude/skills/ship`), which only Dave can invoke (`disable-model-invocation: true`) — do
not hand-run `git checkout -b`/`gh pr create`/`gh pr merge` yourself. Leave the six commits
above on top of `main`'s working tree uncommitted-branch-wise (i.e. they exist as commits,
just not yet pushed/PR'd), and tell Dave the implementation is done and ready for `/ship`.
