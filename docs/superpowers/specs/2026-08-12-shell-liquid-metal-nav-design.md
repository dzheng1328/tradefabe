# Shell redesign: liquid-metal background + top-bar nav

Status: approved, ready for implementation plan.
Amends: Phase 1 (`ops/ui_plan_data.json` phases[1], PR #209) — the ambient background
and nav placement it shipped are being revised.
This is a standalone amendment, not a new phase in the 6-phase dashboard visual-language
plan. `ops/ui_plan_data.json` is not updated by this spec.

## Motivation

Dave's feedback after Phase 3 landed: the ambient constellation-dot background
("nodes in a web pattern") reads as visually weird now that it's seen against real
content, and the left-sidebar `Paper Books` / `Research Lab` nav wastes horizontal
space that could go to content.

## Scope

Three coupled changes to the app shell, all frontend-only, no backend/API changes:

1. `Nav.tsx` becomes a top horizontal bar instead of a left sidebar column.
2. `RowList.tsx`'s toolbar row is redesigned to match: the monitor-only filter is
   removed, and `Sort by` is restyled and repositioned.
3. `ParticleField.tsx` (the ambient dot/constellation background) is replaced by a
   new WebGL2 "liquid metal" shader background, reactive to the cursor.

## 1. Nav → top bar

Today `Nav.tsx` is a `w-fit` left column (`flex flex-col`, brand mark, two
plain-text links, sound toggle pinned to the bottom via `mt-auto`), rendered beside
`RowList`/`DetailPanel` inside `App.tsx`'s `BooksLayout`/`BooksIndexRedirect`.

It becomes a full-width horizontal bar:

```
<nav className="flex items-center gap-6 px-4 h-12 border-b border-white/5">
  <BrandGlyph /> tradefabe
  <NavLink>Paper Books</NavLink>   <!-- active: accent underline, same treatment as
                                        RowList's family-header underline (Phase 2) -->
  <NavLink>Research Lab</NavLink>
  <SoundToggle className="ml-auto" />
</nav>
```

`App.tsx`'s `BooksLayout`/`BooksIndexRedirect` change from a `flex` row containing
`<Nav />` beside the content, to `<Nav />` stacked above a `flex-1 flex` row
containing `RowList` + `DetailPanel`. Nav is no longer a sibling column — it spans
full width above everything.

## 2. RowList toolbar redesign

Current toolbar (`<div className="p-4 flex items-center justify-between text-xs">`):
"Sort by" + `<select>` on the left, "Show monitor-only" checkbox on the right.

Changes:
- **Remove** `showMonitorOnly` state, the checkbox, and the `show_monitor_only` query
  param entirely. The row list always fetches the full, unfiltered list going
  forward — today's default-checked behavior becomes the only behavior. This is a
  permanent removal of the filtering capability, confirmed with Dave.
- **Move** "Sort by" to the right side, where the checkbox used to sit.
- **Restyle** the label and the `<select>` to match the family-header treatment
  (`text-xs uppercase text-ink-muted`, no visible box/border) instead of today's
  plain-text label + boxed `bg-surface` select — it should blend into the row-list
  header rhythm rather than look like a form control.

`RowList.test.tsx` changes: delete both `showMonitorOnly`-checkbox tests, delete
`show_monitor_only` assertions from the sort-refetch test, add an assertion that the
fetch URL never includes `show_monitor_only`.

## 3. Liquid-metal WebGL background

New component `LiquidMetalField.tsx` replaces `<ParticleField />` in `App.tsx`, same
mount position (`position: fixed; inset: 0; z-index: -1; pointer-events: none`).
`ParticleField.tsx`, `ParticleField.test.tsx`, `lib/particles.ts`, and
`lib/particles.test.ts` are deleted — confirmed via grep that nothing else in the
frontend imports from `lib/particles` or references `ParticleField`.

### Rendering

Raw WebGL2 (no library — matches the project's existing zero-dependency canvas
approach in `ParticleField`/`RingLoader`): a fullscreen-triangle vertex shader, and a
fragment shader that:

- Builds a flowing chrome-like surface from domain-warped fractal noise (fbm), using
  the noise field's gradient as a fake surface normal to fake specular highlights (a
  light-reflection trick, not real raytracing).
