// Same green family as `accent`, just pushed deep and muted -- idea #37 (lean into
// the one accent color in more shades, rather than reaching for a new hue) and idea
// #38 (the topo texture below) both draw from this one token.
const ACCENT_DIM = "#2b3e1e";

// Two clusters of elevation-contour rings, each ring's center drifting slightly from
// the last (real contour lines aren't perfectly concentric) so it reads as topography
// rather than a grid of targets. Every ring stays comfortably inside the 160x160 tile
// with margin to spare -- no shape crosses an edge, so the tile repeats with no visible
// seam. Kept to a handful of <ellipse> elements: a static background-image, not a
// runtime cost.
const TOPO_TILE = `
  <svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>
    <g fill='none' stroke='${ACCENT_DIM}' stroke-width='1' stroke-opacity='0.4'>
      <g transform='translate(48 56) rotate(-12)'>
        <ellipse cx='0' cy='0' rx='16' ry='13' />
        <ellipse cx='3' cy='-2' rx='27' ry='22' />
        <ellipse cx='-2' cy='4' rx='38' ry='31' />
      </g>
      <g transform='translate(114 108) rotate(18)'>
        <ellipse cx='0' cy='0' rx='13' ry='11' />
        <ellipse cx='-2' cy='3' rx='22' ry='18' />
        <ellipse cx='3' cy='-3' rx='30' ry='25' />
      </g>
    </g>
  </svg>
`.trim().replace(/\s+/g, " ");

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d0f0c",
        surface: "#181c15",
        accent: "#9fe870",
        "accent-dim": ACCENT_DIM,
        ink: "#f2f5ef",
        "ink-muted": "#7d8877",
      },
      borderRadius: {
        card: "26px",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        none: "none",
      },
      backgroundImage: {
        // Organic topographic-contour texture for card surfaces (idea #38) --
        // pair with `bg-surface bg-repeat`, never used alone.
        topo: `url("data:image/svg+xml,${encodeURIComponent(TOPO_TILE)}")`,
      },
    },
  },
  plugins: [],
};
