import { describe, expect, it } from "vitest";
import { curl, makeNoise2D, mulberry32, stepStrandPhysics, type StrandParams, type StrandVector } from "./introBloom";

describe("mulberry32", () => {
  it("is deterministic for a given seed", () => {
    const a = mulberry32(42);
    const b = mulberry32(42);
    const seqA = Array.from({ length: 5 }, () => a());
    const seqB = Array.from({ length: 5 }, () => b());
    expect(seqA).toEqual(seqB);
  });

  it("produces values in [0, 1)", () => {
    const rng = mulberry32(7);
    for (let i = 0; i < 50; i++) {
      const v = rng();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });
});

describe("makeNoise2D", () => {
  it("is deterministic for a given seed", () => {
    const n1 = makeNoise2D(99);
    const n2 = makeNoise2D(99);
    expect(n1(1.23, 4.56)).toBe(n2(1.23, 4.56));
  });

  it("differs across seeds (not a constant field)", () => {
    const n1 = makeNoise2D(1);
    const n2 = makeNoise2D(2);
    expect(n1(3.1, 2.7)).not.toBe(n2(3.1, 2.7));
  });

  it("stays within Perlin's expected [-1, 1] range", () => {
    const noise = makeNoise2D(5);
    for (let x = 0; x < 20; x += 0.7) {
      for (let y = 0; y < 20; y += 0.7) {
        const v = noise(x, y);
        expect(v).toBeGreaterThanOrEqual(-1.01);
        expect(v).toBeLessThanOrEqual(1.01);
      }
    }
  });
});

describe("curl", () => {
  it("is deterministic and finite", () => {
    const noise = makeNoise2D(3);
    const [cx, cy] = curl(noise, 0.4, 0.6, 0, 0.9);
    expect(Number.isFinite(cx)).toBe(true);
    expect(Number.isFinite(cy)).toBe(true);
    const [cx2, cy2] = curl(noise, 0.4, 0.6, 0, 0.9);
    expect(cx2).toBe(cx);
    expect(cy2).toBe(cy);
  });
});

describe("stepStrandPhysics", () => {
  const noise = makeNoise2D(11);
  const center = { x: 0, y: 0 };
  const baseParams: StrandParams = {
    seedAngle: 0,
    reach: 200,
    speed: 100,
    noiseOffset: 0,
    noiseScale: 0.006,
  };

  it("pushes a fresh strand away from center along its seed angle", () => {
    const state: StrandVector = { x: 0, y: 0, vx: 0, vy: 0 };
    const next = stepStrandPhysics(state, baseParams, noise, center, 0, 0, 1000 / 60);
    // seedAngle=0 means the initial erupt force points along +x
    expect(next.x).toBeGreaterThan(0);
  });

  it("is deterministic given identical inputs", () => {
    const state: StrandVector = { x: 12, y: -5, vx: 3, vy: 1 };
    const a = stepStrandPhysics(state, baseParams, noise, center, 500, 200, 16);
    const b = stepStrandPhysics(state, baseParams, noise, center, 500, 200, 16);
    expect(a).toEqual(b);
  });

  it("decelerates the outward push once a strand nears its reach", () => {
    const near: StrandVector = { x: 195, y: 0, vx: 0, vy: 0 };
    const far: StrandVector = { x: 0, y: 0, vx: 0, vy: 0 };
    const nearStep = stepStrandPhysics(near, baseParams, noise, center, 100, 50, 16);
    const farStep = stepStrandPhysics(far, baseParams, noise, center, 100, 50, 16);
    const nearSpeed = Math.hypot(nearStep.vx, nearStep.vy);
    const farSpeed = Math.hypot(farStep.vx, farStep.vy);
    expect(nearSpeed).toBeLessThan(farSpeed);
  });

  it("decays the outward push as the strand ages past ~900ms", () => {
    const state: StrandVector = { x: 0, y: 0, vx: 0, vy: 0 };
    const young = stepStrandPhysics(state, baseParams, noise, center, 100, 50, 16);
    const old = stepStrandPhysics(state, baseParams, noise, center, 2000, 1950, 16);
    const youngSpeed = Math.hypot(young.vx, young.vy);
    const oldSpeed = Math.hypot(old.vx, old.vy);
    expect(oldSpeed).toBeLessThan(youngSpeed);
  });
});
