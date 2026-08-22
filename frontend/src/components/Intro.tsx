import { useEffect, useRef, useState } from "react";
import introBloomImg from "../assets/intro-bloom.jpg";
import { playIntroSettle } from "../lib/sound";
import { prefersReducedMotion } from "../lib/motion";
import { makeNoise2D, mulberry32, stepStrandPhysics, type StrandVector } from "../lib/introBloom";

const STORAGE_KEY = "tradefabe.intro.shown";
const ACCENT_RGB = "159, 232, 112"; // tailwind.config.js `accent` (#9fe870)
const SEED = 1234;
const NOISE_SCALE = 0.0062;
const N_PETALS = 8;
const N_STRANDS = 340;

// Phase 0's validated_params (particle-assembled wordmark + separate headline) is
// retired: the headline duplicated the particle-assembled word in the same spot
// (the "big white overlap" bug) and thousands of per-frame arc()/fill() calls tanked
// FPS. Redesigned per Dave's review of DataLand-reel-inspired concepts (2026-08):
// boot log + fixed HUD chrome play the whole time, and the same curl-noise strand
// field that used to assemble a wordmark now masks in the real reference photo --
// one canvas, no duplicate text layer, far fewer/larger accumulated paint dabs
// instead of a fresh full-canvas particle redraw every frame.
const TIMING = {
  bootCharMs: 34,
  hudFadeMs: 500,
  bloomStartMs: 950,
  bloomGrowMs: 1500,
  holdMs: 1100,
  fadeMs: 650,
};
const BLOOM_END_MS = TIMING.bloomStartMs + TIMING.bloomGrowMs;
const HOLD_UNTIL_MS = BLOOM_END_MS + TIMING.holdMs;
const TOTAL_MS = HOLD_UNTIL_MS + TIMING.fadeMs;

const BOOT_LINES = [
  "> tradefabe://boot",
  "> loading doctrine v1.6 ...",
  "> assembling signal ...",
  "> ready.",
];

interface Strand extends StrandVector {
  seedAngle: number;
  reach: number;
  speed: number;
  noiseOffset: number;
  spawnMs: number;
  trail: { x: number; y: number }[];
  maxTrail: number;
  width: number;
  started: boolean;
}

function makeStrands(): Strand[] {
  const rng = mulberry32(SEED + 1);
  const strands: Strand[] = [];
  for (let i = 0; i < N_STRANDS; i++) {
    const petal = i % N_PETALS;
    const baseAngle = (petal / N_PETALS) * Math.PI * 2;
    strands.push({
      x: 0, y: 0, vx: 0, vy: 0,
      seedAngle: baseAngle + (rng() - 0.5) * 0.85,
      reach: 90 + rng() * 260,
      speed: 90 + rng() * 150,
      noiseOffset: rng() * 1000,
      spawnMs: TIMING.bloomStartMs + (i / N_STRANDS) * (TIMING.bloomGrowMs * 0.55),
      trail: [],
      maxTrail: 10 + Math.floor(rng() * 14),
      width: 1.0 + rng() * 2.2,
      started: false,
    });
  }
  return strands;
}

