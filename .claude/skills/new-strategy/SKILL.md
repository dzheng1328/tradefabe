---
name: new-strategy
description: Add and evaluate a new trading strategy in tradefabe under DOCTRINE. Enforces that the spec is frozen and committed BEFORE any result exists. Use when adding a candidate, a study, or a new strategy family.
disable-model-invocation: true
---

# new-strategy

Doctrine rule 1: *a strategy's spec is frozen before its OOS verdict is rendered.* That is
the only thing separating this lab from backtest-shopping, and it is enforced by **commit
ordering**, not by intent. A spec and its results in one commit prove nothing — the git
history has to show the spec came first.

## 1. Write the spec — and commit it alone

Add the row to the right family in `STRATEGIES.md`: name, signal, universe, rebalance
frequency, and the economic reason it might work. Status `QUEUED`.

State the parameter and where it came from. "Chosen by analogy to the existing daily spec"
is legitimate; "chosen by scanning" is not — a scan means the search itself needs
pre-registering as a range, the way `factory.GENERATION_RANGES` does.

```sh
git checkout -b prereg-<name>
git add STRATEGIES.md
git commit -m "Pre-register <name> (#NN)"   # NO results in this commit
```

Ship it and merge before running anything. The empty-of-results commit *is* the artifact.

## 2. Check the data can support the claim

Before writing the study, confirm the window. DOCTRINE wants OOS from 2018+. If the data
cannot reach that far — every hourly source here starts in 2023 — that is a **regime
limitation**, and the honest response is to state it and label the verdict, not to quietly
narrow the window or amend doctrine to fit.

Rolling-window sources (yfinance intraday is a rolling 730 days) must be **snapshotted to
`artifacts/`**, or the verdict cannot be reproduced later.

## 3. Write the study

Put shared signal functions in `src/tradefabe/`, not in `research/` — if the strategy may
ever become a live book, the study and the book must import **the same function**, or the
book silently drifts from the spec it was judged on.

The null must be **matched**: random strategies at the same frequency, through the same
cost path, aggregated the same way. Evaluate on daily-aggregated returns so `ANN=252`, the
60/40 benchmark, DSR and CPCV stay comparable to the rest of the roster.

## 4. Run it once, and take the answer

```sh
PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" .venv/bin/python research/<study>.py
```

Back up `graveyard.csv` first — `evaluate()` appends, and a crashed mid-run leaves partial
rows. If you re-run, restore the backup so a strategy isn't double-logged (which inflates
`family_n_tested` for everyone else).

**Do not tune after seeing the result.** A different parameter is a NEW row and a NEW
graveyard entry, per roster rule 2. If a deviation was genuinely forced (a benchmark that
makes a gate mathematically unpassable, say), declare it in `STRATEGIES.md` with its reason
and its direction — a deviation that makes ALIVE harder is defensible; one that makes it
easier is a red flag.

## 5. Record the verdict

Update the `STRATEGIES.md` row with the numbers and the mechanism — *why* it died, not just
that it did. The turnover drag, the failed gate, the benchmark it lost to.

Then wire it into the dashboard or it will crash: `app.py` needs a `BOOK_FAMILY` entry, a
`STRATEGY_DESCRIPTIONS` entry, and — if it can become a live book — its curve source in
`book_panel_data()` **and** its call site.

Run `doctrine-auditor` on the result before trusting it.
