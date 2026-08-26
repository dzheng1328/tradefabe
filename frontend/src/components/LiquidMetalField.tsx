import { useEffect, useRef, useState } from "react";
import {
  addRipple,
  pruneExpiredRipples,
  rippleDirection,
  MAX_RIPPLES,
  RIPPLE_LIFETIME_MS,
  type RipplePoint,
} from "../lib/liquidMetalRipples";
import { prefersReducedMotion } from "../lib/motion";

// This background intentionally uses its OWN palette, separate from
// tailwind.config.js's green `accent` used everywhere else in the app --
// Dave's explicit call: a dark royal-blue liquid surface, darkened enough
// that muted grey UI text (e.g. family-header labels) stays clearly
// legible over it. The cursor doesn't paint a highlight on top -- see
// rippleDisplacement() below -- it physically drags the SAME blue pattern,
// so there's only ever one color story to keep in sync here.
const COLOR_BG: [number, number, number] = [0x05 / 255, 0x07 / 255, 0x12 / 255]; // near-black navy
const COLOR_SURFACE: [number, number, number] = [0x19 / 255, 0x27 / 255, 0x64 / 255]; // dim royal blue
const COLOR_SPECULAR: [number, number, number] = [0x8f / 255, 0xb2 / 255, 0xff / 255]; // icy blue-white sheen

const RIPPLE_LIFETIME_SEC = (RIPPLE_LIFETIME_MS / 1000).toFixed(2);

const VERTEX_SRC = `#version 300 es
const vec2 POSITIONS[3] = vec2[3](vec2(-1.0,-1.0), vec2(3.0,-1.0), vec2(-1.0,3.0));
void main() {
  gl_Position = vec4(POSITIONS[gl_VertexID], 0.0, 1.0);
}`;

