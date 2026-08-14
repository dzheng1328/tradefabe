import { fmt, money } from "../lib/format";

type Position = {
  ticker: string; units: number | null; last_price: number | null;
  value: number | null; weight: number | null;
};

export default function PositionsTable({
  positions, positionsAsof,
}: {
  positions: Position[] | null;
  positionsAsof: string | null;
}) {
  if (!positions || positions.length === 0) {
    return <p className="text-ink-muted text-sm">No open positions (book hasn't rebalanced yet).</p>;
  }
  return (
    <div>
      <table className="w-full text-sm font-mono tabular-nums">
        <thead>
          <tr className="text-ink-muted text-xs uppercase text-left">
            <th className="pb-2 font-sans">Ticker</th>
            <th className="pb-2 text-right">Units</th>
            <th className="pb-2 text-right">Last price</th>
            <th className="pb-2 text-right">Value</th>
            <th className="pb-2 text-right">Weight</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.ticker} className="border-t border-white/5">
              <td className="py-1.5 font-sans">{p.ticker}</td>
              <td className="py-1.5 text-right">{p.units?.toFixed(2) ?? "—"}</td>
              <td className="py-1.5 text-right">{p.last_price !== null ? money(p.last_price) : "—"}</td>
              <td className="py-1.5 text-right">{money(p.value)}</td>
              <td className="py-1.5 text-right">{fmt(p.weight, "pct")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-muted mt-2">
        Priced as of the cached data date ({positionsAsof ?? "unknown"}), not a live
        quote. Weight is % of TOTAL equity (cash + positions), not % of invested value
        — it no longer always sums to 100%.
      </p>
    </div>
  );
}
