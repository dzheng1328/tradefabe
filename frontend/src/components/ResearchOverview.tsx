import { lazy, Suspense, useEffect, useState } from "react";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type OverviewResponse = {
  meta: { source: string; start: string; end: string; oos_start: string; n_assets: number };
  stats: {
    n_tested: number; n_alive: number; n_dead: number; luck_floor_p95: number | null;
    best_strategy: string; best_sharpe: number | null; bench_sharpe: number | null;
  };
  strategies: string[];
  growth_chart: { data: unknown[]; layout: Record<string, unknown> };
  correlation_heatmap: { data: unknown[]; layout: Record<string, unknown> };
};

export default function ResearchOverview() {
  const [data, setData] = useState<OverviewResponse | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/research/overview")
      .then((res) => res.json())
      .then(setData);
  }, []);

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
      <div className="mt-6">
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={data.growth_chart} />
        </Suspense>
      </div>
      <div className="mt-6">
        <Suspense fallback={<div className="h-[440px]" />}>
          <PlotlyChart figure={data.correlation_heatmap} />
        </Suspense>
      </div>
    </div>
  );
}
