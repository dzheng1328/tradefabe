// Pure ring-loader math, mirroring particles.ts's split of math from canvas so it's
// directly unit-testable. Carries forward Phase 0's validated technique (ops/
// ui_plan_data.json phases[0].validated_params.techniques_to_carry_forward): each dot
// springs toward a rotating ring target via a damped mass-spring (semi-implicit
// Euler) instead of snapping straight to the trig position, so the ring settles with
// a slight elastic wobble rather than looking rigidly mechanical.

export interface RingDot {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const STIFFNESS = 140;
const DAMPING = 16;

export function createRingDots(count: number): RingDot[] {
  return Array.from({ length: count }, () => ({ x: 0, y: 0, vx: 0, vy: 0 }));
}

// Phase 0's `wave_depth_px` makes the ring's radius breathe around its circumference
// (a 3-lobed wave) rather than sitting as a perfectly rigid circle.
export function ringTarget(
  index: number,
  count: number,
  radius: number,
  rotation: number,
  waveDepth: number,
): { x: number; y: number } {
  const angle = (index / count) * Math.PI * 2 + rotation;
  const r = radius + waveDepth * Math.sin(angle * 3 + rotation * 2);
  return { x: Math.cos(angle) * r, y: Math.sin(angle) * r };
}

export function springStep(
  dot: RingDot,
  target: { x: number; y: number },
  dt: number,
): RingDot {
  const ax = STIFFNESS * (target.x - dot.x) - DAMPING * dot.vx;
  const ay = STIFFNESS * (target.y - dot.y) - DAMPING * dot.vy;
  const vx = dot.vx + ax * dt;
  const vy = dot.vy + ay * dt;
  return { x: dot.x + vx * dt, y: dot.y + vy * dt, vx, vy };
}
