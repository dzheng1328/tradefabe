// Pure ripple-buffer math for the liquid-metal background (LiquidMetalField.tsx).
// Kept free of WebGL/DOM so it's directly unit-testable, same split as
// particles.ts/ringLoader.ts before it. The fragment shader reimplements this same
// decay/falloff shape per-pixel (GLSL can't call these functions directly) -- see
// LiquidMetalField.tsx's rippleWarp() for the mirrored logic.

export interface RipplePoint {
  x: number;
  y: number;
  t: number; // ms timestamp the point was added (performance.now())
  // Direction of travel * a 0..1 "how fast" mix, in the same flipped WebGL
  // space as x/y. Magnitude 0 = stationary (isotropic ring); magnitude 1 =
  // fast drag (full wake cone). Absent for callers that don't track motion
  // (e.g. the unit tests above), which is equivalent to a stationary point.
  dirX?: number;
  dirY?: number;
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

// Speed (px/ms, in the flipped WebGL space) at which a drag counts as "fast
// enough" for the ripple to read as a full Kelvin-style wake rather than a
// stationary drop's concentric ring -- this same 0..1 mix also scales the
// ripple's on-screen size (see rippleSizeScale() in LiquidMetalField.tsx),
// so a slow move stays a small ring and a fast one both widens into a wake
// AND grows, matching a real skid. ~800px/s -- reachable by an ordinary
// deliberate mouse swipe, not just an unrealistically fast flick.
const WAKE_FULL_MIX_SPEED = 0.8;

// Direction of travel between two consecutive pointer samples, as a vector
// whose magnitude (0..1) is how strongly the wake-cone shape should apply --
// see RipplePoint.dirX/dirY. Pure function so it's unit-testable without a
// live pointer.
export function rippleDirection(
  dx: number,
  dy: number,
  dtMs: number,
): { dirX: number; dirY: number } {
  const dist = Math.hypot(dx, dy);
  if (dtMs <= 0 || dist < 0.0001) return { dirX: 0, dirY: 0 };
  const speed = dist / dtMs;
  const mix = Math.min(speed / WAKE_FULL_MIX_SPEED, 1);
  return { dirX: (dx / dist) * mix, dirY: (dy / dist) * mix };
}

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
