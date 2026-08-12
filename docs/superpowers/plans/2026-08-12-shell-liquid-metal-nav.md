# Shell Redesign: Liquid-Metal Background + Top-Bar Nav Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ambient constellation-dot background with a cursor-reactive WebGL2 "liquid metal" shader, and move the Paper Books / Research Lab nav from a left sidebar column into a top bar, freeing horizontal space for content.

**Architecture:** A new `LiquidMetalField.tsx` component (raw WebGL2, fullscreen-triangle shader, no library) replaces `ParticleField.tsx` at the same mount point in `App.tsx`. `Nav.tsx` becomes a horizontal bar; `App.tsx`'s layout wraps it above the row-list/detail-panel row instead of beside it. `RowList.tsx`'s toolbar drops the monitor-only filter and repositions/restyles the sort control.

**Tech Stack:** React 19, TypeScript, Tailwind, Framer Motion, Vitest + Testing Library, raw WebGL2 (no new npm dependency).

## Global Constraints

- No backend/API changes. `GET /api/books/summary`'s `show_monitor_only` param already defaults to `True` server-side (`src/tradefabe/api/main.py:68`) — simply not sending it preserves today's default (unfiltered) list.
- Every new animation/interaction needs a `prefers-reduced-motion` equivalent, per this repo's established pattern (`ParticleField`, `RingLoader`).
- `npm test`, `npm run build`, `npm run lint` must all be clean before the PR.
- `fixing-motion-performance` and `fixing-accessibility` skills run against the diff before merge (same gate as every prior shell/detail-panel phase).
- Colors come from `tailwind.config.js`'s existing tokens (`bg` `#0d0f0c`, `surface` `#181c15`, `accent` `#9fe870`) — do not introduce new hex values.

---

### Task 1: Ripple math (`lib/liquidMetalRipples.ts`)

**Files:**
- Create: `frontend/src/lib/liquidMetalRipples.ts`
- Test: `frontend/src/lib/liquidMetalRipples.test.ts`

**Interfaces:**
- Produces: `RipplePoint = { x: number; y: number; t: number }`, `RIPPLE_LIFETIME_MS: number`, `MAX_RIPPLES: number`, `addRipple(ripples: RipplePoint[], point: RipplePoint, maxCount?: number): RipplePoint[]`, `pruneExpiredRipples(ripples: RipplePoint[], now: number): RipplePoint[]`, `rippleAmplitudeAt(point: {x:number;y:number}, ripple: RipplePoint, now: number, sigmaPx?: number): number`. Task 2 imports all of these.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/lib/liquidMetalRipples.test.ts
import { describe, expect, it } from "vitest";
import {
  addRipple,
  MAX_RIPPLES,
  pruneExpiredRipples,
  rippleAmplitudeAt,
  RIPPLE_LIFETIME_MS,
  type RipplePoint,
} from "./liquidMetalRipples";

describe("addRipple", () => {
  it("appends a new ripple point", () => {
    const result = addRipple([], { x: 1, y: 2, t: 100 });
    expect(result).toEqual([{ x: 1, y: 2, t: 100 }]);
  });

  it("drops the oldest point once past maxCount, keeping arrival order", () => {
    const existing: RipplePoint[] = Array.from({ length: MAX_RIPPLES }, (_, i) => ({
      x: i, y: 0, t: i,
    }));
    const result = addRipple(existing, { x: 999, y: 0, t: 999 });
    expect(result).toHaveLength(MAX_RIPPLES);
    expect(result[0]).toEqual({ x: 1, y: 0, t: 1 }); // oldest (x:0) dropped
    expect(result[result.length - 1]).toEqual({ x: 999, y: 0, t: 999 });
  });
});

describe("pruneExpiredRipples", () => {
  it("drops points older than RIPPLE_LIFETIME_MS", () => {
    const ripples: RipplePoint[] = [
      { x: 0, y: 0, t: 0 },
      { x: 0, y: 0, t: 500 },
    ];
    const result = pruneExpiredRipples(ripples, RIPPLE_LIFETIME_MS + 500);
    expect(result).toEqual([{ x: 0, y: 0, t: 500 }]);
  });

  it("returns an empty array unchanged", () => {
    expect(pruneExpiredRipples([], 1000)).toEqual([]);
  });
});

