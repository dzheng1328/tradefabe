import { useEffect, useRef } from "react";
import { connectDots, createParticles, stepParticle, twinkleAlpha, type Particle } from "../lib/particles";
import { prefersReducedMotion } from "../lib/motion";

// Phase 0's validated_params (ops/ui_plan_data.json) read as too static and too bright
// once seen live behind real row-list content -- links spanned huge sparse triangles
// that fought the white/grey dollar figures for contrast, and the drift was almost
// imperceptible. Retuned after a live review: faster drift, smaller dots, a shorter
// link distance (finer, denser network instead of a few giant triangles), and lower
// alpha throughout so it reads as ambient texture, not a competing foreground layer.
const PARAMS = { count: 390, driftSpeed: 0.48, dotSize: 0.85, twinkleAmount: 0.1 };
const LINK_DISTANCE = 85;
const ACCENT_RGB = "159, 232, 112"; // tailwind.config.js `accent` (#9fe870) as an rgb triplet

// One glow sprite, rasterized once and reused via drawImage for every particle on
// every frame -- calling ctx.createRadialGradient() per particle per frame (390
// particles x 60fps) forced the browser to rebuild and rasterize a fresh gradient
// continuously on a full-viewport canvas, a real perf smell (fixing-motion-performance
// skill, rule 5: paint-heavy work must stay small/isolated, not run unbounded on a
// large surface). Baked at full brightness/size; per-particle alpha and size are
// applied at draw time via globalAlpha + dest width/height, so one sprite covers every
// depth/twinkle combination.
const SPRITE_SIZE = 64;
let glowSprite: HTMLCanvasElement | null = null;
function getGlowSprite(): HTMLCanvasElement {
  if (glowSprite) return glowSprite;
  const sprite = document.createElement("canvas");
  sprite.width = SPRITE_SIZE;
  sprite.height = SPRITE_SIZE;
  const sctx = sprite.getContext("2d")!;
  const r = SPRITE_SIZE / 2;
  const gradient = sctx.createRadialGradient(r, r, 0, r, r, r);
  gradient.addColorStop(0, `rgba(${ACCENT_RGB}, 1)`);
  gradient.addColorStop(1, `rgba(${ACCENT_RGB}, 0)`);
  sctx.fillStyle = gradient;
  sctx.fillRect(0, 0, SPRITE_SIZE, SPRITE_SIZE);
  glowSprite = sprite;
  return sprite;
}

function renderFrame(
  ctx: CanvasRenderingContext2D,
  particles: Particle[],
  width: number,
  height: number,
  dpr: number,
) {
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  ctx.globalCompositeOperation = "lighter";
  ctx.lineWidth = 1;
  ctx.strokeStyle = `rgba(${ACCENT_RGB}, 1)`;
  for (const link of connectDots(particles, LINK_DISTANCE)) {
    const a = particles[link.ai];
    const b = particles[link.bi];
    ctx.globalAlpha = link.strength * 0.1;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  const sprite = getGlowSprite();
  for (const p of particles) {
    const alpha = twinkleAlpha(0.28, p.twinklePhase, PARAMS.twinkleAmount);
    const glowRadius = p.size * 2.2;
    const d = glowRadius * 2;
    ctx.globalAlpha = alpha;
    ctx.drawImage(sprite, p.x - glowRadius, p.y - glowRadius, d, d);
  }
  ctx.globalAlpha = 1;

  ctx.globalCompositeOperation = "source-over";
  ctx.restore();
}

// Ambient generative background, replacing the old flat .grain-overlay. Fixed,
// pointer-events: none, and drawn on a canvas so redraws never touch layout --
// see index.css's .particle-field rule.
export default function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = window.innerWidth;
    let height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;

    let particles = createParticles(PARAMS, width, height);

    function draw() {
      const ctx = canvas!.getContext("2d");
      if (ctx) renderFrame(ctx, particles, width, height, dpr);
    }

    function handleResize() {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas!.width = width * dpr;
      canvas!.height = height * dpr;
      draw();
    }
    window.addEventListener("resize", handleResize);

    if (prefersReducedMotion()) {
      draw();
      return () => window.removeEventListener("resize", handleResize);
    }

    let frameId: number;
    let last = performance.now();
    function loop(now: number) {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      particles = particles.map((p) => stepParticle(p, dt, width, height, PARAMS));
      draw();
      frameId = requestAnimationFrame(loop);
    }
    frameId = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return <canvas ref={canvasRef} className="particle-field" aria-hidden="true" />;
}
