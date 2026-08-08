// Pure math for the intro's particle-to-wordmark assembly, kept free of canvas/DOM
// so it's directly unit-testable. Carries forward two things locked in by the Phase 0
// spike (ops/ui_plan_data.json phase 0 validated_params.techniques_to_carry_forward):
// easeOutBack for a slight overshoot-and-settle instead of a plain glide, and sampling
// target points using the rendered bitmap's actual INTEGER pixel dims -- indexing with
// the float CSS width/height instead was a real bug that scrambled nearly every lookup.

export interface TargetPoint {
  x: number;
  y: number;
}

// `alphaAt` reads a rendered glyph bitmap's alpha at an integer pixel coordinate
// (e.g. an offscreen canvas's getImageData). `stride` subsamples so the wordmark
// resolves from a sparse cloud of particles rather than one per pixel.
export function sampleTextTargets(
  width: number,
  height: number,
  stride: number,
  alphaAt: (x: number, y: number) => number,
  threshold = 128,
): TargetPoint[] {
  const w = Math.floor(width);
  const h = Math.floor(height);
  const points: TargetPoint[] = [];
  for (let y = 0; y < h; y += stride) {
    for (let x = 0; x < w; x += stride) {
      if (alphaAt(x, y) >= threshold) points.push({ x, y });
    }
  }
  return points;
}

// Slight overshoot past the target before settling, per Dave's Phase 0 review --
// distinguishes assembly from a plain easeOutCubic glide.
export function easeOutBack(t: number, overshoot = 1.70158): number {
  const clamped = Math.min(1, Math.max(0, t));
  const c1 = overshoot;
  const c3 = c1 + 1;
  const shifted = clamped - 1;
  return 1 + c3 * shifted * shifted * shifted + c1 * shifted * shifted;
}

export function assembleParticlePosition(
  start: { x: number; y: number },
  target: { x: number; y: number },
  t: number,
): { x: number; y: number } {
  const e = easeOutBack(t);
  return {
    x: start.x + (target.x - start.x) * e,
    y: start.y + (target.y - start.y) * e,
  };
}
