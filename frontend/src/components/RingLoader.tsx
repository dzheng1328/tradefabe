import { useEffect, useRef } from "react";
import { createRingDots, ringTarget, springStep } from "../lib/ringLoader";
import { prefersReducedMotion } from "../lib/motion";

// Phase 0's validated_params (ops/ui_plan_data.json phases[0]) for the ring loader.
const DOT_COUNT = 64;
const RADIUS = 76;
const LOOP_DURATION_MS = 2700;
const WAVE_DEPTH = 9;
const ACCENT_RGB = "159, 232, 112";
const SIZE = (RADIUS + WAVE_DEPTH) * 2 + 16;

function renderFrame(
  ctx: CanvasRenderingContext2D,
  dots: { x: number; y: number }[],
  size: number,
  dpr: number,
) {
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, size, size);
  ctx.translate(size / 2, size / 2);

  // Neighboring dots connected into a glowing outline (Phase 0's carried-forward
  // technique), plus the two diameters of the brand glyph's crossed-circle motif.
  ctx.globalCompositeOperation = "lighter";
  ctx.strokeStyle = `rgba(${ACCENT_RGB}, 0.5)`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  dots.forEach((d, i) => {
    if (i === 0) ctx.moveTo(d.x, d.y);
    else ctx.lineTo(d.x, d.y);
  });
  ctx.closePath();
  ctx.stroke();

  ctx.fillStyle = `rgba(${ACCENT_RGB}, 0.9)`;
  for (const d of dots) {
    ctx.beginPath();
    ctx.arc(d.x, d.y, 2, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.globalCompositeOperation = "source-over";
  ctx.restore();
}

// Idea #20: the loading state, built from Phase 0's ring-loader spike and reusing
// BrandGlyph's crossed-circle motif (idea #41) so loading feels like the same visual
// language as the rest of the shell, not a borrowed spinner.
export default function RingLoader() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;

    const dots = createRingDots(DOT_COUNT);
    const targets = dots.map((_, i) => ringTarget(i, DOT_COUNT, RADIUS, 0, WAVE_DEPTH));

    function draw(frameDots: { x: number; y: number }[]) {
      const ctx = canvas!.getContext("2d");
      if (ctx) renderFrame(ctx, frameDots, SIZE, dpr);
    }

    if (prefersReducedMotion()) {
      // Settled ring, no rotation -- a frozen frame, not a degraded experience.
      draw(targets);
      return;
    }

    let frameId: number;
    let last = performance.now();
    let rotation = 0;
    let live = dots;
    function loop(now: number) {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      rotation += (Math.PI * 2 * dt * 1000) / LOOP_DURATION_MS;
      live = live.map((d, i) =>
        springStep(d, ringTarget(i, DOT_COUNT, RADIUS, rotation, WAVE_DEPTH), dt)
      );
      draw(live);
      frameId = requestAnimationFrame(loop);
    }
    frameId = requestAnimationFrame(loop);

    return () => cancelAnimationFrame(frameId);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="ring-loader"
      style={{ width: SIZE, height: SIZE }}
      role="status"
      aria-label="Loading"
    />
  );
}
