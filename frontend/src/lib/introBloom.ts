// Pure math for the intro's curl-noise petal bloom, kept free of canvas/DOM so
// it's directly unit-testable (mirrors the old introTargets.ts split). The
// canvas/image compositing lives in Intro.tsx; this module only computes
// deterministic noise fields and per-strand physics.

export function mulberry32(seed: number): () => number {
  let a = seed | 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type Noise2D = (x: number, y: number) => number;

// Seeded Perlin-style gradient noise -- deterministic for a given seed so the
// bloom's shape is reproducible (needed for tests and for a stable "?t=" seek
// harness during development).
export function makeNoise2D(seed: number): Noise2D {
  const rng = mulberry32(seed);
  const p = new Uint8Array(256);
  for (let i = 0; i < 256; i++) p[i] = i;
  for (let i = 255; i > 0; i--) {
    const j = (rng() * (i + 1)) | 0;
    const tmp = p[i];
    p[i] = p[j];
    p[j] = tmp;
  }
  const perm = new Uint8Array(512);
  for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
  const fade = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  const gx = [1, -1, 1, -1, 1, -1, 0, 0];
  const gy = [1, 1, -1, -1, 0, 0, 1, -1];
  const grad = (hash: number, x: number, y: number) => gx[hash & 7] * x + gy[hash & 7] * y;
  return function (x: number, y: number) {
    const X = Math.floor(x) & 255;
    const Y = Math.floor(y) & 255;
    const xf = x - Math.floor(x);
    const yf = y - Math.floor(y);
    const u = fade(xf);
    const v = fade(yf);
    const aa = perm[perm[X] + Y];
    const ab = perm[perm[X] + Y + 1];
    const ba = perm[perm[X + 1] + Y];
    const bb = perm[perm[X + 1] + Y + 1];
    const x1 = lerp(grad(aa, xf, yf), grad(ba, xf - 1, yf), u);
    const x2 = lerp(grad(ab, xf, yf - 1), grad(bb, xf - 1, yf - 1), u);
    return lerp(x1, x2, v);
  };
}

// Curl of the noise potential (finite differences) -- divergence-free, so
// strands flow like a fluid instead of radiating from/collapsing into points.
export function curl(noise2D: Noise2D, x: number, y: number, t: number, eps: number): [number, number] {
  const n1 = noise2D(x, y + eps + t);
  const n2 = noise2D(x, y - eps + t);
  const n3 = noise2D(x + eps, y + t);
  const n4 = noise2D(x - eps, y + t);
  return [(n1 - n2) / (2 * eps), -(n3 - n4) / (2 * eps)];
}

export interface StrandVector {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface StrandParams {
  seedAngle: number;
  reach: number;
  speed: number;
  noiseOffset: number;
  noiseScale: number;
}

// One physics step for a strand: an outward push that decays with both time
// AND proximity to its assigned "reach" (so each petal arm decelerates into a
// curling tip rather than a spike), blended with curl noise that dominates
// once the strand nears/passes its reach.
export function stepStrandPhysics(
  state: StrandVector,
  params: StrandParams,
  noise2D: Noise2D,
  center: { x: number; y: number },
  elapsedMs: number,
  ageMs: number,
  dtMs: number,
): StrandVector {
  const dist = Math.hypot(state.x - center.x, state.y - center.y);
  const timeK = Math.max(0, 1 - ageMs / 900);
  const reachK = Math.max(0, 1 - dist / params.reach);
  const eruptMag = timeK * reachK * 1500;
  const eruptX = Math.cos(params.seedAngle) * eruptMag;
  const eruptY = Math.sin(params.seedAngle) * eruptMag;
  const [cx, cy] = curl(
    noise2D,
    (state.x + params.noiseOffset) * params.noiseScale,
    state.y * params.noiseScale,
    elapsedMs * 0.00035,
    0.9,
  );
  const curlWeight = 1 - reachK;
  const dt = dtMs / 1000;
  let vx = state.vx + (eruptX + cx * params.speed * (0.5 + curlWeight)) * dt;
  let vy = state.vy + (eruptY + cy * params.speed * (0.5 + curlWeight)) * dt;
  vx *= 0.95;
  vy *= 0.95;
  return { x: state.x + vx * dt, y: state.y + vy * dt, vx, vy };
}
