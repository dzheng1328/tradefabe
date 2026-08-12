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
    const reducedMotion = prefersReducedMotion();

    const rippleUniformData = new Float32Array(16 * 3);

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
