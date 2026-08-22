// Generates tradefabe's mark: two colliding bristle-brush blooms (crimson bottom-left,
// teal top-right) over a dim gold filament bloom sitting further back in the frame --
// "Twin Corsage" over "Gold Filament Bloom", the pairing Dave picked from the round-2
// concept deck. Petals are individually-drawn bezier bristle strokes (see petal()), not a
// flat gradient, so detail holds up at 1024px.
//
// Two outputs:
//   logo-twin-corsage.svg         rounded (10% inset + squircle clip) -- app-icon source
//   logo-twin-corsage-square.svg  unrounded, no blur filter -- favicon source. Browsers
//                                 rasterize a favicon SVG live and repeatedly; a heavy
//                                 feGaussianBlur over hundreds of overlapping petals was
//                                 what made the old favicon render as a broken image in
//                                 Safari, so the square variant skips the filter entirely.
//
// Run: node ops/assets/generate-logo.mjs

import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const S = 1024;

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hex2rgb(h) {
  h = h.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function rgb2hex(r, g, b) {
  return "#" + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
}
function ramp(stops, t) {
  t = Math.max(0, Math.min(1, t));
  const n = stops.length - 1;
  const f = t * n;
  const i = Math.min(n - 1, Math.floor(f));
  const local = f - i;
  const [r1, g1, b1] = hex2rgb(stops[i]);
  const [r2, g2, b2] = hex2rgb(stops[i + 1]);
  return rgb2hex(r1 + (r2 - r1) * local, g1 + (g2 - g1) * local, b1 + (b2 - b1) * local);
}

const PALETTE = {
  crimson: ["#1c0608", "#5c1016", "#a8241f", "#e8452f", "#f7a94a"],
  teal: ["#04120f", "#0d3d34", "#1c8a72", "#3dd6c0", "#c9fff2"],
  gold: ["#1a1206", "#5c3c0f", "#a8720f", "#e2a03f", "#fff3d0"],
};

function petal(cx, cy, angle, len, width, color, opacity, rnd) {
  const x1 = cx + Math.cos(angle) * len;
  const y1 = cy + Math.sin(angle) * len;
  const perp = angle + Math.PI / 2;
  const wob = (rnd() - 0.5) * len * 0.32;
  const midx = cx + Math.cos(angle) * len * 0.55 + Math.cos(perp) * wob;
  const midy = cy + Math.sin(angle) * len * 0.55 + Math.sin(perp) * wob;
  const w = width * (0.55 + rnd() * 0.85);
  const ax = cx + Math.cos(perp) * w, ay = cy + Math.sin(perp) * w;
  const bx = cx - Math.cos(perp) * w, by = cy - Math.sin(perp) * w;
  return `<path d="M${ax.toFixed(1)},${ay.toFixed(1)} Q${midx.toFixed(1)},${midy.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)} Q${midx.toFixed(1)},${midy.toFixed(1)} ${bx.toFixed(1)},${by.toFixed(1)} Z" fill="${color}" opacity="${opacity.toFixed(2)}"/>`;
}

// A corsage exploding from one focal point: petals fan out radially from (fx, fy),
// colored by their own distance from the focus so the core reads brightest.
function bloomRadial({ fx, fy, radius, count, minLen, maxLen, minW, maxW, palette, seed, minA, maxA, filtered }) {
  const rnd = mulberry32(seed);
  const filterAttr = filtered ? ` filter="url(#brush)"` : "";
  let out = `<g${filterAttr}>`;
  for (let i = 0; i < count; i++) {
    const t = rnd();
    const rr = t * radius;
    const ang = rnd() * Math.PI * 2;
    const cx = fx + Math.cos(ang) * rr * 0.4;
    const cy = fy + Math.sin(ang) * rr * 0.4;
    const dirAngle = ang + (rnd() - 0.5) * 0.9;
    const len = minLen + rnd() * (maxLen - minLen);
    const w = minW + rnd() * (maxW - minW);
    const color = ramp(palette, t + (rnd() - 0.5) * 0.15);
    const op = minA + rnd() * (maxA - minA);
    out += petal(cx, cy, dirAngle, len, w, color, op, rnd);
  }
  out += "</g>";
  return out;
}

// Fine glowing threads radiating from dead center, each occasionally tipped with a
// small particle -- the gold filament bloom sitting behind the twin corsage, at full
// opacity so its threads stay visible where they cross the near-black ground.
function filamentBurst({ cx, cy, minLen, maxLen, count, palette, seed }) {
  const rnd = mulberry32(seed);
  let out = "<g>";
  for (let i = 0; i < count; i++) {
    const a0 = rnd() * Math.PI * 2;
    const len = minLen + rnd() * (maxLen - minLen);
    const x0 = cx, y0 = cy;
    const midx = x0 + Math.cos(a0) * len * 0.5 + (rnd() - 0.5) * S * 0.05;
    const midy = y0 + Math.sin(a0) * len * 0.5 + (rnd() - 0.5) * S * 0.05;
    const x1 = x0 + Math.cos(a0) * len, y1 = y0 + Math.sin(a0) * len;
    const strokeColor = ramp(palette, rnd());
    out += `<path d="M${x0.toFixed(1)},${y0.toFixed(1)} Q${midx.toFixed(1)},${midy.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}" fill="none" stroke="${strokeColor}" stroke-width="${(1.4 + rnd() * 2.4).toFixed(1)}" stroke-linecap="round" opacity="${(0.6 + rnd() * 0.35).toFixed(2)}"/>`;
    if (rnd() > 0.35) {
      out += `<circle cx="${x1.toFixed(1)}" cy="${y1.toFixed(1)}" r="${(3 + rnd() * 7).toFixed(1)}" fill="${ramp(palette, rnd())}" opacity="${(0.75 + rnd() * 0.25).toFixed(2)}"/>`;
    }
  }
  out += "</g>";
  return out;
}

const GOLD_FILAMENT = { cx: S * 0.5, cy: S * 0.5, minLen: S * 0.18, maxLen: S * 0.42, count: 90, palette: PALETTE.gold, seed: 601 };
const GOLD_PETALS = { fx: S * 0.5, fy: S * 0.5, radius: S * 0.4, count: 70, minLen: S * 0.05, maxLen: S * 0.13, minW: S * 0.006, maxW: S * 0.014, palette: PALETTE.gold, minA: 0.55, maxA: 0.95, seed: 602 };
const CRIMSON = { fx: S * 0.3, fy: S * 0.74, radius: S * 0.4, count: 240, minLen: S * 0.045, maxLen: S * 0.15, minW: S * 0.016, maxW: S * 0.046, palette: PALETTE.crimson, minA: 0.62, maxA: 0.97, seed: 88 };
const TEAL = { fx: S * 0.72, fy: S * 0.28, radius: S * 0.38, count: 210, minLen: S * 0.045, maxLen: S * 0.135, minW: S * 0.016, maxW: S * 0.042, palette: PALETTE.teal, minA: 0.62, maxA: 0.97, seed: 89 };

function buildSvg({ rounded }) {
  const RADIUS = S * 0.225;
  const PAD = S * 0.1;
  const clip = rounded
    ? `<clipPath id="tile"><rect x="${PAD}" y="${PAD}" width="${S - PAD * 2}" height="${S - PAD * 2}" rx="${RADIUS}"/></clipPath>`
    : "";
  const clipAttr = rounded ? `clip-path="url(#tile)"` : "";
  const filter = rounded
    ? `<filter id="brush" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="${(S * 0.003).toFixed(2)}"/></filter>`
    : "";
  return `<svg width="${S}" height="${S}" viewBox="0 0 ${S} ${S}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    ${clip}
    ${filter}
  </defs>
  <g ${clipAttr}>
    <rect x="0" y="0" width="${S}" height="${S}" fill="#07090a"/>
    <g>
      ${filamentBurst(GOLD_FILAMENT)}
      ${bloomRadial({ ...GOLD_PETALS, filtered: rounded })}
    </g>
    ${bloomRadial({ ...CRIMSON, filtered: rounded })}
    ${bloomRadial({ ...TEAL, filtered: rounded })}
  </g>
</svg>`;
}

writeFileSync(join(__dirname, "logo-twin-corsage.svg"), buildSvg({ rounded: true }));
writeFileSync(join(__dirname, "logo-twin-corsage-square.svg"), buildSvg({ rounded: false }));
console.log("wrote ops/assets/logo-twin-corsage.svg and logo-twin-corsage-square.svg");
