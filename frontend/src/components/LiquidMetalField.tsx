import { useEffect, useRef, useState } from "react";
import {
  addRipple,
  pruneExpiredRipples,
  MAX_RIPPLES,
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

// Domain-warped fbm (fbm sampled through two layers of its own offset field,
// "flow") instead of a single flat fbm layer -- a flat layer just pans as a
// static blob texture (reads as camo/marble, not liquid). Warping the sample
// point through nested noise fields is what actually produces the swirling,
// continuously-reshaping look real fluid simulations approximate. The
// gradient of the final height field still drives a fake-specular highlight
// (a light-reflection trick, not real raytracing), but now at a HIGHER
// frequency than the base color layer so highlights read as thin metallic
// streaks, not "each blob has a bright rim" (which is what made v1 look like
// pinched blotches rather than chrome). Ripples are now an expanding wave
// ring (sin of distance-minus-radius, localized by a Gaussian envelope
// around the current radius) rather than a static one-shot radial bulge --
// a real ripple propagates outward, it doesn't just dent the surface in
// place. Revised 2026-08-12 per Dave's live-review feedback (v1 looked like
// "pinching the areas the cursor hovers over," not flowing liquid metal).
const FRAGMENT_SRC = `#version 300 es
precision highp float;
uniform vec2 u_resolution;
uniform float u_time;
uniform vec3 u_colorBg;
uniform vec3 u_colorSurface;
uniform vec3 u_colorAccent;
uniform int u_rippleCount;
uniform vec3 u_ripples[${MAX_RIPPLES}];
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
// previous layer's own fbm output, so the "flow" direction itself drifts
// over time and space instead of the field just sliding sideways.
float flow(vec2 p, float t) {
  vec2 qa = vec2(fbm(p + vec2(0.0, 0.0) + t * 0.06), fbm(p + vec2(5.2, 1.3) - t * 0.05));
  vec2 qb = vec2(
    fbm(p + 3.1 * qa + vec2(1.7, 9.2) + t * 0.03),
    fbm(p + 3.1 * qa + vec2(8.3, 2.8) - t * 0.04)
  );
  return fbm(p + 3.4 * qb);
}
// An expanding ring wave, not a static bulge: sin(dist - speed*age) creates
// concentric crests that travel outward from the ripple origin, localized to
// the current wavefront radius by a Gaussian envelope so old ripples don't
// leave a permanent dent once their wave has passed.
vec2 rippleDisplacement(vec2 fragPx) {
  vec2 disp = vec2(0.0);
  for (int i = 0; i < ${MAX_RIPPLES}; i++) {
    if (i >= u_rippleCount) break;
    vec3 r = u_ripples[i];
    float age = r.z;
    if (age < 0.0 || age >= ${RIPPLE_LIFETIME_SEC}) continue;
    float ageFade = 1.0 - age / ${RIPPLE_LIFETIME_SEC};
    vec2 delta = fragPx - r.xy;
    float dist = length(delta);
    vec2 dir = dist > 0.0001 ? delta / dist : vec2(0.0);
    float waveSpeed = 340.0;
    float radius = waveSpeed * age;
    float wavefront = exp(-pow((dist - radius) / 70.0, 2.0));
    float wave = sin(dist * 0.05 - waveSpeed * age * 0.05);
    disp += dir * wave * wavefront * ageFade * 16.0;
  }
  return disp;
}
void main() {
  vec2 fragPx = gl_FragCoord.xy;
  vec2 disp = rippleDisplacement(fragPx);
  vec2 p = (fragPx + disp) / u_resolution.y * 1.6;

  float h = flow(p, u_time);

  // Sample the SAME warped field at a finer offset for the normal, rather
  // than differentiating the base layer directly -- this is what puts the
  // specular detail at a different (higher) frequency than the color blobs,
  // so highlights read as streaks across the surface, not blob outlines.
  float eps = 0.006;
  float hx = flow(p + vec2(eps, 0.0), u_time) - h;
  float hy = flow(p + vec2(0.0, eps), u_time) - h;
  vec3 normal = normalize(vec3(-hx, -hy, eps * 3.0));
  vec3 lightDir = normalize(vec3(0.35, 0.55, 0.8));
  float specular = pow(max(dot(normal, lightDir), 0.0), 70.0);
  float rim = pow(1.0 - clamp(normal.z, 0.0, 1.0), 3.0);

  // Narrow smoothstep + a dim multiplier keep this an ambient backdrop, not
  // a foreground element competing with row-list/detail-panel text for
  // attention -- most of the surface stays near-black, with the metallic
  // sheen only showing through in a minority of the frame.
  vec3 base = mix(u_colorBg, u_colorSurface, smoothstep(0.42, 0.82, h));
  vec3 color = base;
  color += u_colorAccent * specular * 0.6;
  color += u_colorAccent * rim * 0.03;
  fragColor = vec4(color * 0.8, 1.0);
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
    let uColorAccent: WebGLUniformLocation | null;
    let uRippleCount: WebGLUniformLocation | null;
    let uRipples: WebGLUniformLocation | null;
    try {
      program = createProgram(gl);
      gl.useProgram(program);

      uResolution = gl.getUniformLocation(program, "u_resolution");
      uTime = gl.getUniformLocation(program, "u_time");
      uColorBg = gl.getUniformLocation(program, "u_colorBg");
      uColorSurface = gl.getUniformLocation(program, "u_colorSurface");
      uColorAccent = gl.getUniformLocation(program, "u_colorAccent");
      uRippleCount = gl.getUniformLocation(program, "u_rippleCount");
      uRipples = gl.getUniformLocation(program, "u_ripples");

      gl.uniform3f(uColorBg, ...COLOR_BG);
      gl.uniform3f(uColorSurface, ...COLOR_SURFACE);
      gl.uniform3f(uColorAccent, ...COLOR_ACCENT);
    } catch (err) {
      // A WebGL2 context can exist but still fail to compile/link this
      // shader (e.g. a driver that advertises WebGL2 but rejects it) --
      // that must fall back exactly like "no WebGL2 support", never crash.
      console.warn("liquid-metal: WebGL2 setup failed, falling back", err);
      setUseFallback(true);
      return;
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let height = window.innerHeight;
    const reducedMotion = prefersReducedMotion();

    const rippleUniformData = new Float32Array(MAX_RIPPLES * 3);

    function drawFrame(timeSeconds: number, count: number) {
      gl!.uniform1f(uTime, timeSeconds);
      gl!.uniform1i(uRippleCount, count);
      gl!.uniform3fv(uRipples, rippleUniformData);
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

    let frameId: number;
    const start = performance.now();
    function loop(now: number) {
      if (pendingPoint) {
        ripples = addRipple(ripples, { x: pendingPoint.x, y: pendingPoint.y, t: performance.now() });
        pendingPoint = null;
      }
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
