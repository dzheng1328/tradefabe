import { useRef, useState } from "react";
import Plot from "react-plotly.js";
import type { Data, PlotHoverEvent, PlotMouseEvent } from "plotly.js";
import { applyDarkTheme } from "../lib/plotlyDarkTheme";

type PlotlyFigure = {
  data: Data[];
  layout: Record<string, unknown>;
  // Sibling of data/layout, NOT read by react-plotly.js's <Plot> (it only destructures
  // data/layout/config/frames below), so Plotly.js can never see or mutate it -- unlike
  // an earlier approach of sniffing layout.hoverlabel.bgcolor for a sentinel color,
  // which broke the moment Plotly's own color-normalization pass rewrote
  // "rgba(0,0,0,0)" to "rgba(0, 0, 0, 0)" (spaces added) IN PLACE on the shared layout
  // object during its first redraw, flipping a strict-equality check to false
  // (confirmed live, 2026-08-14 -- see dashboard.py's research_overview()).
  hide_hover_legend?: boolean;
};

export default function PlotlyChart({
  figure, onClick,
}: {
  figure: PlotlyFigure | null | undefined;
  onClick?: (event: PlotMouseEvent) => void;
}) {
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [hoverPx, setHoverPx] = useState<number | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  if (!figure || !figure.data) return null;
  // The figure's own `layout.height` (dashboard.py scales this per chart -- e.g. taller
  // for a bigger correlation heatmap) used to be overridden by a hardcoded 340px here,
  // squeezing anything taller than that into a cramped, illegible box. Fall back to
  // 340 only when the layout doesn't specify one.
  const height = typeof figure.layout.height === "number" ? figure.layout.height : 340;
  // CSS rule in index.css (.tf-hide-hover-legend) removes Plotly's per-trace
  // color-swatch <path>s inside .hoverlayer's .legend group on the overview growth
  // chart -- those swatches aren't controlled by hoverlabel styling at all, so a
  // transparent hoverlabel alone left a column of opaque colored dashes on hover with
  // no text (confirmed live). The class lives on a plain wrapper <div> that REACT
  // alone owns, never touched by Plotly's internal DOM management of the graph div one
  // level down, so it survives every redraw Plotly.react() triggers.
  //
  // With the whole hover box hidden, the date it used to show up top vanished along
  // with it -- readable only by cross-referencing the x axis by eye. Re-add just the
  // date, in a plain DOM label positioned above the crosshair (the "spikeline" the CSS
  // comment above already leaves alone), driven off onHover/onUnhover rather than any
  // Plotly-rendered element so it can't be swept up by the same swatch/legend hiding.
  const showsHoverDate = figure.hide_hover_legend === true;

  return (
    <div
      ref={wrapperRef}
      className={figure.hide_hover_legend ? "tf-hide-hover-legend relative" : "relative"}
    >
      {showsHoverDate && hoverDate !== null && hoverPx !== null && (
        <div
          className="absolute top-0 z-10 -translate-x-1/2 px-1.5 py-0.5 text-[11px] font-mono text-accent bg-surface/90 border border-accent/40 rounded pointer-events-none"
          style={{ left: hoverPx }}
        >
          {hoverDate}
        </div>
      )}
      <Plot
        data={figure.data}
        layout={{ ...applyDarkTheme(figure.layout), autosize: true }}
        style={{ width: "100%", height: `${height}px` }}
        useResizeHandler
        config={{ displayModeBar: false }}
        onClick={onClick}
        onHover={
          showsHoverDate
            ? (event: PlotHoverEvent) => {
                if (!event.points.length || !wrapperRef.current) return;
                const rect = wrapperRef.current.getBoundingClientRect();
                setHoverDate(String(event.points[0].x));
                setHoverPx(event.event.clientX - rect.left);
              }
            : undefined
        }
        onUnhover={
          showsHoverDate
            ? () => {
                setHoverDate(null);
                setHoverPx(null);
              }
            : undefined
        }
      />
    </div>
  );
}
