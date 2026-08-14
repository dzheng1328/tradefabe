import { lazy, Suspense, useEffect, useState } from "react";
import RingLoader from "./RingLoader";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

type ChartResponse = { chart: { data: unknown[]; layout: Record<string, unknown> } };

export default function Diagnostics({ selected }: { selected: string | null }) {
  const [luckFloor, setLuckFloor] = useState<(ChartResponse & { label: string }) | null>(null);
  const [luckFloorError, setLuckFloorError] = useState<string | null>(null);
  const [drawdownPick, setDrawdownPick] = useState<string | null>(selected);
  const [drawdown, setDrawdown] = useState<(ChartResponse & { max_drawdown: number }) | null>(null);

  useEffect(() => { setDrawdownPick(selected); }, [selected]);

  useEffect(() => {
    if (!selected) { setLuckFloor(null); setLuckFloorError(null); return; }
    setLuckFloorError(null);
    fetch(`http://localhost:8000/api/research/luck_floor?strategy=${selected}`)
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
    if (!drawdownPick) { setDrawdown(null); return; }
    fetch(`http://localhost:8000/api/research/drawdown?pick=${encodeURIComponent(drawdownPick)}`)
      .then((res) => res.json())
      .then(setDrawdown);
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
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={luckFloor.chart} />
        </Suspense>
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
        {drawdown ? (
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
