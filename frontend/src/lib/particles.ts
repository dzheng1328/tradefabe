// Pure particle-field math, kept free of canvas/DOM so it's directly unit-testable.
// Techniques carried forward from the Phase 0 spike (ops/ui_plan_data.json phase 0
// validated_params): per-particle wander force + drag instead of constant-velocity
// linear drift, depth-based parallax, and a spatial-grid constellation network.

export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  depth: number; // 0 (far) .. 1 (near) -- drives both size and drift speed parallax
  size: number;
  wanderAngle: number;
  twinklePhase: number;
}

export interface ParticleFieldParams {
  count: number;
  driftSpeed: number;
  dotSize: number;
  twinkleAmount: number;
}

export interface DotLink {
  ai: number;
  bi: number;
  strength: number;
}

// Higher = velocity snaps toward the wander target faster; lower = more elastic lag.
const DRAG = 1.4;
// Max random turn rate applied to the wander angle, radians/sec.
const WANDER_TURN_RATE = 2.4;
// How fast the twinkle phase advances, radians/sec.
const TWINKLE_FREQ = 1.6;

export function createParticles(
  params: ParticleFieldParams,
  width: number,
  height: number,
  rand: () => number = Math.random,
): Particle[] {
  const particles: Particle[] = [];
  for (let i = 0; i < params.count; i++) {
    const x = rand() * width;
    const y = rand() * height;
    const depth = rand();
    particles.push({
      x,
      y,
      vx: 0,
      vy: 0,
      depth,
      size: params.dotSize * (0.5 + depth),
      wanderAngle: rand() * Math.PI * 2,
      twinklePhase: rand() * Math.PI * 2,
    });
  }
  return particles;
}

export function stepParticle(
  p: Particle,
  dt: number,
  width: number,
  height: number,
  params: ParticleFieldParams,
  rand: () => number = Math.random,
): Particle {
  const wanderAngle = p.wanderAngle + (rand() - 0.5) * WANDER_TURN_RATE * dt;
  const speed = params.driftSpeed * (0.4 + 0.6 * p.depth); // near particles drift faster
  const targetVx = Math.cos(wanderAngle) * speed;
  const targetVy = Math.sin(wanderAngle) * speed;

  // Velocity eases toward the wander target rather than snapping to it -- same
  // damped-approach shape as the ring loader's spring-toward-target technique.
  const dragF = Math.min(1, DRAG * dt);
  const vx = p.vx + (targetVx - p.vx) * dragF;
  const vy = p.vy + (targetVy - p.vy) * dragF;

  let x = p.x + vx * dt;
  let y = p.y + vy * dt;
  if (x < 0) x += width;
  else if (x >= width) x -= width;
  if (y < 0) y += height;
  else if (y >= height) y -= height;

  return {
    ...p,
    x,
    y,
    vx,
    vy,
    wanderAngle,
    twinklePhase: p.twinklePhase + dt * TWINKLE_FREQ,
  };
}

export function twinkleAlpha(baseAlpha: number, twinklePhase: number, twinkleAmount: number): number {
  const alpha = baseAlpha + twinkleAmount * Math.sin(twinklePhase);
  return Math.min(1, Math.max(0, alpha));
}

// O(n) connected-dot constellation via a uniform spatial grid sized to the link
// distance, so only the 3x3 neighborhood of cells needs checking per particle.
export function connectDots(particles: Particle[], linkDistance: number): DotLink[] {
  const cell = linkDistance;
  const grid = new Map<string, number[]>();
  const cellOf = (v: number) => Math.floor(v / cell);
  const key = (cx: number, cy: number) => `${cx},${cy}`;

  particles.forEach((p, i) => {
    const k = key(cellOf(p.x), cellOf(p.y));
    const bucket = grid.get(k);
    if (bucket) bucket.push(i);
    else grid.set(k, [i]);
  });

  const links: DotLink[] = [];
  particles.forEach((p, i) => {
    const cx = cellOf(p.x);
    const cy = cellOf(p.y);
    for (let oy = -1; oy <= 1; oy++) {
      for (let ox = -1; ox <= 1; ox++) {
        const bucket = grid.get(key(cx + ox, cy + oy));
        if (!bucket) continue;
        for (const j of bucket) {
          if (j <= i) continue; // skip self and already-visited pairs
          const other = particles[j];
          const d = Math.hypot(p.x - other.x, p.y - other.y);
          if (d < linkDistance) {
            links.push({ ai: i, bi: j, strength: 1 - d / linkDistance });
          }
        }
      }
    }
  });
  return links;
}
