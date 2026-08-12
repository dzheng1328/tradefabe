import { describe, expect, it } from "vitest";
import { connectDots, createParticles, stepParticle, twinkleAlpha } from "./particles";

const PARAMS = { count: 5, driftSpeed: 0.046, dotSize: 1.2, twinkleAmount: 0.15 };

function sequenceRand(values: number[]): () => number {
  let i = 0;
  return () => values[i++ % values.length];
}

describe("createParticles", () => {
  it("generates exactly `count` particles", () => {
    const particles = createParticles(PARAMS, 800, 600);
    expect(particles).toHaveLength(5);
  });

  it("places every particle inside the field bounds", () => {
    const particles = createParticles(PARAMS, 800, 600);
    for (const p of particles) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThan(800);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThan(600);
    }
  });

  it("sizes far particles (depth near 0) close to half dotSize", () => {
    const rand = sequenceRand([0.5, 0.5, 0]); // x, y, depth=0
    const [p] = createParticles({ ...PARAMS, count: 1 }, 800, 600, rand);
    expect(p.size).toBeCloseTo(PARAMS.dotSize * 0.5, 5);
  });

  it("sizes near particles (depth near 1) close to 1.5x dotSize", () => {
    const rand = sequenceRand([0.5, 0.5, 0.999999]); // x, y, depth~1
    const [p] = createParticles({ ...PARAMS, count: 1 }, 800, 600, rand);
    expect(p.size).toBeCloseTo(PARAMS.dotSize * 1.5, 3);
  });
});

describe("stepParticle", () => {
  const base = {
    x: 400, y: 300, vx: 0, vy: 0, depth: 0.5,
    size: 1.2, wanderAngle: 0, twinklePhase: 0,
  };

  it("advances twinklePhase by a fixed rate regardless of wander randomness", () => {
    const next = stepParticle(base, 0.5, 800, 600, PARAMS, () => 0.5);
    expect(next.twinklePhase).toBeGreaterThan(base.twinklePhase);
    const nextAgain = stepParticle(base, 0.5, 800, 600, PARAMS, () => 0.1);
    expect(nextAgain.twinklePhase).toBeCloseTo(next.twinklePhase, 10);
  });

  it("wraps x back to 0 when it drifts past the right edge", () => {
    const p = { ...base, x: 799.99, vx: 50, vy: 0 };
    const next = stepParticle(p, 1, 800, 600, { ...PARAMS, driftSpeed: 0 }, () => 0.5);
    expect(next.x).toBeGreaterThanOrEqual(0);
    expect(next.x).toBeLessThan(800);
  });

  it("wraps x back near the right edge when it drifts past the left edge", () => {
    const p = { ...base, x: 0.01, vx: -50, vy: 0 };
    const next = stepParticle(p, 1, 800, 600, { ...PARAMS, driftSpeed: 0 }, () => 0.5);
    expect(next.x).toBeGreaterThanOrEqual(0);
    expect(next.x).toBeLessThan(800);
  });

  it("damps velocity toward the wander target instead of snapping to it", () => {
    // rand() always 0.5 keeps wanderAngle fixed at the particle's own angle (0),
    // so the target velocity is (driftSpeed, 0). A tiny dt should nudge vx toward
    // that target without ever reaching it in one step.
    const p = { ...base, wanderAngle: 0, vx: 0, vy: 0 };
    const next = stepParticle(p, 0.01, 800, 600, PARAMS, () => 0.5);
    expect(next.vx).toBeGreaterThan(0);
    expect(next.vx).toBeLessThan(PARAMS.driftSpeed);
  });
});

describe("twinkleAlpha", () => {
  it("returns the base alpha when the twinkle phase is at rest (sin = 0)", () => {
    expect(twinkleAlpha(0.6, 0, 0.15)).toBeCloseTo(0.6, 10);
  });

  it("adds the full twinkle amount at the phase's positive peak", () => {
    expect(twinkleAlpha(0.6, Math.PI / 2, 0.15)).toBeCloseTo(0.75, 10);
  });

  it("clamps above 1", () => {
    expect(twinkleAlpha(0.95, Math.PI / 2, 0.15)).toBeLessThanOrEqual(1);
  });

  it("clamps below 0", () => {
    expect(twinkleAlpha(0.05, -Math.PI / 2, 0.15)).toBeGreaterThanOrEqual(0);
  });
});

describe("connectDots", () => {
  it("links two particles within the link distance", () => {
    const particles = [
      { ...({} as any), x: 0, y: 0 },
      { ...({} as any), x: 10, y: 0 },
    ];
    const links = connectDots(particles as any, 20);
    expect(links).toHaveLength(1);
    expect(links[0]).toMatchObject({ ai: 0, bi: 1 });
  });

  it("does not link particles farther apart than the link distance", () => {
    const particles = [
      { ...({} as any), x: 0, y: 0 },
      { ...({} as any), x: 1000, y: 0 },
    ];
    const links = connectDots(particles as any, 20);
    expect(links).toHaveLength(0);
  });

  it("never duplicates a pair or links a particle to itself", () => {
    const particles = [
      { ...({} as any), x: 0, y: 0 },
      { ...({} as any), x: 5, y: 0 },
      { ...({} as any), x: 10, y: 0 },
    ];
    const links = connectDots(particles as any, 20);
    expect(links).toHaveLength(3); // 0-1, 1-2, 0-2, no self-links, no duplicates
    for (const link of links) {
      expect(link.ai).not.toBe(link.bi);
    }
  });

  it("strength falls off linearly to 0 at the link distance", () => {
    const particles = [
      { ...({} as any), x: 0, y: 0 },
      { ...({} as any), x: 10, y: 0 },
    ];
    const links = connectDots(particles as any, 20);
    expect(links[0].strength).toBeCloseTo(0.5, 5); // 1 - 10/20
  });
});
