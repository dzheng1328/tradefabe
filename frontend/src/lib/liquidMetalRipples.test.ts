import { describe, expect, it } from "vitest";
import {
  addRipple,
  MAX_RIPPLES,
  pruneExpiredRipples,
  rippleAmplitudeAt,
  RIPPLE_LIFETIME_MS,
  type RipplePoint,
} from "./liquidMetalRipples";

describe("addRipple", () => {
  it("appends a new ripple point", () => {
    const result = addRipple([], { x: 1, y: 2, t: 100 });
    expect(result).toEqual([{ x: 1, y: 2, t: 100 }]);
  });

  it("drops the oldest point once past maxCount, keeping arrival order", () => {
    const existing: RipplePoint[] = Array.from({ length: MAX_RIPPLES }, (_, i) => ({
      x: i, y: 0, t: i,
    }));
    const result = addRipple(existing, { x: 999, y: 0, t: 999 });
    expect(result).toHaveLength(MAX_RIPPLES);
    expect(result[0]).toEqual({ x: 1, y: 0, t: 1 }); // oldest (x:0) dropped
    expect(result[result.length - 1]).toEqual({ x: 999, y: 0, t: 999 });
  });
});

describe("pruneExpiredRipples", () => {
  it("drops points older than RIPPLE_LIFETIME_MS", () => {
    const ripples: RipplePoint[] = [
      { x: 0, y: 0, t: 0 },
      { x: 0, y: 0, t: 500 },
    ];
    const result = pruneExpiredRipples(ripples, RIPPLE_LIFETIME_MS + 500);
    expect(result).toEqual([{ x: 0, y: 0, t: 500 }]);
  });

  it("returns an empty array unchanged", () => {
    expect(pruneExpiredRipples([], 1000)).toEqual([]);
  });
});

describe("rippleAmplitudeAt", () => {
  it("is 1 at the ripple's own location the instant it's added", () => {
    const ripple: RipplePoint = { x: 50, y: 50, t: 1000 };
    expect(rippleAmplitudeAt({ x: 50, y: 50 }, ripple, 1000)).toBeCloseTo(1, 5);
  });

  it("decays toward 0 as the ripple ages", () => {
    const ripple: RipplePoint = { x: 50, y: 50, t: 0 };
    const early = rippleAmplitudeAt({ x: 50, y: 50 }, ripple, 100);
    const late = rippleAmplitudeAt({ x: 50, y: 50 }, ripple, RIPPLE_LIFETIME_MS - 100);
    expect(late).toBeLessThan(early);
  });

  it("is 0 once past RIPPLE_LIFETIME_MS", () => {
    const ripple: RipplePoint = { x: 50, y: 50, t: 0 };
    expect(rippleAmplitudeAt({ x: 50, y: 50 }, ripple, RIPPLE_LIFETIME_MS + 1)).toBe(0);
  });

  it("falls off with distance from the ripple center", () => {
    const ripple: RipplePoint = { x: 0, y: 0, t: 0 };
    const near = rippleAmplitudeAt({ x: 10, y: 0 }, ripple, 0);
    const far = rippleAmplitudeAt({ x: 500, y: 0 }, ripple, 0);
    expect(far).toBeLessThan(near);
  });
});
