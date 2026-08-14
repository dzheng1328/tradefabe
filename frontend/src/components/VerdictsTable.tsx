import { useEffect, useState } from "react";
import { fmt, dateTime } from "../lib/format";
import { fetchJSON } from "../lib/api";
import RingLoader from "./RingLoader";

type VerdictRow = {
  strategy: string; freq: string; tested: string; oos_sharpe: number | null;
  oos_sortino: number | null; oos_calmar: number | null; oos_maxdd: number | null;
  corr_bench: number | null; null_p95: number | null; verdict: string;
};

const COLUMNS: { key: keyof VerdictRow; label: string }[] = [
  { key: "strategy", label: "Strategy" }, { key: "freq", label: "Freq" },
  { key: "tested", label: "Tested" },
  { key: "oos_sharpe", label: "Sharpe" }, { key: "oos_sortino", label: "Sortino" },
  { key: "oos_calmar", label: "Calmar" }, { key: "oos_maxdd", label: "MaxDD" },
  { key: "corr_bench", label: "Corr" }, { key: "null_p95", label: "Null p95" },
  { key: "verdict", label: "Verdict" },
];

export default function VerdictsTable({ onSelect }: { onSelect: (name: string) => void }) {
  const [rows, setRows] = useState<VerdictRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<keyof VerdictRow>("tested");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  useEffect(() => {
    fetchJSON<{ rows: VerdictRow[] }>("http://localhost:8000/api/research/verdicts")
      .then((body) => setRows(body.rows))
      .catch(() => setError("Couldn't load the verdicts table."));
  }, []);

  if (error) {
    return <p className="text-ink-muted text-sm">{error}</p>;
  }

  if (!rows) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av === null) return 1;
    if (bv === null) return -1;
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });

  function toggleSort(key: keyof VerdictRow) {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(1); }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead className="text-ink-muted uppercase">
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} className="text-left py-1 cursor-pointer select-none" onClick={() => toggleSort(c.key)}>
                {c.label}{sortKey === c.key ? (sortDir === 1 ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.strategy}
              className="border-t border-white/5 hover:bg-white/5 cursor-pointer"
              onClick={() => onSelect(r.strategy)}
            >
              <td className="py-1 text-ink">{r.strategy}</td>
              <td className="text-ink-muted">{r.freq}</td>
              <td className="text-ink-muted tabular-nums">{dateTime(r.tested)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_sharpe)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_sortino)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_calmar)}</td>
              <td className="text-ink tabular-nums">{fmt(r.oos_maxdd, "pct")}</td>
              <td className="text-ink tabular-nums">{fmt(r.corr_bench)}</td>
              <td className="text-ink tabular-nums">{fmt(r.null_p95)}</td>
              <td className={r.verdict === "ALIVE" ? "text-accent" : "text-red-400"}>{r.verdict}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
