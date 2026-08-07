# tradefabe dashboard — frontend

The new dashboard UI for [tradefabe](../README.md), replacing `../app.py`'s Streamlit
dashboard one sub-project at a time (see `../CLAUDE.md`'s Layout section and
`../docs/superpowers/specs/2026-08-05-dashboard-foundation-design.md` for the full
rationale and the validated dark/lime theme direction).

**Status: sub-project 1 of 4 (Foundation).** This is currently just a placeholder screen
(`src/App.tsx`) proving the fetch → API → data pipe works — not the real dashboard, and
not wired into the desktop app yet. `../app.py` is still the only live UI.

## Stack

Vite + React + TypeScript + Tailwind CSS + Framer Motion. Theme tokens live in
`tailwind.config.js` (`bg`/`surface`/`accent`/`ink`/`ink-muted` colors, `card` border
radius) — extend that file rather than hardcoding hex values in components.

## Running locally

Needs the API running first (from the repo root):

```sh
.venv/bin/pip install -e ".[dev,desktop,api]"   # once
.venv/bin/tradefabe-api                          # localhost:8000
```

Then, from this directory:

```sh
npm install   # once
npm run dev   # localhost:5173
```

`npm run build` produces a static `dist/` (not yet consumed by anything — the desktop-app
cutover that would serve it is sub-project 4).
