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

// Default Gaussian falloff radius (px) used by rippleAmplitudeAt() below and
// mirrored into the fragment shader's sigma constant in LiquidMetalField.tsx,
// so the two implementations can't silently desync.
export const RIPPLE_SIGMA_PX = 120;

export function addRipple(
  ripples: RipplePoint[],
  point: RipplePoint,
  maxCount: number = MAX_RIPPLES,
): RipplePoint[] {
  const next = [...ripples, point];
  return next.length > maxCount ? next.slice(next.length - maxCount) : next;
}

export function pruneExpiredRipples(ripples: RipplePoint[], now: number): RipplePoint[] {
  return ripples.filter((r) => now - r.t <= RIPPLE_LIFETIME_MS);
}

// Amplitude in [0, 1] at `point` contributed by a single ripple: linear fade by
// age, Gaussian falloff by distance (sigmaPx controls the falloff radius).
export function rippleAmplitudeAt(
  point: { x: number; y: number },
  ripple: RipplePoint,
  now: number,
  sigmaPx = RIPPLE_SIGMA_PX,
): number {
  const age = now - ripple.t;
  if (age < 0 || age > RIPPLE_LIFETIME_MS) return 0;
  const ageFade = 1 - age / RIPPLE_LIFETIME_MS;
  const dx = point.x - ripple.x;
  const dy = point.y - ripple.y;
  const dist2 = dx * dx + dy * dy;
  const spatialFalloff = Math.exp(-dist2 / (2 * sigmaPx * sigmaPx));
  return ageFade * spatialFalloff;
}