// Fourth rewrite, 2026-08-12: the metaball attempt (isolated glowing dots)
// missed the mark just as badly as the earlier noise-blotch attempts, per
// live review -- separate glowing blobs read as decoration, not metal. Real
// liquid metal is a CONTINUOUS surface. Domain-warped fbm "flow" field
// (the closest of the earlier attempts, per feedback), mapped to color
// across its FULL range with no smoothstep threshold, so there are zero
// gaps/islands. Fifth pass, same day: recolored to royal blue (from the
// app's usual green) with the ripple waves picked out in yellow -- ripple
// intensity is now tracked as its own scalar (rippleGlow), separate from
// the ambient blue specular sheen, so the wave rings actually read as a
// distinct yellow highlight riding on the blue surface rather than just
// another blue glint.
// Sixth pass, 2026-08-13: two fixes per live feedback. (1) The old point
// specular -- pow(dot(normal,lightDir), 45) -- lit up wherever the noisy
// flow-field normal happened to align with the fixed light direction,
// which scattered as isolated bright dots ("white spots") rather than a
// sheen; replaced with a continuous slope-driven term (no exponent spike)
// so brightness varies smoothly with how steep the surface is instead of
// firing at discrete points. (2) Ripples were purely circular; real
// skimming-object wakes are directional.
// Seventh pass, same day: reimagined again per live feedback. The colored
// "ripple glow" (a yellow highlight painted on TOP of the surface wherever
// a wavefront ring passed) is gone entirely -- it read as decoration
// layered over the liquid, not as the liquid actually moving. What's left
// is only rippleDisplacement() below, which was already warping the
// SAMPLED COORDINATE the flow field is evaluated at (real refraction-style
// displacement, not paint), but the push was too small to see and mostly
// radial. Now the push is large enough to visibly drag the existing blue
// pattern, and its direction follows u_rippleDirs (the cursor's actual
// direction of travel) rather than radiating outward as a ring -- so a
// fast swipe visibly smears the metal along the path, and a stationary
// click still gets a small circular push (falls back to radial when
// there's no travel direction), the way a dropped stone ripples outward
// but a dragged hand drags the water sideways. Overall palette darkened
// substantially (per feedback the sheen was fighting muted grey UI text
// for attention) -- both COLOR_SURFACE and the final brightness multiplier
// dropped.
const FRAGMENT_SRC = `#version 300 es
precision highp float;
uniform vec2 u_resolution;
uniform float u_time;
uniform vec3 u_colorBg;
uniform vec3 u_colorSurface;
uniform vec3 u_colorSpecular;
uniform int u_rippleCount;
uniform vec3 u_ripples[${MAX_RIPPLES}];
uniform vec2 u_rippleDirs[${MAX_RIPPLES}];
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
  for (int i = 0; i < 4; i++) {
    value += amplitude * noise(p);
    p *= 2.0;
    amplitude *= 0.5;
  }
  return value;
}
// Two layers of domain warp: each layer samples fbm at a point offset by the
// previous layer's own fbm output, so the surface continuously reshapes
// (swirls) rather than sliding sideways as a static texture.
float flow(vec2 p, float t) {
  vec2 qa = vec2(fbm(p + vec2(0.0, 0.0) + t * 0.05), fbm(p + vec2(5.2, 1.3) - t * 0.045));
  vec2 qb = vec2(
    fbm(p + 3.0 * qa + vec2(1.7, 9.2) + t * 0.03),
    fbm(p + 3.0 * qa + vec2(8.3, 2.8) - t * 0.035)
  );
  return fbm(p + 3.2 * qb);
}
// The cursor physically pushes the sampled flow-field coordinate, the same
// way dragging a hand through water drags the surface with it -- this is
// the WHOLE ripple effect now, no separate glow/color layered on top.
// pushDir follows u_rippleDirs (the cursor's actual direction of travel at
// the moment this point was laid down) rather than radiating outward from
// the point, so a fast swipe visibly smears the existing pattern along the
// path instead of sending circular rings out from it. A point with no
// travel direction (a stationary click, or the very first sample) falls
// back to pushing radially outward, like a dropped stone's circular
// ripple. pushFade uses its own short time constant (~0.35s) independent
// of RIPPLE_LIFETIME_MS (1.4s, still used just to prune the point buffer)
// so the drag feels responsive rather than smeared out over a long tail.
vec2 rippleDisplacement(vec2 fragPx) {
  vec2 disp = vec2(0.0);
  for (int i = 0; i < ${MAX_RIPPLES}; i++) {
    if (i >= u_rippleCount) break;
    vec3 r = u_ripples[i];
    float age = r.z;
    if (age < 0.0 || age >= ${RIPPLE_LIFETIME_SEC}) continue;
    vec2 wakeVec = u_rippleDirs[i];
    float speedMix = clamp(length(wakeVec), 0.0, 1.0);
    vec2 delta = fragPx - r.xy;
    float dist = length(delta);
    vec2 pushDir = speedMix > 0.001 ? wakeVec / speedMix : (dist > 0.0001 ? delta / dist : vec2(0.0));
    float sizeScale = mix(0.4, 1.6, speedMix);
    float sigma = 55.0 * sizeScale;
    float falloff = exp(-(dist * dist) / (2.0 * sigma * sigma));
    float pushFade = exp(-age / 0.35);
    disp += pushDir * falloff * pushFade * 220.0 * sizeScale;
  }
  return disp;
}
void main() {
  vec2 fragPx = gl_FragCoord.xy;
  vec2 disp = rippleDisplacement(fragPx);
  vec2 p = (fragPx + disp) / u_resolution.y * 2.0;

  float h = flow(p, u_time);

  // Full-range mapping (no smoothstep gate) -- the whole viewport is ONE
  // continuous surface, not islands of color separated by flat black.
  vec3 base = mix(u_colorBg, u_colorSurface, h);

  // Sample the SAME warped field at a finer offset to get the local slope,
  // rather than differentiating the base layer directly -- this puts the
  // sheen detail at a higher frequency than the base undertone. A slope
  // magnitude with smoothstep (no exponent) reads as brightness that varies
  // continuously with how steep the surface is, unlike a fixed-light-dot
  // specular power curve, which only fires where the noisy normal happens
  // to line up with the light and scatters into isolated bright spots.
  float eps = 0.004;
  float hx = flow(p + vec2(eps, 0.0), u_time) - h;
  float hy = flow(p + vec2(0.0, eps), u_time) - h;
  float slope = length(vec2(hx, hy)) / eps;
  float sheen = smoothstep(0.15, 1.4, slope);

  vec3 color = base + u_colorSpecular * sheen * 0.22;
  // Overall surface brightness dialed down hard (was 0.72, then 0.5) --
  // muted grey UI text (e.g. the family-header labels) needs the surface
  // dark enough that it's not competing for attention.
  fragColor = vec4(color * 0.32, 1.0);
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

    let program: WebGLProgram;
    let uResolution: WebGLUniformLocation | null;
    let uTime: WebGLUniformLocation | null;
    let uColorBg: WebGLUniformLocation | null;
    let uColorSurface: WebGLUniformLocation | null;
    let uColorSpecular: WebGLUniformLocation | null;
    let uRippleCount: WebGLUniformLocation | null;
    let uRipples: WebGLUniformLocation | null;
    let uRippleDirs: WebGLUniformLocation | null;
    try {
      program = createProgram(gl);
      gl.useProgram(program);

      uResolution = gl.getUniformLocation(program, "u_resolution");
      uTime = gl.getUniformLocation(program, "u_time");
      uColorBg = gl.getUniformLocation(program, "u_colorBg");
      uColorSurface = gl.getUniformLocation(program, "u_colorSurface");
      uColorSpecular = gl.getUniformLocation(program, "u_colorSpecular");
      uRippleCount = gl.getUniformLocation(program, "u_rippleCount");
      uRipples = gl.getUniformLocation(program, "u_ripples");
      uRippleDirs = gl.getUniformLocation(program, "u_rippleDirs");

      gl.uniform3f(uColorBg, ...COLOR_BG);
      gl.uniform3f(uColorSurface, ...COLOR_SURFACE);
      gl.uniform3f(uColorSpecular, ...COLOR_SPECULAR);
    } catch (err) {
      // A WebGL2 context can exist but still fail to compile/link this
      // shader (e.g. a driver that advertises WebGL2 but rejects it) --
      // that must fall back exactly like "no WebGL2 support", never crash.
      console.warn("liquid-metal: WebGL2 setup failed, falling back", err);
      setUseFallback(true);
      return;
    }

    // Capped at 1x (was 2x) -- this shader samples fbm() up to 6 times per pixel
    // (flow() twice for height, twice more each for the hx/hy slope taps), so 2x
    // device pixel ratio was quadrupling the per-frame fragment cost on any
    // Retina/HiDPI display for a background element nobody looks at up close.
    const dpr = Math.min(window.devicePixelRatio || 1, 1);
    let height = window.innerHeight;
    const reducedMotion = prefersReducedMotion();

    const rippleUniformData = new Float32Array(MAX_RIPPLES * 3);
    const rippleDirData = new Float32Array(MAX_RIPPLES * 2);

    function drawFrame(timeSeconds: number, count: number) {
      gl!.uniform1f(uTime, timeSeconds);
      gl!.uniform1i(uRippleCount, count);
      gl!.uniform3fv(uRipples, rippleUniformData);
      gl!.uniform2fv(uRippleDirs, rippleDirData);
      gl!.drawArrays(gl!.TRIANGLES, 0, 3);
    }

    function resize() {
      const width = window.innerWidth;
      height = window.innerHeight;
      canvas!.width = width * dpr;
      canvas!.height = height * dpr;
      gl!.viewport(0, 0, canvas!.width, canvas!.height);
      gl!.uniform2f(uResolution, canvas!.width, canvas!.height);
      // Setting canvas.width/height above clears the drawing buffer (HTML
      // spec), so under reduced motion -- where nothing else redraws -- a
      // resize would otherwise leave the canvas blank until the next
      // pointer/frame event, which never comes. Redraw the single static
      // frame immediately so it persists across resizes.
      if (reducedMotion) drawFrame(0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    let ripples: RipplePoint[] = [];

    function buildRippleUniforms(now: number): number {
      ripples = pruneExpiredRipples(ripples, now);
      ripples.forEach((r, i) => {
        rippleUniformData[i * 3] = r.x;
        rippleUniformData[i * 3 + 1] = r.y;
        rippleUniformData[i * 3 + 2] = (now - r.t) / 1000;
        rippleDirData[i * 2] = r.dirX ?? 0;
        rippleDirData[i * 2 + 1] = r.dirY ?? 0;
      });
      return ripples.length;
    }

    if (reducedMotion) {
      // resize() (called synchronously above) already drew the single
      // static frame with 0 ripples and will redraw on future resizes;
      // nothing else runs in this mode.
      return () => window.removeEventListener("resize", resize);
    }

    // Raw pointermove fires far faster than one sample per animation frame
    // (a high-polling-rate mouse can fire dozens of times per 16ms) -- only
    // record the latest position here; loop() below consumes it once per
    // rendered frame so the ripple buffer isn't flooded and evicted early.
    let pendingPoint: { x: number; y: number } | null = null;
    function handlePointerMove(e: PointerEvent) {
      // WebGL's fragCoord y-origin is bottom-left; DOM clientY is top-left --
      // flip so the ripple lands where the cursor visually is.
      pendingPoint = { x: e.clientX * dpr, y: (height - e.clientY) * dpr };
    }
    window.addEventListener("pointermove", handlePointerMove);

    // Direction is measured between consumed samples (one per rendered
    // frame, see the pendingPoint comment above), not raw pointermove
    // events, so it reflects on-screen travel rather than mouse-polling
    // noise.
    let lastConsumed: { x: number; y: number; t: number } | null = null;
    let frameId: number;
    const start = performance.now();

    // This is a purely decorative background, not something anyone reads frame-by-frame
    // -- there's no reason to pay a GPU-bound draw call at the display's full refresh
    // rate (60/120/144Hz) for it. Still schedule a rAF every real frame (cheap, CPU-only)
    // so ripple/resize timing stays smooth, but only issue the expensive draw call
    // (flow() samples fbm() up to 6x per pixel) at TARGET_FPS.
    const TARGET_FPS = 30;
    const FRAME_INTERVAL_MS = 1000 / TARGET_FPS;
    let lastDrawMs = -Infinity; // so the very first frame always draws
    function loop(now: number) {
      frameId = requestAnimationFrame(loop);
      if (now - lastDrawMs < FRAME_INTERVAL_MS) return;
      lastDrawMs = now;
      if (pendingPoint) {
        const t = performance.now();
        const { dirX, dirY } = lastConsumed
          ? rippleDirection(pendingPoint.x - lastConsumed.x, pendingPoint.y - lastConsumed.y, t - lastConsumed.t)
          : { dirX: 0, dirY: 0 };
        ripples = addRipple(ripples, { x: pendingPoint.x, y: pendingPoint.y, t, dirX, dirY });
        lastConsumed = { x: pendingPoint.x, y: pendingPoint.y, t };
        pendingPoint = null;
      }
      const count = buildRippleUniforms(now);
      drawFrame((now - start) / 1000, count);
    }
    frameId = requestAnimationFrame(loop);

    // A backgrounded/minimized window still fires rAF in most browsers (throttled, not
    // stopped), and the WKWebView/pywebview desktop shell may not throttle it at all --
    // stop drawing entirely rather than rely on that, so an unfocused tab/window costs
    // zero GPU instead of a throttled-but-nonzero amount.
    function handleVisibilityChange() {
      if (document.hidden) {
        cancelAnimationFrame(frameId);
      } else {
        frameId = requestAnimationFrame(loop);
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [useFallback]);

  if (useFallback) {
    return <div className="ambient-field liquid-metal-fallback" aria-hidden="true" />;
  }

  return <canvas ref={canvasRef} className="ambient-field" aria-hidden="true" />;
}