// Renders the boot log + fixed HUD chrome + curl-noise petal-mask reveal of the
// reference bloom image onto one canvas. Runs its own rAF loop independent of the
// outer phase state machine, and honors reduced motion by never mounting at all
// (see Intro below).
function IntroCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;

    // Persistent paint layer: strand dabs/strokes ACCUMULATE here across frames
    // (never cleared until the sequence resets) rather than being redrawn fresh
    // each frame -- this is what turns sparse per-frame arcs into a dense, filled
    // bloom shape instead of a firework-spark look.
    const paintCanvas = document.createElement("canvas");
    paintCanvas.width = width * dpr;
    paintCanvas.height = height * dpr;
    const paintCtx = paintCanvas.getContext("2d");
    if (!paintCtx) return;
    paintCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const compositeCanvas = document.createElement("canvas");
    compositeCanvas.width = width * dpr;
    compositeCanvas.height = height * dpr;
    const compositeCtx = compositeCanvas.getContext("2d");
    if (!compositeCtx) return;
    compositeCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const noise2D = makeNoise2D(SEED);
    const strands = makeStrands();
    const cx = width / 2;
    const cy = height / 2;

    let bloomImgReady = false;
    const bloomImg = new Image();
    bloomImg.onload = () => { bloomImgReady = true; };
    bloomImg.src = introBloomImg;

    function stepStrand(s: Strand, dt: number, elapsed: number) {
      if (elapsed < s.spawnMs) return;
      if (!s.started) {
        s.started = true;
        s.x = cx + Math.cos(s.seedAngle) * 4;
        s.y = cy + Math.sin(s.seedAngle) * 4;
        s.trail = [{ x: s.x, y: s.y }];
      }
      const age = elapsed - s.spawnMs;
      const next = stepStrandPhysics(
        s,
        { seedAngle: s.seedAngle, reach: s.reach, speed: s.speed, noiseOffset: s.noiseOffset, noiseScale: NOISE_SCALE },
        noise2D,
        { x: cx, y: cy },
        elapsed,
        age,
        dt,
      );
      s.x = next.x; s.y = next.y; s.vx = next.vx; s.vy = next.vy;
      s.trail.push({ x: s.x, y: s.y });
      if (s.trail.length > s.maxTrail) s.trail.shift();
    }

    // Paints the strand's newest segment as a WHITE ALPHA MASK, not a synthetic
    // color -- the mask later reveals the real reference photo, so the bloom's
    // texture is the actual picture rather than a hand-approximated palette.
    function paintStrand(s: Strand, elapsed: number) {
      if (!s.started || s.trail.length < 2) return;
      const age = elapsed - s.spawnMs;
      const introAlpha = Math.min(1, age / 300);
      if (introAlpha <= 0.02) return;
      const p0 = s.trail[s.trail.length - 2];
      const p1 = s.trail[s.trail.length - 1];

      const dabR = s.width * 3.4;
      const grad = paintCtx!.createRadialGradient(p1.x, p1.y, 0, p1.x, p1.y, dabR);
      grad.addColorStop(0, `rgba(255,255,255,${(introAlpha * 0.09).toFixed(3)})`);
      grad.addColorStop(1, "rgba(255,255,255,0)");
      paintCtx!.fillStyle = grad;
      paintCtx!.beginPath();
      paintCtx!.arc(p1.x, p1.y, dabR, 0, Math.PI * 2);
      paintCtx!.fill();

      paintCtx!.strokeStyle = `rgba(255,255,255,${(introAlpha * 0.5).toFixed(3)})`;
      paintCtx!.lineWidth = s.width * 0.6;
      paintCtx!.beginPath();
      paintCtx!.moveTo(p0.x, p0.y);
      paintCtx!.lineTo(p1.x, p1.y);
      paintCtx!.stroke();
    }

    function drawBoot(elapsed: number) {
      const charsShown = Math.floor(elapsed / TIMING.bootCharMs);
      if (charsShown <= 0) return;
      ctx!.font = "12px 'SF Mono', 'JetBrains Mono', monospace";
      ctx!.textBaseline = "top";
      let shown = charsShown;
      let y = 28;
      for (const line of BOOT_LINES) {
        if (shown <= 0) break;
        const n = Math.min(line.length, shown);
        ctx!.fillStyle = `rgba(${ACCENT_RGB},0.85)`;
        ctx!.fillText(line.slice(0, n), 24, y);
        shown -= line.length + 6;
        y += 17;
      }
    }

    function drawCorner(x: number, y: number, sx: number, sy: number, len: number) {
      ctx!.beginPath();
      ctx!.moveTo(x, y + len * sy);
      ctx!.lineTo(x, y);
      ctx!.lineTo(x + len * sx, y);
      ctx!.stroke();
    }

    function drawHud(elapsed: number) {
      const a = Math.min(1, elapsed / TIMING.hudFadeMs);
      if (a <= 0) return;
      ctx!.save();
      ctx!.globalAlpha = a * 0.8;
      ctx!.strokeStyle = `rgba(${ACCENT_RGB},0.55)`;
      ctx!.lineWidth = 1;
      const m = 24, len = 22;
      drawCorner(m, m, 1, 1, len);
      drawCorner(width - m, m, -1, 1, len);
      drawCorner(m, height - m, 1, -1, len);
      drawCorner(width - m, height - m, -1, -1, len);

      ctx!.font = "10px 'SF Mono', 'JetBrains Mono', monospace";
      ctx!.textBaseline = "middle";
      const bx = m, by = height - m - 70;
      ctx!.strokeStyle = `rgba(${ACCENT_RGB},0.35)`;
      ctx!.strokeRect(bx, by, 176, 58);
      const stats: [string, string][] = [
        ["DOCTRINE", "v1.6"],
        ["MODE", "PAPER ONLY"],
        ["GATE", "DSR ≥ 0"],
      ];
      let sy = by + 12;
      for (const [k, v] of stats) {
        ctx!.fillStyle = `rgba(${ACCENT_RGB},0.7)`;
        ctx!.fillText(k, bx + 10, sy);
        ctx!.fillStyle = "rgba(242,245,239,0.75)";
        ctx!.fillText(v, bx + 88, sy);
        sy += 16;
      }
      ctx!.restore();
    }

    // Cover-fits the reference photo into a same-size canvas, then punches it
    // through the accumulated curl-noise alpha mask so only the grown petal
    // shape reveals the photo.
    function compositeBloom() {
      compositeCtx!.clearRect(0, 0, width, height);
      if (bloomImgReady) {
        const scale = Math.max(width / bloomImg.width, height / bloomImg.height) * 1.5;
        const iw = bloomImg.width * scale;
        const ih = bloomImg.height * scale;
        compositeCtx!.drawImage(bloomImg, (width - iw) / 2, (height - ih) / 2, iw, ih);
      }
      compositeCtx!.globalCompositeOperation = "destination-in";
      compositeCtx!.drawImage(paintCanvas, 0, 0, width, height);
      compositeCtx!.globalCompositeOperation = "source-over";
    }

    let frameId: number;
    let prev = performance.now();
    const startTime = prev;

    function loop(now: number) {
      const dt = Math.min(now - prev, 1000 / 30);
      prev = now;
      const elapsed = now - startTime;

      paintCtx!.globalCompositeOperation = "lighter";
      for (const s of strands) {
        stepStrand(s, dt, elapsed);
        paintStrand(s, elapsed);
      }
      paintCtx!.globalCompositeOperation = "source-over";

      const growAlpha = elapsed < TIMING.bloomStartMs
        ? 0
        : elapsed < BLOOM_END_MS
          ? Math.min(1, (elapsed - TIMING.bloomStartMs) / (TIMING.bloomGrowMs * 0.7))
          : 1;

      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx!.clearRect(0, 0, width, height);
      compositeBloom();
      ctx!.globalAlpha = growAlpha;
      ctx!.drawImage(compositeCanvas, 0, 0, width, height);
      ctx!.globalAlpha = 1;

      drawBoot(elapsed);
      drawHud(elapsed);

      if (elapsed < TOTAL_MS + 200) {
        frameId = requestAnimationFrame(loop);
      }
    }
    frameId = requestAnimationFrame(loop);

    return () => cancelAnimationFrame(frameId);
  }, []);

  return <canvas ref={canvasRef} className="intro-canvas" />;
}

