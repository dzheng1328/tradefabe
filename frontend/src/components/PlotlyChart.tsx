import Plot from "react-plotly.js";
import type { Data } from "plotly.js";
import { applyDarkTheme } from "../lib/plotlyDarkTheme";

type PlotlyFigure = {
  data: Data[];
  layout: Record<string, unknown>;
};

export default function PlotlyChart({ figure }: { figure: PlotlyFigure | null | undefined }) {
  if (!figure || !figure.data) return null;
  return (
    <Plot
      data={figure.data}
      layout={{ ...applyDarkTheme(figure.layout), autosize: true }}
      style={{ width: "100%", height: "340px" }}
      useResizeHandler
      config={{ displayModeBar: false }}
    />
  );
}
