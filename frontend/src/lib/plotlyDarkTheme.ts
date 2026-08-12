// Overrides the color-bearing keys of a Plotly layout fetched from the API. The
// backend's dashboard.themed_layout() bakes in the OLD Streamlit theme's light colors
// (paper_bgcolor #fcfcfb) -- it can't be changed there because app.py still renders
// these same charts live with that theme. Confirmed working via a pre-plan spike:
// react-plotly.js renders correctly against the dark canvas once these keys are
// overridden client-side. Only color-bearing keys are touched; trace-level `data`
// (line/fill colors) already come from the API's per-book SLOTS palette and are
// left untouched.
const SURFACE = "#181c15";
const INK_MUTED = "#7d8877";
const GRID = "#2a2f24";
const ACCENT = "#9fe870";
const MONO_FONT = "IBM Plex Mono, monospace";

export function applyDarkTheme(
  layout: Record<string, unknown>
): Record<string, unknown> {
  const font = (layout.font as Record<string, unknown>) ?? {};
  const xaxis = (layout.xaxis as Record<string, unknown>) ?? {};
  const yaxis = (layout.yaxis as Record<string, unknown>) ?? {};
  return {
    ...layout,
    paper_bgcolor: SURFACE,
    plot_bgcolor: SURFACE,
    font: { ...font, color: INK_MUTED },
    xaxis: { ...xaxis, gridcolor: GRID, linecolor: GRID },
    yaxis: { ...yaxis, gridcolor: GRID, linecolor: GRID },
    // Idea #45: the hover tooltip/crosshair gets the same mono font + accent
    // color as the rest of the shell, instead of Plotly's default light tooltip.
    hoverlabel: {
      bgcolor: SURFACE,
      bordercolor: ACCENT,
      font: { family: MONO_FONT, color: ACCENT, size: 11 },
    },
  };
}
