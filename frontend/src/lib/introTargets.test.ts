import { describe, expect, it } from "vitest";
import { assembleParticlePosition, easeOutBack, sampleTextTargets } from "./introTargets";

describe("sampleTextTargets", () => {
  it("only samples points at or above the alpha threshold", () => {
    // A synthetic 4x1 glyph: opaque at x=0,1 (alpha 255), transparent at x=2,3 (alpha 0).
    const alphaAt = (x: number) => (x < 2 ? 255 : 0);
    const points = sampleTextTargets(4, 1, 1, alphaAt, 128);
    expect(points).toEqual([{ x: 0, y: 0 }, { x: 1, y: 0 }]);
  });

  it("floors float width/height to integer pixel bounds", () => {
    // Regression guard for the Phase 0 spike bug: indexing with the float CSS
    // w/h instead of the canvas's actual integer pixel dims scrambled almost
    // every lookup. A fully-opaque field must never sample x/y >= the floored
    // integer bound (10), even though width/height were passed in as 10.7.
    const alphaAt = () => 255;
    const points = sampleTextTargets(10.7, 10.7, 1, alphaAt, 128);
    for (const p of points) {
      expect(p.x).toBeLessThan(10);
      expect(p.y).toBeLessThan(10);
    }
  });

  it("respects stride, skipping pixels between samples", () => {
    const alphaAt = () => 255;
    const points = sampleTextTargets(6, 1, 2, alphaAt, 128);
    expect(points).toEqual([{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 4, y: 0 }]);
  });
});

describe("easeOutBack", () => {
  it("starts at 0 and ends exactly at 1", () => {
    expect(easeOutBack(0)).toBeCloseTo(0, 10);
    expect(easeOutBack(1)).toBeCloseTo(1, 10);
  });

  it("overshoots past 1 before settling -- the overshoot-and-settle signature", () => {
    const samples = Array.from({ length: 20 }, (_, i) => easeOutBack((i + 1) / 20));
    expect(Math.max(...samples)).toBeGreaterThan(1);
  });

  it("clamps t outside [0, 1]", () => {
    expect(easeOutBack(-1)).toBeCloseTo(0, 10);
    expect(easeOutBack(2)).toBeCloseTo(1, 10);
  });
});

describe("assembleParticlePosition", () => {
  it("stays at the start position at t=0", () => {
    const p = assembleParticlePosition({ x: 10, y: 20 }, { x: 100, y: 200 }, 0);
    expect(p.x).toBeCloseTo(10, 10);
    expect(p.y).toBeCloseTo(20, 10);
  });

  it("lands exactly on the target at t=1", () => {
    const p = assembleParticlePosition({ x: 10, y: 20 }, { x: 100, y: 200 }, 1);
    expect(p.x).toBeCloseTo(100, 10);
    expect(p.y).toBeCloseTo(200, 10);
  });
});
