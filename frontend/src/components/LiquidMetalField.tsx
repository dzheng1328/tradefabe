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

// Third rewrite, 2026-08-12: the two fbm-based attempts both read as a
// textured/grainy surface ("green blotches"), not a sleek modern liquid --
// noise-texture shading was the wrong tool regardless of tuning. This
// version drops noise entirely and blends a handful of perfectly smooth
// circular blobs with a polynomial smooth-min (the standard metaball
// technique), the same family of effect behind Stripe-style mesh-gradient
// backgrounds: a few soft, slowly-drifting shapes that melt into each other
// at their edges rather than a textured field. Cursor reactivity reuses the
// existing ripple buffer (lib/liquidMetalRipples.ts, unchanged) but instead
// of physically displacing a noise field, each live ripple point is simply
// ANOTHER small blob blended into the same field -- so moving the cursor
// leaves a short trail of blobs merging into the ambient ones, which is a
// simpler, cheaper, and (per live review) better-looking effect than the
// wave-displacement math it replaces.
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

// Polynomial smooth-min (Inigo Quilez): blends two signed distances so their
// surfaces merge smoothly instead of meeting at a hard seam -- this IS the
// "liquid" look, no noise texture involved.
float smin(float a, float b, float k) {
  float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
  return mix(b, a, h) - k * h * (1.0 - h);
}

// A handful of large ambient blobs on independent slow Lissajous-style
// drift paths -- deterministic per-index phase/speed/radius so no random
// texture lookup is needed, just smooth periodic motion.
#define AMBIENT_BLOBS 5
float ambientField(vec2 uv, float t) {
  float field = 1.0e5;
  for (int i = 0; i < AMBIENT_BLOBS; i++) {
    float seed = float(i) * 1.37 + 0.5;
    float speed = 0.04 + fract(seed * 3.19) * 0.03;
    float rx = 0.42 + fract(seed * 7.71) * 0.34;
    float ry = 0.38 + fract(seed * 5.33) * 0.34;
    float phase = seed * 6.2831;
    vec2 center = vec2(0.15 + fract(seed * 2.11) * 0.7, 0.15 + fract(seed * 4.87) * 0.7)
      + vec2(sin(t * speed + phase), cos(t * speed * 0.82 + phase * 1.6)) * vec2(rx, ry) * 0.12;
    float radius = 0.075 + 0.012 * sin(t * 0.15 + phase);
    float d = length(uv - center) - radius;
    field = smin(field, d, 0.09);
  }
  return field;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution.xy;
  float aspect = u_resolution.x / u_resolution.y;
  vec2 auv = vec2(uv.x * aspect, uv.y);

  float field = ambientField(auv, u_time);

  // Each live ripple point is a small blob that shrinks and fades with age,
  // merged into the same distance field -- a moving cursor leaves a soft
  // trail of blobs melting into the ambient ones instead of a static mark.
  for (int i = 0; i < ${MAX_RIPPLES}; i++) {
    if (i >= u_rippleCount) break;
    vec3 r = u_ripples[i];
    float age = r.z;
    if (age < 0.0 || age >= ${RIPPLE_LIFETIME_SEC}) continue;
    float ageFade = 1.0 - age / ${RIPPLE_LIFETIME_SEC};
    vec2 center = (r.xy / u_resolution.xy) * vec2(aspect, 1.0);
    float radius = 0.05 * ageFade;
    float d = length(auv - center) - radius;
    field = smin(field, d, 0.10);
  }

  // Soft-edged mask (no hard antialiased circle edge -- a wide smoothstep
  // band is what makes the blobs read as blurred/glowing rather than flat
  // filled shapes) plus a tighter inner core for a subtle brighter center.
  float mask = smoothstep(0.05, -0.05, field);
  float core = smoothstep(0.0, -0.10, field);

  vec3 color = mix(u_colorBg, u_colorSurface, mask * 0.75);
  color = mix(color, u_colorAccent, core * 0.4);

  // Gentle vignette so the corners stay darkest -- reinforces this as a
  // backdrop, not a foreground shape competing with row-list/detail-panel
  // content for attention.
  float vignette = smoothstep(1.0, 0.15, length(uv - 0.5));
  color *= mix(0.82, 1.0, vignette);

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
