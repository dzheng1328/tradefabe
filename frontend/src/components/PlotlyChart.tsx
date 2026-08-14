import Plot from "react-plotly.js";
import type { Data } from "plotly.js";
import { applyDarkTheme } from "../lib/plotlyDarkTheme";

type PlotlyFigure = {
  data: Data[];
  layout: Record<string, unknown>;
};

export default function PlotlyChart({ figure }: { figure: PlotlyFigure | null | undefined }) {
  if (!figure || !figure.data) return null;
  // The figure's own `layout.height` (dashboard.py scales this per chart -- e.g. taller
  // for a bigger correlation heatmap) used to be overridden by a hardcoded 340px here,
  // squeezing anything taller than that into a cramped, illegible box. Fall back to
  // 340 only when the layout doesn't specify one.
  const height = typeof figure.layout.height === "number" ? figure.layout.height : 340;
  return (
    <Plot
      data={figure.data}
      layout={{ ...applyDarkTheme(figure.layout), autosize: true }}
      style={{ width: "100%", height: `${height}px` }}
      useResizeHandler
      config={{ displayModeBar: false }}
    />
  );
}
