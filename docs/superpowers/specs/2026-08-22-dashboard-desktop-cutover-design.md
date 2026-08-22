# Dashboard rebuild — Desktop app cutover (sub-project 4) design spec

Status: draft, awaiting Dave's review
Date: 2026-08-22
Related: fills in sub-project 4, left unspecced by
`2026-08-05-dashboard-foundation-design.md` ("Issues for #2–4 get filed when their
sub-project starts, not now"). Picks up an already-started, uncommitted WIP found
sitting in the working tree this session while debugging the desktop app.

## Why this, why now

Sub-projects 1–3 plus the shell redesign and 2b panel work have all shipped (PRs
#203/#204/#209–212/#215/#222). The condition that kept sub-project 4 out of scope through
1–3 — "`app.py` keeps serving the live dashboard exactly as today" — no longer needs to
hold: every `render_*` function in `app.py` now has a shipped React equivalent (see
"Retire `app.py`" below).

This session started by debugging why the desktop app wouldn't open. Root cause of the
*data* symptom (verdicts page frozen) turned out to be a stale local git checkout, unrelated
to the app itself. But the app's actual launch mechanism — spawn `npm run dev` and
`tradefabe-api` as two independent child processes, poll their ports, hope — is exactly the
kind of fragile two-process startup race worth hardening while this cutover happens anyway,
rather than shipping it as-is and hitting the same flakiness again later.

Separately, someone (a prior, uncommitted session) already started sub-project 4's core
work directly in `desktop.py` with no spec written. This doc formalizes that work
retroactively and defines what's left to finish it.

## Current state (uncommitted, in the working tree as of 2026-08-22)

Already done, sitting uncommitted:

- `src/tradefabe/desktop.py` — repointed from spawning `streamlit run app.py` on `:8501`
  to spawning `tradefabe-api` (`:8000`) and `npm run dev` (`:5173`) as two child processes,
  then opening a webview at `:5173`.
- `src/tradefabe/api/main.py` — CORS widened to allow both `http://localhost:5173` and
  `http://127.0.0.1:5173`. Needed because the WKWebView and the `_serving()` port check
  both target the IPv4 `127.0.0.1` form, while Vite defaults to IPv6 loopback (`::1`).
- `frontend/vite.config.ts` — dev server pinned to `host: '127.0.0.1'`, same IPv4/IPv6
  mismatch reason.
- `ops/icon.icns` — binary changed, 59KB → 1.16MB (~20x). Not yet verified why; needs a
  sanity check before this ships (see Open questions).

Verified working in this session: launching `tradefabe-app` directly, and via
`open ~/Applications/tradefabe.app`, both produced a live "tradefabe lab" webview window
at the expected size and position, with backend and frontend both responding. The reported
"bounces once, then nothing" failure could not be reproduced on demand — see item 3 below
for the leading theory and the fix that should also address it.

**Confirmed NOT part of this refactor**, despite sharing the same dirty working tree: the
`frontend/src/components/Intro.tsx` rework, new `frontend/src/lib/introBloom.ts` and
`useScrollSound.ts`, `frontend/src/assets/intro-bloom.jpg`, the deleted `introTargets.ts`,
and the `sound.ts` changes. No existing spec or plan references "bloom" or scroll-sound
work — this is separate, undocumented frontend work that happens to be dirty in the same
tree. It should be split onto its own branch (or stashed) before this branch starts, so
the cutover PR reads clean.

## What's actually left

1. **Verify `ops/icon.icns`.** Confirm the 20x size jump is an intentional higher-resolution
   icon swap, not an accidental corruption or wrong-file copy, before it ships.

2. **Retire `app.py` for real.** Feature-parity check done this session — every `render_*`
   function in `app.py` maps to an already-shipped React component:

   | `app.py` | frontend equivalent |
   |---|---|
   | `render_book_status` / `render_paper_books` | `RowList` + `DetailPanel` |
   | `render_trade_log` | `TradeLog` |
   | `render_carry_risk_panel` | `CarryRiskPanel` |
   | `render_risk_register` | `RiskRegister` |
   | `render_strategy_panel` / `render_strategy_detail` | `StrategyDetail` |
   | `render_research_lab` | `ResearchLab` + `ResearchOverview` + `PiggybackLab` + `GrowthValuesPanel` + `VerdictsTable` |

   All of `app.py`'s Streamlit-free logic already lives in `dashboard.py` per the
   sub-project-1 decision — `app.py` just re-imports it now, so no further moving is
   needed there. What's actually left:
   - Migrate the 6 test files still doing `import app` directly (`test_kronos_live.py`,
     `test_book_panel_data.py`, `test_book_family_grouping.py`,
     `test_live_equity_chart.py`, `test_dead_strategy_detail.py`, `test_retirement.py`) to
     `import tradefabe.dashboard as dashboard` and update call sites. This is the move the
     Foundation spec described but never finished for these six files.
   - Delete `app.py` itself.
   - Drop `streamlit` from `pyproject.toml`'s core `dependencies` list — it's a required
     core dependency today, not an optional extra, so this is a real removal.
   - Remove the stale `:8501` references in `README.md` (lines 30, 67) and rewrite
     CLAUDE.md's Layout section, which currently states `app.py` is "still the only live
     UI" and that the dashboard rebuild is "not wired in yet" — both need to describe the
     new architecture once this ships.

3. **Decide and implement the app's runtime shape.** The two-process dev-server model
   (spawning `npm run dev` fresh on every launch) is the leading suspect for the
   intermittent "opens fine sometimes, bounces-and-nothing other times" behavior reported
   this session: it's a race between two independently-spawned processes, a polling
   `_serving()` check, and a hardcoded 60s timeout, and it requires Node/npm present on the
   machine at every launch rather than only at build time. Two options:

   - **(a) Keep the dev-server model.** No further work beyond what's already uncommitted.
     Keeps both the flakiness risk and the Node/npm runtime dependency.
   - **(b) Static build (recommended).** `ops/build_app.sh` runs `npm run build` once at
     build time; FastAPI mounts and serves `frontend/dist/` directly, so the app becomes
     one process instead of two; `desktop.py` only waits on the API port. This removes the
     two-process race, drops the Node/npm runtime dependency, and is a real step toward the
     "ship it as a standalone installer" direction discussed this session — not full parity
     with a signed `.dmg`/frozen-interpreter build (that's a separate project, see Out of
     scope), but a much smaller lift in the right direction. `ops/build_app.sh`'s existing
     verification step needs a companion check that `frontend/dist/` exists and isn't
     stale, since a stale build would now fail silently at runtime instead of at build time.

   Recommend (b). Needs Dave's confirmation — it changes the desktop app's startup path
   but not the `npm run dev` browser workflow at `localhost:5173`, which stays as-is.

4. **CI gap.** No workflow step runs `npm run build` today — `frontend-tests` in
   `.github/workflows/tests.yml` runs `npm test` only. If (b) is adopted, add a
   `npm run build` step so a broken production build fails the PR instead of failing
   silently on Dave's machine at `ops/build_app.sh` time.

5. **`ops/*.plist` cleanup.** CLAUDE.md already notes these exist unused (nothing
   `launchctl load`ed). Confirm none of them still reference the old
   `streamlit run app.py --server.port 8501` invocation — a stray one is exactly the shape
   of bug that resurfaces later as a duplicate-process/port conflict.

## Testing

- The 6-file test migration (`import app` → `import tradefabe.dashboard as dashboard`) is
  mechanical, no behavior change expected — same discipline as the sub-project-1 move
  ("functions moved, not rewritten").
- If (b) is adopted: a new test asserting `ops/build_app.sh` exits non-zero when
  `frontend/dist/` is missing or empty, mirroring its existing
  `[ -x "$VENV_BIN/tradefabe-app" ]` guard.
- Manual: rebuild and relaunch `~/Applications/tradefabe.app` across a handful of
  cold-start attempts to confirm the window opens reliably — the flakiness reported this
  session couldn't be reproduced from an automated shell and needs a real double-click test
  on Dave's machine.
- `pytest tests/` and `npm test` both green. `doctrine-auditor` not needed — no
  `STRATEGIES.md`/`graveyard.csv` changes.

## Explicitly out of scope

- The Intro/bloom/scroll-sound frontend rework sitting in the same dirty tree — separate,
  undocumented work; split it out before this branch starts.
- A fully standalone signed installer (PyInstaller/briefcase freezing the interpreter,
  GitHub Releases distribution) — a real separate project, only worth starting if the
  static-build fix in item 3 doesn't resolve the actual flakiness Dave's hitting.
- Any change to `state/`, `engine.py`, doctrine logic, or anything the paper-engine
  GitHub Action owns.

## Open questions for Dave

1. Confirm option (b) (static build) over (a) (keep the dev-server spawn) for the packaged
   desktop app's runtime model.
2. Confirm the `ops/icon.icns` size jump is intentional before it ships.
3. Confirm splitting the Intro/bloom/scroll-sound WIP onto its own branch/stash rather than
   folding it into this PR.

## Process

- Branch: `feat/dashboard-desktop-cutover` off `main`, once the unrelated Intro/bloom WIP
  is split out.
- One GitHub issue filed for sub-project 4 — none exists yet (checked `gh issue list`).
- PR body: change + test plan, via quoted heredoc per repo convention.
- `/ship` isn't available to Dave for this project — branch → PR → CI-wait → merge → verify
  → cleanup by hand, following CLAUDE.md's documented gotchas exactly: verify
  `state=MERGED` as its own step before any cleanup, never chain the branch delete onto the
  merge command, quoted heredoc (`<<'EOF'`) for the PR body.
- `doctrine-auditor` not needed — no changes to `STRATEGIES.md` or `graveyard.csv`.
