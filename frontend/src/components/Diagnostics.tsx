import { lazy, Suspense, useEffect, useState } from "react";
import type { Data } from "plotly.js";
import RingLoader from "./RingLoader";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type ChartResponse = { chart: { data: Data[]; layout: Record<string, unknown> } };
type LuckFloorShape = "per_strategy" | "per_frequency";

export default function Diagnostics({ selected }: { selected: string | null }) {
  const [luckFloor, setLuckFloor] = useState<
    (ChartResponse & { label: string; shape: LuckFloorShape }) | null
  >(null);
  const [luckFloorError, setLuckFloorError] = useState<string | null>(null);
  const [drawdownPick, setDrawdownPick] = useState<string | null>(selected);
  const [drawdown, setDrawdown] = useState<(ChartResponse & { max_drawdown: number }) | null>(null);
  const [drawdownError, setDrawdownError] = useState<string | null>(null);

  useEffect(() => { setDrawdownPick(selected); setDrawdownError(null); }, [selected]);

  useEffect(() => {
    if (!selected) { setLuckFloor(null); setLuckFloorError(null); return; }
    setLuckFloorError(null);
    fetch(`http://127.0.0.1:8000/api/research/luck_floor?strategy=${selected}`)
      .then((res) => {
        if (!res.ok) {
          setLuckFloor(null);
          setLuckFloorError("No luck-floor distribution available for this strategy.");
          return null;
        }
        return res.json();
      })
      .then((data) => { if (data) setLuckFloor(data); });
  }, [selected]);

  useEffect(() => {
    if (!drawdownPick) { setDrawdown(null); setDrawdownError(null); return; }
    setDrawdownError(null);
    fetch(`http://127.0.0.1:8000/api/research/drawdown?pick=${encodeURIComponent(drawdownPick)}`)
      .then((res) => {
        if (!res.ok) {
          setDrawdown(null);
          setDrawdownError("No backtest curve available for this pick.");
          return null;
        }
        return res.json();
      })
      .then((data) => { if (data) setDrawdown(data); });
  }, [drawdownPick]);

  if (!selected) {
    return <p className="text-ink-muted text-sm">Pick a strategy from the Verdicts tab to see its diagnostics.</p>;
  }

  return (
    <div>
      <h4 className="text-sm text-ink">{luckFloor?.label ?? "Luck floor"}</h4>
      {luckFloorError ? (
        <p className="text-ink-muted text-sm py-12">{luckFloorError}</p>
      ) : luckFloor ? (
        <>
          <p className="text-xs text-ink-muted mt-1">
            {luckFloor.shape === "per_strategy"
              ? "Scored against random rotations of this strategy's own signal (DOCTRINE v1.5)."
              : `Shared distribution across all ${luckFloor.label.toLowerCase()} strategies - not specific to this one.`}
          </p>
          <Suspense fallback={<div className="h-[340px]" />}>
            <PlotlyChart figure={luckFloor.chart} />
          </Suspense>
        </>
      ) : (
        <div className="flex justify-center py-12"><RingLoader /></div>
      )}

      <div className="mt-6 pt-6 border-t border-white/5">
        <div className="flex items-center justify-between">
          <h4 className="text-sm text-ink">Underwater - drawdown from peak</h4>
          <select
            value={drawdownPick ?? ""}
            onChange={(e) => setDrawdownPick(e.target.value)}
            className="bg-surface border border-white/10 rounded px-2 py-1 text-xs text-ink font-mono"
          >
            <option value={selected}>{selected}</option>
            <option value="60/40">60/40</option>
            <option value="SPY">SPY</option>
          </select>
        </div>
        {drawdownError ? (
          <p className="text-ink-muted text-sm py-12">{drawdownError}</p>
        ) : drawdown ? (
          <>
            <Suspense fallback={<div className="h-[280px]" />}>
              <PlotlyChart figure={drawdown.chart} />
            </Suspense>
            <p className="text-xs text-ink-muted mt-2">
              Max drawdown: <strong className="text-ink">{(drawdown.max_drawdown * 100).toFixed(1)}%</strong>
            </p>
          </>
        ) : (
          <div className="flex justify-center py-12"><RingLoader /></div>
        )}
      </div>
    </div>
  );
}
