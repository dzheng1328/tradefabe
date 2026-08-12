import { describe, expect, it } from "vitest";
import { createRingDots, ringTarget, springStep } from "./ringLoader";

describe("ringLoader math", () => {
  it("creates the requested number of dots, all starting collapsed at the origin", () => {
    const dots = createRingDots(8);
    expect(dots).toHaveLength(8);
    expect(dots.every((d) => d.x === 0 && d.y === 0 && d.vx === 0 && d.vy === 0)).toBe(true);
  });

  it("places a ring target at the given radius when wave depth is zero", () => {
    const t = ringTarget(0, 4, 76, 0, 0);
    expect(Math.hypot(t.x, t.y)).toBeCloseTo(76, 5);
  });

  it("distributes dots evenly around the circle", () => {
    const a = ringTarget(0, 4, 100, 0, 0);
    const b = ringTarget(1, 4, 100, 0, 0);
    // Quarter-turn apart -> perpendicular vectors, dot product ~0.
    expect(a.x * b.x + a.y * b.y).toBeCloseTo(0, 5);
  });

  it("springs a dot closer to its target with each step", () => {
    let dot = { x: 0, y: 0, vx: 0, vy: 0 };
    const target = { x: 50, y: 0 };
    const distBefore = Math.hypot(target.x - dot.x, target.y - dot.y);
    dot = springStep(dot, target, 1 / 60);
    const distAfter = Math.hypot(target.x - dot.x, target.y - dot.y);
    expect(distAfter).toBeLessThan(distBefore);
  });

  it("converges near a fixed target after enough steps", () => {
    let dot = { x: -30, y: 20, vx: 0, vy: 0 };
    const target = { x: 40, y: -10 };
    for (let i = 0; i < 300; i++) dot = springStep(dot, target, 1 / 60);
    expect(Math.hypot(target.x - dot.x, target.y - dot.y)).toBeLessThan(0.5);
  });
});