// Session-gated intro: boot log + HUD chrome play throughout while a curl-noise
// strand field masks in the real reference photo at center, then holds and fades
// into the app underneath. Mounted alongside the real route tree (not gating it),
// so RowList's first fetch runs concurrently under the overlay instead of waiting
// for the intro to finish (idea #4).
type Phase = "playing" | "settling" | "done";

export default function Intro() {
  const [phase, setPhase] = useState<Phase>(() => {
    if (typeof window === "undefined") return "done";
    if (sessionStorage.getItem(STORAGE_KEY) === "1") return "done";
    if (prefersReducedMotion()) return "done"; // skip straight to the settled end-state
    return "playing";
  });

  useEffect(() => {
    if (phase === "done") sessionStorage.setItem(STORAGE_KEY, "1");
  }, [phase]);

  useEffect(() => {
    if (phase !== "playing") return;
    const toSettle = setTimeout(() => setPhase("settling"), HOLD_UNTIL_MS);
    const toDone = setTimeout(() => {
      playIntroSettle();
      setPhase("done");
    }, TOTAL_MS);
    return () => {
      clearTimeout(toSettle);
      clearTimeout(toDone);
    };
    // Deliberately mount-once: schedules from the state this component started
    // in, not on every re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (phase === "done") return null;

  return (
    <div
      className={`intro-overlay${phase === "settling" ? " intro-overlay--settling" : ""}`}
      aria-hidden="true"
    >
      <IntroCanvas />
    </div>
  );
}
