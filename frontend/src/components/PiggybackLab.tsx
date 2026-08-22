import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { Data } from "plotly.js";
import StatTile from "./StatTile";
import RingLoader from "./RingLoader";
import { fmt } from "../lib/format";
import { fetchJSON } from "../lib/api";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

const DEBOUNCE_MS = 250;
const RECOMMEND_LIMIT = 8;
const SEARCH_RESULTS_LIMIT = 8;

type PiggybackResponse = {
  stats: { sharpe: number | null; sharpe_delta: number | null; calmar: number | null;
           calmar_delta: number | null; maxdd: number | null; maxdd_delta: number | null };
  chart: { data: Data[]; layout: Record<string, unknown> };
};

type RecommendRow = {
  strategy: string; resulting_sharpe: number | null; resulting_calmar: number | null;
  delta_sharpe: number | null;
};

export default function PiggybackLab() {
  const [strategies, setStrategies] = useState<string[] | null>(null);
  const [strategiesError, setStrategiesError] = useState<string | null>(null);
  const [weight, setWeight] = useState(30);
  const [sleeve, setSleeve] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<PiggybackResponse | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendRow[] | null>(null);
  const [recommendError, setRecommendError] = useState<string | null>(null);

  useEffect(() => {
    fetchJSON<{ strategies: string[] }>("http://127.0.0.1:8000/api/research/overview")
      .then((body) => setStrategies(body.strategies))
      .catch(() => setStrategiesError("Couldn't load the strategy list."));
  }, []);

  // Re-simulate the sleeve stats/chart on every add/remove/weight change.
  useEffect(() => {
    if (sleeve.length === 0) { setResult(null); setResultError(null); return; }
    setResultError(null);
    const id = setTimeout(() => {
      fetchJSON<PiggybackResponse>(
        `http://127.0.0.1:8000/api/research/piggyback?sleeve=${sleeve.join(",")}&weight=${weight}`
      )
        .then(setResult)
        .catch(() => { setResult(null); setResultError("Couldn't simulate this sleeve."); });
    }, DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [sleeve, weight]);

  // Recommended-additions list: reflects the FULL current sleeve + each candidate, not
  // the candidate alone -- see research_piggyback_recommend()'s own docstring. Refetches
  // on every add/remove so the list always ranks "what helps THIS sleeve next."
  useEffect(() => {
    setRecommendError(null);
    const id = setTimeout(() => {
      fetchJSON<{ recommendations: RecommendRow[] }>(
        `http://127.0.0.1:8000/api/research/piggyback/recommend?sleeve=${sleeve.join(",")}&weight=${weight}&limit=${RECOMMEND_LIMIT}`
      )
        .then((body) => setRecommendations(body.recommendations))
        .catch(() => { setRecommendations(null); setRecommendError("Couldn't load recommendations."); });
    }, DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [sleeve, weight]);

  const searchMatches = useMemo(() => {
    if (!strategies || !query.trim()) return [];
    const q = query.trim().toLowerCase();
    return strategies
      .filter((s) => !sleeve.includes(s) && s.toLowerCase().includes(q))
      .slice(0, SEARCH_RESULTS_LIMIT);
  }, [strategies, sleeve, query]);

  function addToSleeve(name: string) {
    setSleeve((prev) => (prev.includes(name) ? prev : [...prev, name]));
    setQuery("");
  }

  function removeFromSleeve(name: string) {
    setSleeve((prev) => prev.filter((s) => s !== name));
  }

  if (strategiesError) {
    return <p className="text-ink-muted text-sm">{strategiesError}</p>;
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

        {sleeve.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {sleeve.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => removeFromSleeve(s)}
                className="text-xs font-mono px-2 py-1 rounded-full border border-accent text-accent hover:bg-accent/10"
                title="Remove from sleeve"
              >
                {s} ×
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 relative">
          <label className="text-xs text-ink-muted uppercase font-mono" htmlFor="piggyback-search">
            Add a strategy
          </label>
          <input
            id="piggyback-search"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search strategies…"
            className="w-full mt-2 px-2 py-1.5 text-sm bg-surface border border-white/10 rounded text-ink placeholder:text-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          />
          {searchMatches.length > 0 && (
            <ul className="absolute z-10 w-full mt-1 bg-surface border border-white/10 rounded shadow-lg max-h-56 overflow-y-auto">
              {searchMatches.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => addToSleeve(s)}
                    className="w-full text-left px-2 py-1.5 text-sm text-ink hover:bg-white/5 font-mono"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-6">
          <div className="text-xs text-ink-muted uppercase font-mono mb-2">
            {sleeve.length === 0 ? "Recommended to start with" : "Recommended next"}
          </div>
          {recommendError ? (
            <p className="text-ink-muted text-xs">{recommendError}</p>
          ) : recommendations === null ? (
            <div className="flex justify-center py-4"><RingLoader /></div>
          ) : recommendations.length === 0 ? (
            <p className="text-ink-muted text-xs">Nothing left to recommend.</p>
          ) : (
            <ul className="space-y-1">
              {recommendations.map((r) => (
                <li key={r.strategy}>
                  <button
                    type="button"
                    onClick={() => addToSleeve(r.strategy)}
                    className="w-full flex items-center justify-between gap-2 px-2 py-1.5 text-sm rounded border border-white/5 hover:border-accent/50 hover:bg-white/5 text-left"
                  >
                    <span className="text-ink font-mono truncate min-w-0">{r.strategy}</span>
                    <span className="text-ink-muted font-mono text-xs tabular-nums shrink-0">
                      sharpe {fmt(r.resulting_sharpe)}
                      {r.delta_sharpe != null && (
                        <span className={r.delta_sharpe >= 0 ? "text-accent" : "text-red-400"}>
                          {" "}({r.delta_sharpe >= 0 ? "+" : ""}{fmt(r.delta_sharpe)})
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="flex-1">
        {resultError ? (
          <p className="text-ink-muted text-sm">{resultError}</p>
        ) : result ? (
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
          <p className="text-ink-muted text-sm">
            Search for a strategy or pick one from the recommended list to start a sleeve.
          </p>
        )}
      </div>
    </div>
  );
}
