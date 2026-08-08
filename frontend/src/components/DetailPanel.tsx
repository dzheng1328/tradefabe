import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { Data } from "plotly.js";
import RangeControl from "./RangeControl";
import { SPRING } from "../lib/motion";
import { playDataLanded } from "../lib/sound";

// plotly.js alone is ~1.5MB gzipped -- lazy-loading keeps it out of the initial
// bundle (RowList/Nav/routing shell) and fetches it only once a book is actually
// opened, which is also the earliest point a real figure exists to render.
const PlotlyChart = lazy(() => import("./PlotlyChart"));

type DetailResponse = {
  name: string;
  kind: "equity" | "carry";
  blurb: string;
  retirement_note: { at: string; reason: string } | null;
  stats: Record<"Sharpe" | "Sortino" | "Calmar" | "MaxDD" | "CAGR" | "Vol", number | null>;
  live_start: string;
  bt_start: string | null;
  available_windows: string[];
  live_equity_chart: { data: Data[]; layout: Record<string, unknown> };
  backtest_chart: { data: Data[]; layout: Record<string, unknown> };
  divergence_state: "insufficient" | "ok" | "diverging";
  divergence_detail: string;
  verdict?: string;
  corr_bench?: number | null;
  null_p95?: number | null;
  freq?: string;
  carry_meta?: Record<string, number | null>;
};

function fmt(v: number | null | undefined, kind: "ratio" | "pct" = "ratio") {
  if (v === null || v === undefined) return "—";
  return kind === "ratio" ? v.toFixed(2) : `${(v * 100).toFixed(1)}%`;
}

export default function DetailPanel({ name }: { name: string }) {
  const [data, setData] = useState<DetailResponse | null>(null);
  const [window, setWindow] = useState("ALL");
  // True from a name change until that book's first response lands -- distinguishes
  // "just opened this book" (plays the landed sound) from "changed the range window on
  // a book already open" (RangeControl's own click sound already covers that feedback;
  // playing both would double up).
  const isInitialLoad = useRef(true);

  useEffect(() => {
    setData(null);
    setWindow("ALL");
    isInitialLoad.current = true;
  }, [name]);

  useEffect(() => {
    fetch(`http://localhost:8000/api/books/${name}/detail?window=${window}`)
      .then((res) => res.json())
      .then((body: DetailResponse) => {
        setData(body);
        if (isInitialLoad.current) {
          playDataLanded();
          isInitialLoad.current = false;
        }
      });
  }, [name, window]);

  if (!data) return <p className="text-ink-muted">Loading…</p>;

  const statEntries: [string, number | null][] = [
    ["Sharpe", data.stats.Sharpe], ["Sortino", data.stats.Sortino],
    ["Calmar", data.stats.Calmar], ["Max Drawdown", data.stats.MaxDD],
    ["CAGR", data.stats.CAGR], ["Vol (ann.)", data.stats.Vol],
  ];

  return (
    <motion.div key={name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}>
      <h2 className="text-2xl font-bold text-ink">{name}</h2>
      <p className="text-ink-muted mt-1">{data.blurb}</p>

      {data.retirement_note && (
        <div className="bg-surface rounded-card p-4 mt-4 text-sm">
          Retired {data.retirement_note.at} — {data.retirement_note.reason}
        </div>
      )}

      <div className="grid grid-cols-6 gap-4 mt-6 pb-6 border-b border-white/5">
        {statEntries.map(([label, kind]) => (
          <div key={label}>
            <div className="text-xs text-ink-muted uppercase">{label}</div>
            <div className="text-xl text-ink font-mono tabular-nums">
              {fmt(kind, label === "Max Drawdown" || label === "CAGR" || label === "Vol (ann.)" ? "pct" : "ratio")}
            </div>
          </div>
        ))}
      </div>

      {data.kind === "equity" ? (
        <p className="text-xs text-ink-muted mt-2 font-mono">
          Verdict: {data.verdict} · corr to 60/40: {fmt(data.corr_bench)} · noise floor:{" "}
          {fmt(data.null_p95)} · rebalance {data.freq}
        </p>
      ) : (
        <p className="text-xs text-ink-muted mt-2 font-mono">
          Net yield: {fmt(data.carry_meta?.net_yield, "pct")} · % days positive:{" "}
          {fmt(data.carry_meta?.pct_days_positive, "pct")}
        </p>
      )}

      <div className="mt-6 pt-6 border-t border-white/5">
        <div className="flex items-center justify-between">
          <span className="text-sm text-ink">Live paper equity</span>
          <RangeControl options={data.available_windows} value={window} onChange={setWindow} />
        </div>
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={data.live_equity_chart} />
        </Suspense>
      </div>

      <details className="mt-6 pt-6 border-t border-white/5">
        <summary className="text-sm text-ink cursor-pointer">
          Backtest history & live tracking check
        </summary>
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={data.backtest_chart} />
        </Suspense>
        <p className="text-xs text-ink-muted mt-2">
          {data.divergence_state}: {data.divergence_detail}
        </p>
      </details>
    </motion.div>
  );
}
