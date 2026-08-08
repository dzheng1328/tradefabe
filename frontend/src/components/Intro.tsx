import { useEffect, useRef, useState } from "react";
import { playIntroSettle } from "../lib/sound";
import { assembleParticlePosition, sampleTextTargets, type TargetPoint } from "../lib/introTargets";

const STORAGE_KEY = "tradefabe.intro.shown";
const WORDMARK = "tradefabe";
// Phase 0 validated_params (ops/ui_plan_data.json), locked in by Dave's live review.
const TIMING = { assemblyMs: 1200, headlineDelayMs: 1000, holdMs: 1100, settleFadeMs: 600 };
const ACCENT_RGB = "159, 232, 112"; // tailwind.config.js `accent` (#9fe870)

type Phase = "assembling" | "headline" | "settling" | "done";

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

// Renders the wordmark to an offscreen canvas and reads back its alpha channel to
// find target points -- sampled using the canvas's actual INTEGER pixel dims (see
// introTargets.ts) rather than the float CSS width/height, per the Phase 0 spike bug.
function buildTargets(width: number, height: number): TargetPoint[] {
  const w = Math.floor(width);
  const h = Math.floor(height);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return []; // no canvas 2D support -- headline-only fallback, still correct

  // Measure at a base size, then scale to fit within a fraction of the viewport
  // width -- a fixed height-relative size overflows badly on wide/short viewports.
  const baseSize = 200;
  ctx.font = `900 ${baseSize}px 'Space Grotesk', sans-serif`;
  const measuredWidth = ctx.measureText(WORDMARK).width || baseSize;
  const fontSize = Math.floor(baseSize * Math.min(1, (w * 0.6) / measuredWidth));

  ctx.fillStyle = "#fff";
  ctx.font = `900 ${fontSize}px 'Space Grotesk', sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(WORDMARK, w / 2, h / 2);

  const data = ctx.getImageData(0, 0, w, h).data;
  const alphaAt = (x: number, y: number) => data[(y * w + x) * 4 + 3] ?? 0;
  return sampleTextTargets(w, h, 4, alphaAt, 128);
}

function IntroCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;

    const particles = buildTargets(width, height).map((target) => ({
      start: { x: Math.random() * width, y: Math.random() * height },
      target,
    }));

    let frameId: number;
    const startTime = performance.now();
    function draw() {
      const ctx = canvas!.getContext("2d");
      const t = Math.min(1, (performance.now() - startTime) / TIMING.assemblyMs);
      if (ctx) {
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = `rgb(${ACCENT_RGB})`;
        for (const p of particles) {
          const pos = assembleParticlePosition(p.start, p.target, t);
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, 1.4, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }
      if (t < 1) frameId = requestAnimationFrame(draw);
    }
    frameId = requestAnimationFrame(draw);

    return () => cancelAnimationFrame(frameId);
  }, []);

  return <canvas ref={canvasRef} className="intro-canvas" />;
}

// Session-gated intro: the wordmark assembles from drifting particles, a headline
// reveals, holds, then fades into the app underneath. Mounted alongside the real
// route tree (not gating it), so RowList's first fetch runs concurrently under the
// overlay instead of waiting for the intro to finish (idea #4).
export default function Intro() {
  const [phase, setPhase] = useState<Phase>(() => {
    if (typeof window === "undefined") return "done";
    if (sessionStorage.getItem(STORAGE_KEY) === "1") return "done";
    if (prefersReducedMotion()) return "done"; // skip straight to the settled end-state
    return "assembling";
  });

  useEffect(() => {
    if (phase === "done") sessionStorage.setItem(STORAGE_KEY, "1");
  }, [phase]);

  useEffect(() => {
    if (phase !== "assembling") return;
    const toHeadline = setTimeout(() => setPhase("headline"), TIMING.headlineDelayMs);
    const toSettle = setTimeout(
      () => setPhase("settling"),
      TIMING.headlineDelayMs + TIMING.holdMs,
    );
    const toDone = setTimeout(
      () => {
        playIntroSettle();
        setPhase("done");
      },
      TIMING.headlineDelayMs + TIMING.holdMs + TIMING.settleFadeMs,
    );
    return () => {
      clearTimeout(toHeadline);
      clearTimeout(toSettle);
      clearTimeout(toDone);
    };
    // Deliberately mount-once: this schedules the sequence from the phase this
    // component started in, not on every phase change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (phase === "done") return null;

  return (
    <div
      className={`intro-overlay${phase === "settling" ? " intro-overlay--settling" : ""}`}
      aria-hidden="true"
    >
      {/* Runs its own assembly timer independent of the headline reveal -- the
          headline can appear while particles are still mid-flight, but the
          particles themselves always finish resolving into the wordmark rather
          than freezing wherever they happened to be when the headline phase hit. */}
      <IntroCanvas />
      {phase !== "assembling" ? <h1 className="intro-headline">{WORDMARK}</h1> : null}
    </div>
  );
}
