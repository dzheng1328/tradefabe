import { lazy, Suspense, useEffect, useState } from "react";
import type { PlotMouseEvent } from "plotly.js";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import GrowthValuesPanel, { type GrowthValueRow } from "./GrowthValuesPanel";
import { fmt } from "../lib/format";
import { fetchJSON } from "../lib/api";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type OverviewResponse = {
  meta: { source: string; start: string; end: string; oos_start: string; n_assets: number };
  stats: {
    n_tested: number; n_alive: number; n_dead: number; luck_floor_p95: number | null;
    best_strategy: string; best_sharpe: number | null; bench_sharpe: number | null;
  };
  strategies: string[];
  growth_chart: { data: unknown[]; layout: Record<string, unknown>; hide_hover_legend?: boolean };
  correlation_heatmap: { data: unknown[]; layout: Record<string, unknown> };
};

export default function ResearchOverview() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clickedDate, setClickedDate] = useState<string | null>(null);
  const [clickedRows, setClickedRows] = useState<GrowthValueRow[] | null>(null);

  useEffect(() => {
    fetchJSON<OverviewResponse>("http://localhost:8000/api/research/overview")
      .then(setData)
      .catch(() => setError("Couldn't load the research overview."));
  }, []);

  // Populates GrowthValuesPanel from the SAME points Plotly's own "x unified" hover
  // would have shown -- clicking anywhere on the chart resolves the nearest x across
  // every trace at once (hovermode="x unified", set server-side in growth_chart()),
  // so `event.points` already has one entry per series without any extra API call.
  function handleGrowthChartClick(event: PlotMouseEvent) {
    if (!event.points.length) return;
    const rows: GrowthValueRow[] = event.points
      .filter((p) => typeof p.y === "number")
      .map((p) => ({
        name: p.data.name ?? "",
        value: p.y as number,
        color: (p.data.line?.color as string) ?? "#9fe870",
      }));
    setClickedDate(String(event.points[0].x));
    setClickedRows(rows);
  }

  if (error) {
    return <p className="text-ink-muted text-sm">{error}</p>;
  }

  if (!data) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-ink-muted font-mono">
        DATA <strong className="text-ink">{data.meta.source}</strong> {data.meta.start} →{" "}
        {data.meta.end} · OOS FROM <strong className="text-ink">{data.meta.oos_start}</strong> ·{" "}
        {data.meta.n_assets} assets
      </p>
      <div className="grid grid-cols-5 gap-4 mt-4">
        <StatTile label="Tested" value={String(data.stats.n_tested)} />
        <StatTile label="Alive" value={String(data.stats.n_alive)} />
        <StatTile label="Dead" value={String(data.stats.n_dead)} />
        <StatTile label="Luck floor p95" value={fmt(data.stats.luck_floor_p95)} />
        <StatTile label={`Best · ${data.stats.best_strategy}`} value={fmt(data.stats.best_sharpe)} />
      </div>
      <p className="text-xs text-ink-muted mt-2 font-mono">
        60/40 benchmark OOS Sharpe: <strong className="text-ink">{fmt(data.stats.bench_sharpe)}</strong>
      </p>
      <div className="mt-6 flex gap-4 items-start">
        <div className="flex-1 min-w-0">
          <Suspense fallback={<div className="h-[340px]" />}>
            <PlotlyChart figure={data.growth_chart} onClick={handleGrowthChartClick} />
          </Suspense>
        </div>
        <GrowthValuesPanel date={clickedDate} rows={clickedRows} />
      </div>
      <div className="mt-6">
        <Suspense fallback={<div className="h-[440px]" />}>
          <PlotlyChart figure={data.correlation_heatmap} />
        </Suspense>
      </div>
    </div>
  );
}
