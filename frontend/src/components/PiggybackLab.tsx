import { lazy, Suspense, useEffect, useState } from "react";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

const DEFAULT_SLEEVE = ["xsec_momentum", "tsmom_12m"];
const DEBOUNCE_MS = 250;

type PiggybackResponse = {
  stats: { sharpe: number | null; sharpe_delta: number | null; calmar: number | null;
           calmar_delta: number | null; maxdd: number | null; maxdd_delta: number | null };
  chart: { data: unknown[]; layout: Record<string, unknown> };
};

export default function PiggybackLab() {
  const [strategies, setStrategies] = useState<string[] | null>(null);
  const [weight, setWeight] = useState(30);
  const [sleeve, setSleeve] = useState<string[]>([]);
  const [result, setResult] = useState<PiggybackResponse | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/research/overview")
      .then((res) => res.json())
      .then((body: { strategies: string[] }) => {
        setStrategies(body.strategies);
        setSleeve(DEFAULT_SLEEVE.filter((s) => body.strategies.includes(s)));
      });
  }, []);

  useEffect(() => {
    if (sleeve.length === 0) { setResult(null); return; }
    const id = setTimeout(() => {
      fetch(`http://localhost:8000/api/research/piggyback?sleeve=${sleeve.join(",")}&weight=${weight}`)
        .then((res) => res.json())
        .then(setResult);
    }, DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [sleeve, weight]);

  function toggle(name: string) {
    setSleeve((prev) => (prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]));
  }

  if (!strategies) {
    return <div className="flex justify-center py-12"><RingLoader /></div>;
  }

  return (
    <div className="flex gap-6">
      <div className="w-1/3 shrink-0">
        <label className="text-xs text-ink-muted uppercase font-mono">Sleeve weight ({weight}%)</label>
        <input
          type="range" min={0} max={50} step={5} value={weight}
          onChange={(e) => setWeight(Number(e.target.value))}
          className="w-full accent-accent mt-2"
        />
        <div className="mt-4 space-y-1">
          <div className="text-xs text-ink-muted uppercase font-mono">Sleeve strategies</div>
          {strategies.map((s) => (
            <label key={s} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                aria-label={s}
                checked={sleeve.includes(s)}
                onChange={() => toggle(s)}
                className="accent-accent"
              />
              {s}
            </label>
          ))}
        </div>
      </div>
      <div className="flex-1">
        {result ? (
          <>
            <div className="grid grid-cols-3 gap-4">
              <StatTile label="Sharpe" value={`${fmt(result.stats.sharpe)} (${fmt(result.stats.sharpe_delta)} vs 60/40)`} />
              <StatTile label="Calmar" value={`${fmt(result.stats.calmar)} (${fmt(result.stats.calmar_delta)} vs 60/40)`} />
              <StatTile label="Max drawdown" value={`${fmt(result.stats.maxdd, "pct")} (${fmt(result.stats.maxdd_delta, "pct")} vs 60/40)`} />
            </div>
            <div className="mt-4">
              <Suspense fallback={<div className="h-[340px]" />}>
                <PlotlyChart figure={result.chart} />
              </Suspense>
            </div>
            <p className="text-xs text-ink-muted mt-2">
              Reminder: a sleeve usually LOWERS raw dollars while smoothing the ride — Sharpe up ≠ more profit.
            </p>
          </>
        ) : (
          <p className="text-ink-muted text-sm">Pick at least one sleeve strategy.</p>
        )}
      </div>
    </div>
  );
}
