import { lazy, Suspense, useEffect, useState } from "react";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type StrategyResponse = {
  name: string; blurb: string; verdict: string; freq: string;
  corr_bench: number | null; null_p95: number | null; has_returns: boolean;
  stats: Record<string, number | null>;
  chart: { data: unknown[]; layout: Record<string, unknown> } | null;
};

export default function StrategyDetail({ selected }: { selected: string | null }) {
  const [data, setData] = useState<StrategyResponse | null>(null);

  useEffect(() => {
    if (!selected) { setData(null); return; }
    fetch(`http://localhost:8000/api/research/strategy/${selected}`)
      .then((res) => res.json())
      .then(setData);
  }, [selected]);

  if (!selected) {
    return <p className="text-ink-muted text-sm">Pick a strategy from the Verdicts tab to see its detail.</p>;
  }
  if (!data) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  const statEntries = data.has_returns
    ? (["Sharpe", "Sortino", "Calmar", "MaxDD", "CAGR", "Vol"] as const)
    : (["Sharpe", "Sortino", "Calmar", "MaxDD"] as const);

  return (
    <div>
      <h3 className="text-xl font-bold text-ink">{data.name}</h3>
      <p className="text-ink-muted mt-1 border-l-2 border-accent pl-3">{data.blurb}</p>
      <div className="grid grid-cols-6 gap-4 mt-4">
        {statEntries.map((label) => (
          <StatTile
            key={label}
            label={label === "MaxDD" ? "Max Drawdown" : label === "Vol" ? "Vol (ann.)" : label}
            value={fmt(data.stats[label], label === "MaxDD" || label === "CAGR" || label === "Vol" ? "pct" : "ratio")}
          />
        ))}
      </div>
      <p className="text-xs text-ink-muted mt-2 font-mono">
        Verdict: <span className={data.verdict === "ALIVE" ? "text-accent" : "text-red-400"}>{data.verdict}</span>
        {" · "}corr to 60/40: {fmt(data.corr_bench)} · noise floor: {fmt(data.null_p95)} · rebalance {data.freq}
      </p>
      {data.chart ? (
        <div className="mt-4">
          <Suspense fallback={<div className="h-[280px]" />}>
            <PlotlyChart figure={data.chart} />
          </Suspense>
        </div>
      ) : (
        <p className="text-xs text-ink-muted mt-4">
          Backtest return series isn't stored in the standard format for this strategy -
          showing the summary stats logged at evaluation time instead.
        </p>
      )}
    </div>
  );
}