describe("rippleAmplitudeAt", () => {
  it("is 1 at the ripple's own location the instant it's added", () => {
    const ripple: RipplePoint = { x: 50, y: 50, t: 1000 };
    expect(rippleAmplitudeAt({ x: 50, y: 50 }, ripple, 1000)).toBeCloseTo(1, 5);
  });

  it("decays toward 0 as the ripple ages", () => {
    const ripple: RipplePoint = { x: 50, y: 50, t: 0 };
    const early = rippleAmplitudeAt({ x: 50, y: 50 }, ripple, 100);
    const late = rippleAmplitudeAt({ x: 50, y: 50 }, ripple, RIPPLE_LIFETIME_MS - 100);
    expect(late).toBeLessThan(early);
  });

  it("is 0 once past RIPPLE_LIFETIME_MS", () => {
    const ripple: RipplePoint = { x: 50, y: 50, t: 0 };
    expect(rippleAmplitudeAt({ x: 50, y: 50 }, ripple, RIPPLE_LIFETIME_MS + 1)).toBe(0);
  });

  it("falls off with distance from the ripple center", () => {
    const ripple: RipplePoint = { x: 0, y: 0, t: 0 };
    const near = rippleAmplitudeAt({ x: 10, y: 0 }, ripple, 0);
    const far = rippleAmplitudeAt({ x: 500, y: 0 }, ripple, 0);
    expect(far).toBeLessThan(near);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- liquidMetalRipples`
Expected: FAIL — `Failed to resolve import "./liquidMetalRipples"`.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/lib/liquidMetalRipples.ts
// Pure ripple-buffer math for the liquid-metal background (LiquidMetalField.tsx).
// Kept free of WebGL/DOM so it's directly unit-testable, same split as
// particles.ts/ringLoader.ts before it. The fragment shader reimplements this same
// decay/falloff shape per-pixel (GLSL can't call these functions directly) -- see
// LiquidMetalField.tsx's rippleWarp() for the mirrored logic.

export interface RipplePoint {
  x: number;
  y: number;
  t: number; // ms timestamp the point was added (performance.now())
}

// A ripple fully decays to zero amplitude at this age and should be dropped.
export const RIPPLE_LIFETIME_MS = 1400;

// Caps how many ripples are tracked at once -- also the fixed size of the
// u_ripples uniform array in the fragment shader.
export const MAX_RIPPLES = 16;

export function addRipple(
  ripples: RipplePoint[],
  point: RipplePoint,
  maxCount: number = MAX_RIPPLES,
): RipplePoint[] {
  const next = [...ripples, point];
  return next.length > maxCount ? next.slice(next.length - maxCount) : next;
}

export function pruneExpiredRipples(ripples: RipplePoint[], now: number): RipplePoint[] {
  return ripples.filter((r) => now - r.t < RIPPLE_LIFETIME_MS);
}

// Amplitude in [0, 1] at `point` contributed by a single ripple: linear fade by
// age, Gaussian falloff by distance (sigmaPx controls the falloff radius).
export function rippleAmplitudeAt(
  point: { x: number; y: number },
  ripple: RipplePoint,
  now: number,
  sigmaPx = 120,
): number {
  const age = now - ripple.t;
  if (age < 0 || age >= RIPPLE_LIFETIME_MS) return 0;
  const ageFade = 1 - age / RIPPLE_LIFETIME_MS;
  const dx = point.x - ripple.x;
  const dy = point.y - ripple.y;
  const dist2 = dx * dx + dy * dy;
  const spatialFalloff = Math.exp(-dist2 / (2 * sigmaPx * sigmaPx));
  return ageFade * spatialFalloff;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- liquidMetalRipples`
Expected: PASS, all 7 tests green.

- [ ] **Step 5: Commit**

```bash
cd /Users/dzheng/tradefabe
git add frontend/src/lib/liquidMetalRipples.ts frontend/src/lib/liquidMetalRipples.test.ts
git commit -m "Add pure ripple-buffer math for the liquid-metal background"
```

---

### Task 2: `LiquidMetalField.tsx` component

**Files:**
- Create: `frontend/src/components/LiquidMetalField.tsx`
- Test: `frontend/src/components/LiquidMetalField.test.tsx`

**Interfaces:**
- Consumes: `addRipple`, `pruneExpiredRipples`, `RIPPLE_LIFETIME_MS`, `RipplePoint` from `../lib/liquidMetalRipples` (Task 1). `prefersReducedMotion()` from `../lib/motion` (existing).
- Produces: default export `LiquidMetalField` (no props) — a `<canvas className="ambient-field">` when WebGL2 is available, a `<div className="ambient-field liquid-metal-fallback">` otherwise. Task 3 mounts this in `App.tsx` and adds the `.ambient-field`/`.liquid-metal-fallback` CSS rules it depends on.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/components/LiquidMetalField.test.tsx
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LiquidMetalField from "./LiquidMetalField";

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

// A minimal WebGL2 context stub -- enough for LiquidMetalField's setup/draw path
// to run without throwing, so the component takes the "WebGL2 available" branch.
function mockWebGL2Context() {
  return {
    createShader: vi.fn(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    getShaderParameter: vi.fn(() => true),
    getShaderInfoLog: vi.fn(() => ""),
    deleteShader: vi.fn(),
    createProgram: vi.fn(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    getProgramParameter: vi.fn(() => true),
    getProgramInfoLog: vi.fn(() => ""),
    deleteProgram: vi.fn(),
    useProgram: vi.fn(),
    getUniformLocation: vi.fn(() => ({})),
    uniform1f: vi.fn(),
    uniform1i: vi.fn(),
    uniform2f: vi.fn(),
    uniform3f: vi.fn(),
    uniform3fv: vi.fn(),
    viewport: vi.fn(),
    drawArrays: vi.fn(),
    VERTEX_SHADER: 0,
    FRAGMENT_SHADER: 1,
    COMPILE_STATUS: 2,
    LINK_STATUS: 3,
    TRIANGLES: 4,
  } as unknown as WebGL2RenderingContext;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LiquidMetalField", () => {
  it("renders a canvas when WebGL2 is available", () => {
    mockMatchMedia(false);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockWebGL2Context());
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    const { container } = render(<LiquidMetalField />);
    expect(container.querySelector("canvas.ambient-field")).not.toBeNull();
    expect(rafSpy).toHaveBeenCalled();
  });

  it("renders the static fallback when WebGL2 is unavailable", () => {
    mockMatchMedia(false);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const { container, rerender } = render(<LiquidMetalField />);
    rerender(<LiquidMetalField />);
    expect(container.querySelector(".liquid-metal-fallback")).not.toBeNull();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("draws exactly one static frame under prefers-reduced-motion, with no pointer listener or animation loop", () => {
    mockMatchMedia(true);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockWebGL2Context());
    const rafSpy = vi.spyOn(window, "requestAnimationFrame");
    const addEventSpy = vi.spyOn(window, "addEventListener");
    render(<LiquidMetalField />);
    expect(rafSpy).not.toHaveBeenCalled();
    expect(addEventSpy).not.toHaveBeenCalledWith("pointermove", expect.any(Function));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- LiquidMetalField`
Expected: FAIL — `Failed to resolve import "./LiquidMetalField"`.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/LiquidMetalField.tsx
import { useEffect, useRef, useState } from "react";
import {
  addRipple,
  pruneExpiredRipples,
  RIPPLE_LIFETIME_MS,
  type RipplePoint,
} from "../lib/liquidMetalRipples";
import { prefersReducedMotion } from "../lib/motion";

// tailwind.config.js tokens (bg/surface/accent) as 0..1 rgb triplets -- kept in
// sync by hand since the shader can't import the Tailwind config directly.
const COLOR_BG: [number, number, number] = [0x0d / 255, 0x0f / 255, 0x0c / 255];
const COLOR_SURFACE: [number, number, number] = [0x18 / 255, 0x1c / 255, 0x15 / 255];
const COLOR_ACCENT: [number, number, number] = [0x9f / 255, 0xe8 / 255, 0x70 / 255];

const RIPPLE_LIFETIME_SEC = (RIPPLE_LIFETIME_MS / 1000).toFixed(2);

const VERTEX_SRC = `#version 300 es
const vec2 POSITIONS[3] = vec2[3](vec2(-1.0,-1.0), vec2(3.0,-1.0), vec2(-1.0,3.0));
void main() {
  gl_Position = vec4(POSITIONS[gl_VertexID], 0.0, 1.0);
}`;

// Domain-warped fractal noise (fbm) read as a fake height field; its gradient
// approximates a surface normal, driving a cheap fake-specular highlight -- a
// light-reflection trick, not real raytracing. rippleWarp() reimplements
// lib/liquidMetalRipples.ts's rippleAmplitudeAt() shape (age fade x Gaussian
// distance falloff) per-pixel, since GLSL can't call the TS function directly.
const FRAGMENT_SRC = `#version 300 es
precision highp float;
uniform vec2 u_resolution;
uniform float u_time;
uniform vec3 u_colorBg;
uniform vec3 u_colorSurface;
uniform vec3 u_colorAccent;
uniform int u_rippleCount;
uniform vec3 u_ripples[16];
out vec4 fragColor;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 5; i++) {
    value += amplitude * noise(p);
    p *= 2.0;
    amplitude *= 0.5;
  }
  return value;
}
vec2 rippleWarp(vec2 fragPx) {
  vec2 warp = vec2(0.0);
  for (int i = 0; i < 16; i++) {
    if (i >= u_rippleCount) break;
    vec3 r = u_ripples[i];
    float age = r.z;
    if (age < 0.0 || age >= ${RIPPLE_LIFETIME_SEC}) continue;
    float ageFade = 1.0 - age / ${RIPPLE_LIFETIME_SEC};
    vec2 delta = fragPx - r.xy;
    float dist2 = dot(delta, delta);
    float spatial = exp(-dist2 / (2.0 * 120.0 * 120.0));
    float amp = ageFade * spatial;
    vec2 dir = dist2 > 0.0001 ? normalize(delta) : vec2(0.0);
    warp += dir * amp * 40.0;
  }
  return warp;
}
void main() {
  vec2 fragPx = gl_FragCoord.xy;
  vec2 warp = rippleWarp(fragPx);
  vec2 p = (fragPx + warp) / u_resolution.y * 3.0;
  p += vec2(u_time * 0.03, u_time * 0.02);

  float h = fbm(p);
  float eps = 0.01;
  float hx = fbm(p + vec2(eps, 0.0)) - h;
  float hy = fbm(p + vec2(0.0, eps)) - h;
  vec3 normal = normalize(vec3(-hx, -hy, eps));
  vec3 lightDir = normalize(vec3(0.4, 0.6, 0.7));
  float specular = pow(max(dot(normal, lightDir), 0.0), 24.0);

  vec3 base = mix(u_colorBg, u_colorSurface, h);
  vec3 color = mix(base, u_colorAccent, specular * 0.8);
  fragColor = vec4(color, 1.0);
}`;

function compileShader(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`liquid-metal shader compile failed: ${info}`);
  }
  return shader;
}

function createProgram(gl: WebGL2RenderingContext): WebGLProgram {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SRC);
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SRC);
  const program = gl.createProgram()!;
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const info = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`liquid-metal program link failed: ${info}`);
  }
  return program;
}

// Ambient background, replacing the old dot/constellation .particle-field (idea:
// Dave's Phase-1-revision feedback, 2026-08-12) -- cursor-reactive "liquid metal"
// via a WebGL2 fragment shader. Falls back to a static CSS gradient when WebGL2
// isn't available, and freezes to one still frame under prefers-reduced-motion,
// same precedent as ParticleField/RingLoader.
export default function LiquidMetalField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [useFallback, setUseFallback] = useState(false);

  useEffect(() => {
    if (useFallback) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl2");
    if (!gl) {
      setUseFallback(true);
      return;
    }

    const program = createProgram(gl);
    gl.useProgram(program);

    const uResolution = gl.getUniformLocation(program, "u_resolution");
    const uTime = gl.getUniformLocation(program, "u_time");
    const uColorBg = gl.getUniformLocation(program, "u_colorBg");
    const uColorSurface = gl.getUniformLocation(program, "u_colorSurface");
    const uColorAccent = gl.getUniformLocation(program, "u_colorAccent");
    const uRippleCount = gl.getUniformLocation(program, "u_rippleCount");
    const uRipples = gl.getUniformLocation(program, "u_ripples");

    gl.uniform3f(uColorBg, ...COLOR_BG);
    gl.uniform3f(uColorSurface, ...COLOR_SURFACE);
    gl.uniform3f(uColorAccent, ...COLOR_ACCENT);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let height = window.innerHeight;

    function resize() {
      const width = window.innerWidth;
      height = window.innerHeight;
      canvas!.width = width * dpr;
      canvas!.height = height * dpr;
      gl!.viewport(0, 0, canvas!.width, canvas!.height);
      gl!.uniform2f(uResolution, canvas!.width, canvas!.height);
    }
    resize();
    window.addEventListener("resize", resize);

    let ripples: RipplePoint[] = [];
    const rippleUniformData = new Float32Array(16 * 3);

    function buildRippleUniforms(now: number): number {
      ripples = pruneExpiredRipples(ripples, now);
      ripples.forEach((r, i) => {
        rippleUniformData[i * 3] = r.x;
        rippleUniformData[i * 3 + 1] = r.y;
        rippleUniformData[i * 3 + 2] = (now - r.t) / 1000;
      });
      return ripples.length;
    }

    function drawFrame(timeSeconds: number, count: number) {
      gl!.uniform1f(uTime, timeSeconds);
      gl!.uniform1i(uRippleCount, count);
      gl!.uniform3fv(uRipples, rippleUniformData);
      gl!.drawArrays(gl!.TRIANGLES, 0, 3);
    }

    if (prefersReducedMotion()) {
      const count = buildRippleUniforms(performance.now());
      drawFrame(0, count);
      return () => window.removeEventListener("resize", resize);
    }

    function handlePointerMove(e: PointerEvent) {
      // WebGL's fragCoord y-origin is bottom-left; DOM clientY is top-left --
      // flip so the ripple lands where the cursor visually is.
      ripples = addRipple(ripples, {
        x: e.clientX * dpr,
        y: (height - e.clientY) * dpr,
        t: performance.now(),
      });
    }
    window.addEventListener("pointermove", handlePointerMove);

    let frameId: number;
    const start = performance.now();
    function loop(now: number) {
      const count = buildRippleUniforms(now);
      drawFrame((now - start) / 1000, count);
      frameId = requestAnimationFrame(loop);
    }
    frameId = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", handlePointerMove);
    };
  }, [useFallback]);

  if (useFallback) {
    return <div className="ambient-field liquid-metal-fallback" aria-hidden="true" />;
  }

  return <canvas ref={canvasRef} className="ambient-field" aria-hidden="true" />;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- LiquidMetalField`
Expected: PASS, all 3 tests green.

- [ ] **Step 5: Commit**

```bash
cd /Users/dzheng/tradefabe
git add frontend/src/components/LiquidMetalField.tsx frontend/src/components/LiquidMetalField.test.tsx
git commit -m "Add LiquidMetalField: WebGL2 cursor-reactive background"
```

---

### Task 3: Wire in `LiquidMetalField`, retire `ParticleField`

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/index.css`
- Delete: `frontend/src/components/ParticleField.tsx`
- Delete: `frontend/src/components/ParticleField.test.tsx`
- Delete: `frontend/src/lib/particles.ts`
- Delete: `frontend/src/lib/particles.test.ts`

**Interfaces:**
- Consumes: `LiquidMetalField` default export (Task 2).

- [ ] **Step 1: Confirm nothing else references the files being deleted**

Run: `cd frontend && grep -rln "lib/particles\|ParticleField" src/ --include="*.tsx" --include="*.ts"`
Expected output: exactly `src/App.tsx`, `src/components/ParticleField.test.tsx`, `src/components/ParticleField.tsx`, `src/lib/particles.ts` — all four are either being deleted or updated in this task. If anything else shows up, stop and investigate before deleting.

- [ ] **Step 2: Delete the retired files**

```bash
cd /Users/dzheng/tradefabe/frontend
git rm src/components/ParticleField.tsx src/components/ParticleField.test.tsx src/lib/particles.ts src/lib/particles.test.ts
```

- [ ] **Step 3: Swap the import and JSX in `App.tsx`**

In `frontend/src/App.tsx`, change:

```typescript
import ParticleField from "./components/ParticleField";
```

to:

```typescript
import LiquidMetalField from "./components/LiquidMetalField";
```

and change:

```tsx
      <ParticleField />
```

to:

```tsx
      <LiquidMetalField />
```

- [ ] **Step 4: Replace `.particle-field` with `.ambient-field` + `.liquid-metal-fallback` in `index.css`**

In `frontend/src/index.css`, replace this block:

```css
.particle-field {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  display: block;
  width: 100vw;
  height: 100vh;
}

@media (prefers-reduced-motion: reduce) {
  .particle-field {
    /* Still shows the frozen frame drawn once on mount -- see ParticleField.tsx --
       this rule only guarantees no CSS-driven motion sneaks in independently. */
    animation: none;
    transition: none;
  }
}
```

with:

```css
.ambient-field {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  display: block;
  width: 100vw;
  height: 100vh;
}

/* Static gradient shown when WebGL2 isn't available -- see LiquidMetalField.tsx's
   useFallback path. Reduced-motion is handled entirely in JS (one static frame,
   no listeners), so no CSS motion guard is needed here the way .particle-field
   used to need one. */
.liquid-metal-fallback {
  background: radial-gradient(circle at 30% 20%, #181c15 0%, #0d0f0c 70%);
}
```

- [ ] **Step 5: Run the full frontend suite and build**

Run: `cd frontend && npm test && npm run build && npm run lint`
Expected: all green. (`ParticleField.test.tsx`/`particles.test.ts` are gone, so the total test count drops by their tests; `LiquidMetalField.test.tsx`/`liquidMetalRipples.test.ts` from Tasks 1-2 replace them.)

- [ ] **Step 6: Manual smoke test**

Run: `cd frontend && npm run dev`, open `http://localhost:5173`, confirm the liquid-metal background renders and ripples follow the cursor. Toggle "Reduce motion" in OS accessibility settings (or devtools' rendering panel → "Emulate CSS prefers-reduced-motion: reduce") and reload — confirm the background is a static frame with no cursor reactivity.

- [ ] **Step 7: Commit**

```bash
cd /Users/dzheng/tradefabe
git add frontend/src/App.tsx frontend/src/index.css
git commit -m "Replace ParticleField with LiquidMetalField in the app shell"
```

---

### Task 4: `Nav.tsx` → top bar

**Files:**
- Modify: `frontend/src/components/Nav.tsx`
- Modify: `frontend/src/components/Nav.test.tsx`

**Interfaces:**
- No new exports; `Nav`'s default export signature (`() => JSX.Element`, no props) is unchanged. Existing tests for brand glyph, sound toggle text/click/pulse, and unmount-cleanup keep passing unmodified.

- [ ] **Step 1: Write the failing test for the new underline**

Add to `frontend/src/components/Nav.test.tsx`, inside the existing `describe("Nav", ...)` block:

```typescript
  it("shows an accent underline beneath the active Paper Books tab", () => {
    const { container } = render(<Nav />);
    expect(container.querySelector(".family-underline")).not.toBeNull();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- Nav`
Expected: FAIL — `expected null not to be null` (no `.family-underline` element exists yet).

- [ ] **Step 3: Rewrite `Nav.tsx` as a horizontal bar**

Replace the full contents of `frontend/src/components/Nav.tsx`:

```typescript
import { useEffect, useRef, useState } from "react";
import { isSoundEnabled, onSoundPlayed, setSoundEnabled } from "../lib/sound";
import BrandGlyph from "./BrandGlyph";

const PULSE_MS = 500;

export default function Nav() {
  const [soundOn, setSoundOn] = useState(isSoundEnabled());
  const [pulsing, setPulsing] = useState(false);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubscribe = onSoundPlayed(() => {
      setPulsing(true);
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
      pulseTimer.current = setTimeout(() => setPulsing(false), PULSE_MS);
    });
    return () => {
      unsubscribe();
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
    };
  }, []);

  return (
    <nav className="flex items-center gap-6 px-4 h-12 border-b border-white/5 text-sm text-ink-muted shrink-0">
      <div className="text-ink font-bold flex items-center gap-2">
        <BrandGlyph className="w-4 h-4 text-accent shrink-0" />
        tradefabe
      </div>
      <div className="text-ink">
        Paper Books
        <span className="family-underline block h-px w-full mt-1 bg-accent origin-left animate-underline-draw" />
      </div>
      <div>Research Lab</div>
      <button
        className={`ml-auto text-xs text-ink-muted${pulsing ? " sound-toggle-pulse" : ""}`}
        onClick={() => {
          const next = !soundOn;
          setSoundEnabled(next);
          setSoundOn(next);
        }}
      >
        Sound: {soundOn ? "on" : "off"}
      </button>
    </nav>
  );
}
```

Note: `Paper Books` is the only routed page today (`Research Lab` has no route yet — it was already inert plain text before this change, and stays that way; this task only changes layout, not navigation behavior). The underline reuses `.family-underline`/`.animate-underline-draw`, already defined in `index.css` from Phase 2's `RowList` family headers — no new CSS needed.

- [ ] **Step 4: Run the full Nav test file to verify it passes**

Run: `cd frontend && npm test -- Nav`
Expected: PASS, all 5 tests green (4 pre-existing + 1 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/dzheng/tradefabe
git add frontend/src/components/Nav.tsx frontend/src/components/Nav.test.tsx
git commit -m "Turn Nav into a top bar instead of a left sidebar column"
```

---

### Task 5: `App.tsx` layout restructure

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- None — pure JSX restructuring, no new props or exports. `frontend/src/App.tsx` has no existing test file (confirmed: no `App.test.tsx` in the repo), so this task is verified by the manual smoke test in Step 3, plus the full suite staying green (nothing else imports `BooksLayout`/`BooksIndexRedirect` directly).

- [ ] **Step 1: Restructure `BooksLayout` and `BooksIndexRedirect`**

In `frontend/src/App.tsx`, change `BooksLayout` from:

```tsx
function BooksLayout() {
  const { name } = useParams();
  return (
    <div className="h-screen flex overflow-hidden">
      <Nav />
      <div className="flex-1 flex overflow-hidden">
        <div className="w-[30rem] border-r border-white/5 overflow-y-auto">
          <RowList selectedName={name ?? null} />
        </div>
        <main className="flex-1 p-10 overflow-y-auto">
          {name ? <DetailPanel name={name} /> : null}
        </main>
      </div>
    </div>
  );
}
```

to:

```tsx
function BooksLayout() {
  const { name } = useParams();
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Nav />
      <div className="flex-1 flex overflow-hidden">
        <div className="w-[30rem] border-r border-white/5 overflow-y-auto">
          <RowList selectedName={name ?? null} />
        </div>
        <main className="flex-1 p-10 overflow-y-auto">
          {name ? <DetailPanel name={name} /> : null}
        </main>
      </div>
    </div>
  );
}
```

(`flex` → `flex flex-col` on the outer div; everything else is unchanged — `Nav` is now a stacked-above sibling of the `flex-1 flex` row instead of a row-sibling of it.)

Change `BooksIndexRedirect` from:

```tsx
function BooksIndexRedirect() {
  return (
    <div className="h-screen flex overflow-hidden">
      <Nav />
      <div className="w-[30rem] border-r border-white/5 overflow-y-auto">
        <RowList selectedName={null} />
      </div>
    </div>
  );
}
```

to:

```tsx
function BooksIndexRedirect() {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Nav />
      <div className="w-[30rem] border-r border-white/5 overflow-y-auto">
        <RowList selectedName={null} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all green — this is a layout-only change, no test should be affected.

- [ ] **Step 3: Manual smoke test**

Run: `cd frontend && npm run dev`, open `http://localhost:5173`. Confirm: the nav bar spans full width above the content, `RowList` and `DetailPanel` sit side-by-side below it, and selecting a book still routes to `/books/:name` and renders its detail panel correctly.

- [ ] **Step 4: Commit**

```bash
cd /Users/dzheng/tradefabe
git add frontend/src/App.tsx
git commit -m "Stack Nav above content instead of beside it"
```

---

### Task 6: `RowList.tsx` toolbar redesign

**Files:**
- Modify: `frontend/src/components/RowList.tsx`
- Modify: `frontend/src/components/RowList.test.tsx`

**Interfaces:**
- `RowList`'s exported default component signature (`{ selectedName: string | null }`) is unchanged. The `GET /api/books/summary` request URL changes: `show_monitor_only` is no longer sent (backend already defaults to `true`, so this preserves the current unfiltered-list behavior).

- [ ] **Step 1: Update the failing/changing tests**

In `frontend/src/components/RowList.test.tsx`, delete this entire test block (it tests a control that's being removed):

```typescript
  it("refetches with show_monitor_only=false when the checkbox is unchecked", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const checkbox = screen.getByLabelText(/show monitor-only/i);
    await userEvent.click(checkbox);
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("show_monitor_only=false"))).toBe(true);
    });
  });
```

Replace it with a test asserting the param is gone entirely:

```typescript
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
```

In the `"redirects to a still-visible book when the selected one is filtered out"` test, update the comment that references the now-removed checkbox — change:

```typescript
      // tsmom_12m (the currently-selected book) is absent -- as if it was just
      // filtered out by unchecking "Show monitor-only".
```

to:

```typescript
      // tsmom_12m (the currently-selected book) is absent -- as if a sort/data
      // change server-side made it drop out of the list.
```

- [ ] **Step 2: Run the tests to verify the new one fails**

Run: `cd frontend && npm test -- RowList`
Expected: FAIL on `"never sends show_monitor_only -- the monitor-only filter was removed"` — the current fetch URL still includes `&show_monitor_only=true`. The old deleted test's absence causes no failure (it's just gone).

- [ ] **Step 3: Remove the monitor-only state/control, reposition and restyle Sort by**

In `frontend/src/components/RowList.tsx`, remove the `showMonitorOnly` state:

```typescript
  const [showMonitorOnly, setShowMonitorOnly] = useState(true);
```

Change the fetch effect from:

```typescript
  useEffect(() => {
    const sort = SORT_OPTIONS[sortLabel];
    fetch(`http://localhost:8000/api/books/summary?sort=${sort}&show_monitor_only=${showMonitorOnly}`)
      .then((res) => res.json())
      .then((body: SummaryResponse) => {
        setData(body);
        const allBooks = "families" in body ? body.families.flatMap((f) => f.books) : body.books;
        const seen = readSeenBooks();
        setNewBooks(new Set(allBooks.map((b) => b.book).filter((name) => !seen.has(name))));
        localStorage.setItem(SEEN_BOOKS_KEY, JSON.stringify(allBooks.map((b) => b.book)));
        const stillVisible = selectedName !== null && allBooks.some((b) => b.book === selectedName);
        if (!stillVisible) {
          const first = allBooks[0];
          if (first) navigate(`/books/${first.book}`, { replace: true });
        }
      });
  }, [sortLabel, showMonitorOnly, selectedName, navigate]);
```

to:

```typescript
  useEffect(() => {
    const sort = SORT_OPTIONS[sortLabel];
    fetch(`http://localhost:8000/api/books/summary?sort=${sort}`)
      .then((res) => res.json())
      .then((body: SummaryResponse) => {
        setData(body);
        const allBooks = "families" in body ? body.families.flatMap((f) => f.books) : body.books;
        const seen = readSeenBooks();
        setNewBooks(new Set(allBooks.map((b) => b.book).filter((name) => !seen.has(name))));
        localStorage.setItem(SEEN_BOOKS_KEY, JSON.stringify(allBooks.map((b) => b.book)));
        const stillVisible = selectedName !== null && allBooks.some((b) => b.book === selectedName);
        if (!stillVisible) {
          const first = allBooks[0];
          if (first) navigate(`/books/${first.book}`, { replace: true });
        }
      });
  }, [sortLabel, selectedName, navigate]);
```

Change the toolbar JSX from:

```tsx
      <div className="p-4 flex items-center justify-between text-xs">
        <label className="flex items-center gap-2">
          Sort by
          <select
            aria-label="Sort by"
            value={sortLabel}
            onChange={(e) => setSortLabel(e.target.value)}
            className="bg-surface text-ink rounded px-1 py-0.5"
          >
            {Object.keys(SORT_OPTIONS).map((label) => (
              <option key={label} value={label}>{label}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            aria-label="Show monitor-only (backtest-DEAD) books"
            type="checkbox"
            checked={showMonitorOnly}
            onChange={(e) => setShowMonitorOnly(e.target.checked)}
          />
          Show monitor-only
        </label>
      </div>
```

to:

```tsx
      <div className="p-4 pb-2 flex items-center justify-end">
        <label className="flex items-center gap-2 text-xs uppercase text-ink-muted">
          Sort by
          <select
            aria-label="Sort by"
            value={sortLabel}
            onChange={(e) => setSortLabel(e.target.value)}
            className="bg-transparent text-ink-muted uppercase text-xs tracking-wide border-none focus:outline-none focus:text-ink"
          >
            {Object.keys(SORT_OPTIONS).map((label) => (
              <option key={label} value={label} className="normal-case bg-surface text-ink">
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
```

- [ ] **Step 4: Run the full RowList suite to verify it passes**

Run: `cd frontend && npm test -- RowList`
Expected: PASS. Test count drops by one net (one deleted, one added) versus before this task.

- [ ] **Step 5: Commit**

```bash
cd /Users/dzheng/tradefabe
git add frontend/src/components/RowList.tsx frontend/src/components/RowList.test.tsx
git commit -m "Drop the monitor-only filter, reposition and restyle Sort by"
```

---

### Task 7: Full verification, accessibility/motion review, PR

**Files:** none (verification only).

- [ ] **Step 1: Run the full frontend suite, build, and lint**

Run: `cd frontend && npm test && npm run build && npm run lint`
Expected: all clean.

- [ ] **Step 2: Run the backend suite for safety**

Run: `cd /Users/dzheng/tradefabe && .venv/bin/pytest tests/ -n0`
Expected: all passing, unchanged (no backend files touched by this plan).

- [ ] **Step 3: Run `fixing-motion-performance` and `fixing-accessibility` against the diff**

Invoke both skills against the changes from Tasks 1-6 (`LiquidMetalField.tsx`, `Nav.tsx`, `RowList.tsx`, `App.tsx`, `index.css`). Fix anything they flag inline before proceeding. Points worth double-checking going in: the WebGL draw loop only runs `requestAnimationFrame` (compositor-driven GPU work, not layout/paint thrash) and is skipped entirely under reduced motion; the nav's two tabs remain visible text (no icon-only controls needing `aria-label`); the sort `<select>` keeps its existing `aria-label="Sort by"`.

- [ ] **Step 4: Final manual smoke test**

Run both dev servers (`.venv/bin/tradefabe-api` and `cd frontend && npm run dev`), open `http://localhost:5173`, and walk: top bar renders correctly, liquid-metal background ripples on cursor movement, row list has no monitor-only checkbox and Sort by sits top-right in the small-caps style, selecting different books still works, reduced-motion (OS setting or devtools emulation) freezes the background to a still frame.

- [ ] **Step 5: Push and open the PR**

```bash
cd /Users/dzheng/tradefabe
git push -u origin shell-liquid-metal-nav
gh pr create --title "Shell redesign: liquid-metal background + top-bar nav" --body-file - <<'EOF'
## Summary
- Replaces the ambient constellation-dot background (ParticleField) with a cursor-reactive WebGL2 "liquid metal" shader (LiquidMetalField) -- ripple-on-cursor-move, static-gradient fallback when WebGL2 is unavailable, frozen single frame under prefers-reduced-motion
- Moves Nav from a left sidebar column to a top horizontal bar, freeing width for RowList/DetailPanel
- Removes RowList's "Show monitor-only" filter entirely (always shows the full list now, matching today's default); repositions and restyles "Sort by" to match the family-header typography

Standalone amendment to Phase 1 (ops/ui_plan_data.json, PR #209) per Dave's feedback after reviewing Phase 3 live -- see docs/superpowers/specs/2026-08-12-shell-liquid-metal-nav-design.md. Not a new phase in the plan file.

## Test plan
- [x] `npm test` -- all green (new: liquidMetalRipples.test.ts, LiquidMetalField.test.tsx, Nav.test.tsx +1; removed: ParticleField.test.tsx, particles.test.ts; RowList.test.tsx net -0)
- [x] `npm run build` -- clean
- [x] `npm run lint` -- clean
- [x] `pytest tests/ -n0` -- unchanged, passing (no backend changes)
- [x] fixing-motion-performance / fixing-accessibility -- clean
- [x] Manual smoke test against both dev servers
EOF
```

- [ ] **Step 6: Verify CI, then report the PR URL**

Run: `gh pr checks <PR-number>` (poll until non-pending) — confirm both `frontend-tests` and `pytest` pass before considering this plan complete.

---

## Self-Review Notes

- **Spec coverage:** All three spec sections (Nav → top bar, RowList toolbar, liquid-metal background) map to tasks 4/5, 6, and 1-3 respectively. Testing plan, accessibility/motion gate, and rollout (standalone PR, no `ops/ui_plan_data.json` edit) are covered by Task 7.
- **Type consistency:** `RipplePoint`, `RIPPLE_LIFETIME_MS`, `MAX_RIPPLES`, `addRipple`, `pruneExpiredRipples`, `rippleAmplitudeAt` are defined once in Task 1 and consumed with matching names/signatures in Task 2. `LiquidMetalField`'s default export is referenced by the same name in Task 3.
- **Scope check:** Single PR, matches the spec's rollout section exactly.