- Colors from the existing palette — dark base near `#0d0f0c`/`#181c15`, highlights
  near accent `#9fe870` — passed in as uniforms (not hardcoded twice in the shader
  source) so it stays in sync with `tailwind.config.js`'s tokens. Reads as tinted
  chrome, not a generic rainbow-metal effect.
- Takes the last ~16 pointer positions as a uniform array, each carrying an age.
  Every point warps the domain locally with a Gaussian falloff by distance and decay
  by age — this is what produces the ripple-trail look. No ping-pong framebuffer
  simulation needed at this fidelity; distance+age math per pixel is enough.

### Interaction wiring

A `pointermove` listener (throttled to one sample per animation frame) pushes
`{x, y, t: performance.now()}` into a small ripple buffer. A `requestAnimationFrame`
loop prunes expired points, uploads the buffer + elapsed time as uniforms, and draws.
Resize handling mirrors `ParticleField`'s existing dpr-capped pattern
(`Math.min(window.devicePixelRatio || 1, 2)`).

### Testable math

`lib/liquidMetalRipples.ts` holds pure functions, unit-tested directly (same split
as `particles.ts`/`ringLoader.ts` before it):

- `pruneExpiredRipples(ripples, now)` — drops points past their lifetime.
- `rippleAmplitudeAt(point, ripple, now)` — decays with age, falls off with
  distance; both handle an empty ripple list.

The GLSL itself isn't unit-testable — same limitation every canvas component here
already has (`ParticleField`, `RingLoader`).

### Fallback path

On mount, try `canvas.getContext("webgl2")`. If it returns `null`, render a plain
`<div>` with a static CSS gradient (`.liquid-metal-fallback` in `index.css`, same
dark palette) instead of touching WebGL again. No error, no crash — just a simpler
still background.

### Reduced motion

`prefersReducedMotion()` (existing `lib/motion.ts` helper) checked once on mount. If
true: skip the `pointermove` listener and the rAF loop entirely, draw exactly one
static frame (no ripples, `u_time = 0`). Same freeze-to-a-still-frame precedent as
`ParticleField`/`RingLoader` — an equivalent experience, not a degraded one.

## Testing plan

- `liquidMetalRipples.test.ts` — pure function tests per above.
- `LiquidMetalField.test.tsx` — mocked `HTMLCanvasElement.getContext`: renders
  `<canvas>` when WebGL2 is available; renders `.liquid-metal-fallback` when it
  returns `null`; under reduced motion, no `pointermove` listener is attached and
  `requestAnimationFrame` is never called (same assertion style as
  `RingLoader.test.tsx`'s reduced-motion test).
- `Nav.test.tsx` — updated for the top-bar markup: both tabs remain keyboard-reachable
  links/buttons with visible accessible names, sound toggle still present and
  functional.
- `RowList.test.tsx` — per section 2 above.

## Accessibility & motion-performance

Same gate as every prior shell/detail-panel phase: `fixing-motion-performance` and
`fixing-accessibility` skills run against the diff before merge. The shader is
GPU-composited per-pixel work (not a performance concern under those rules), and the
ripple buffer is capped at ~16 points, so CPU-side per-frame math stays trivial.

## Rollout

One branch, one PR, off current `main` (Phase 3 already merged). No entry added to
`ops/ui_plan_data.json` — this is a standalone amendment note, not a new phase.

## Out of scope

- DetailPanel, RingLoader, Intro — untouched. They keep their existing
  particle/dot-based look; this redesign is about the ambient backdrop and nav shell
  only, not every particle-adjacent surface in the app.
- Sub-project 2b (positions/trade-log/risk panel, Phase 4) — unaffected, still
  sequenced after Phase 3.
