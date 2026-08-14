import { money } from "../lib/format";

type Trade = {
  ts: string | null; ticker: string | null; side: string | null;
  shares: number | null; price: number | null; notional: number | null;
  position_after: number | null;
};

export default function TradeLog({
  trades, accrualOnly, costBps,
}: {
  trades: Trade[];
  accrualOnly: boolean;
  costBps: number | null;
}) {
  if (accrualOnly) {
    return (
      <p className="text-ink-muted text-sm">
        This book is delta-neutral carry: its value moves from funding accrual, not
        discrete trades, so no fill log ever applies here — not an empty log waiting
        to fill, a different economics entirely.
      </p>
    );
  }
  if (trades.length === 0) {
    return (
      <p className="text-ink-muted text-sm">
        No fills recorded yet. The log starts at this book's next rebalance — earlier
        trades happened before the ledger recorded them and cannot be reconstructed,
        since only the resulting position was kept.
      </p>
    );
  }
  const lastTs = trades[0]?.ts;
  return (
    <div>
      <table className="w-full text-sm font-mono tabular-nums">
        <thead>
          <tr className="text-ink-muted text-xs uppercase text-left">
            <th className="pb-2">When (UTC)</th>
            <th className="pb-2 font-sans">Ticker</th>
            <th className="pb-2 font-sans">Side</th>
            <th className="pb-2 text-right">Δ units</th>
            <th className="pb-2 text-right">Fill price</th>
            <th className="pb-2 text-right">Notional</th>
            <th className="pb-2 text-right">Position after</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-t border-white/5">
              <td className="py-1.5">{t.ts ? t.ts.replace("T", " ").slice(0, 16) : "—"}</td>
              <td className="py-1.5 font-sans">{t.ticker ?? "—"}</td>
              <td className="py-1.5 font-sans">{t.side ?? "—"}</td>
              <td className="py-1.5 text-right">
                {t.shares !== null ? `${t.shares >= 0 ? "+" : ""}${t.shares.toFixed(2)}` : "—"}
              </td>
              <td className="py-1.5 text-right">{t.price !== null ? money(t.price) : "—"}</td>
              <td className="py-1.5 text-right">{money(t.notional)}</td>
              <td className="py-1.5 text-right">{t.position_after?.toFixed(2) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-muted mt-2">
        {trades.length} fill(s), newest first; last {lastTs ? lastTs.replace("T", " ").slice(0, 16) : "—"} UTC.
        Sides are named from the POSITION's view, not the order's: BUY/SELL open or
        grow a long, SHORT/COVER open or reduce a short. Simulated fills at the mark
        close with a {costBps !== null ? costBps.toFixed(0) : "—"}bp per-side cost,
        capped at the most recent 500 — these ledgers are committed to git every cycle, so
        the log is bounded on purpose.
      </p>
    </div>
  );
}
