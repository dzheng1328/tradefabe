import { useMemo, useState } from "react";
import { useScrollSound } from "../lib/useScrollSound";

export type GrowthValueRow = { name: string; value: number; color: string };

const PANEL_HEIGHT = 340;   // matches growth_chart()'s own height so the two sit flush

// Docked alongside the overview growth chart, populated by clicking a point on the
// chart (see ResearchOverview.tsx's onClick handler) instead of Plotly's own "x
// unified" hover box -- that box is a floating overlay clipped to the chart's own SVG
// bounds, which a 22-row list can never reliably fit inside regardless of font size or
// value precision (2026-08-14). A normal, fixed-height, scrollable DOM panel has no
// such ceiling: it just gets a scrollbar instead of clipping.
export default function GrowthValuesPanel({
  date, rows,
}: {
  date: string | null;
  rows: GrowthValueRow[] | null;
}) {
  const [query, setQuery] = useState("");
  const scrollRef = useScrollSound<HTMLDivElement>();

  const filtered = useMemo(() => {
    if (!rows) return [];
    const sorted = [...rows].sort((a, b) => b.value - a.value);
    const q = query.trim().toLowerCase();
    return q ? sorted.filter((r) => r.name.toLowerCase().includes(q)) : sorted;
  }, [rows, query]);

  return (
    <div
      className="w-72 shrink-0 flex flex-col rounded border border-white/5 bg-surface/60"
      style={{ height: PANEL_HEIGHT }}
    >
      <div className="px-3 pt-2 pb-1.5 border-b border-white/5 shrink-0">
        <div className="text-xs text-ink-muted uppercase font-mono">
          {date ? `Values at ${date}` : "Values"}
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search…"
          disabled={!rows}
          className="w-full mt-1.5 px-2 py-1 text-xs bg-transparent border border-white/10 rounded text-ink placeholder:text-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:opacity-40"
        />
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-1 py-1">
        {!rows ? (
          <p className="text-ink-muted text-xs px-2 py-3">
            Click a point on the chart to see every strategy's value there.
          </p>
        ) : filtered.length === 0 ? (
          <p className="text-ink-muted text-xs px-2 py-3">No match.</p>
        ) : (
          filtered.map((r) => (
            <div
              key={r.name}
              className="flex items-center gap-2 px-2 py-1 text-xs font-mono rounded hover:bg-white/5"
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: r.color }}
              />
              <span className="text-ink-muted truncate min-w-0 flex-1">{r.name}</span>
              <span className="text-ink tabular-nums shrink-0">{r.value.toFixed(3)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
