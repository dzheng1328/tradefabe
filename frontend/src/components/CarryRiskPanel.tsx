import { pct } from "../lib/format";

type Posture = { leverage: number; liq_distance: number };
type CoinRisk = {
  funding_7d: number | null; funding_flip_alert: boolean;
  max_leverage: number | null; maint_margin: number | null;
  postures: Record<string, Posture>;
};
type CarryRisk = {
  generated_at: string; funding_window_days: number;
  coins: { BTC: CoinRisk; ETH: CoinRisk };
  blended_funding_7d: number | null; blended_funding_flip_alert: boolean;
  headline_leverage_fraction: number; liq_distance_warn: number;
  high_risk_alert: { BTC: boolean; ETH: boolean };
};

const TIERS = ["10%", "25%", "50%", "100%"];

// app.py formats funding_7d as f"{f7:+.2%}" -- 2 decimals, explicit sign. This is a
// different precision from lib/format.ts's pct() (1 decimal), so it's formatted locally
// rather than forced through the shared helper.
function fundingPct(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

export default function CarryRiskPanel({ risk }: { risk: CarryRisk | null }) {
  if (!risk) {
    return (
      <p className="text-ink-muted text-sm">
        No risk report yet — generated automatically by `tradefabe run`.
      </p>
    );
  }
  const flagged = (["BTC", "ETH"] as const).filter((c) => risk.high_risk_alert[c]);
  const hasPostures =
    Object.keys(risk.coins.BTC.postures).length > 0 ||
    Object.keys(risk.coins.ETH.postures).length > 0;
  return (
    <div>
      <p className="text-xs text-ink-muted font-mono">
        As of {risk.generated_at} · trailing {risk.funding_window_days}d funding
      </p>
      <div className="grid grid-cols-2 gap-4 mt-2">
        {(["BTC", "ETH"] as const).map((coin) => (
          <div key={coin}>
            <div className="text-xs text-ink-muted uppercase">{coin} 7d funding</div>
            <div className="text-xl text-ink font-mono tabular-nums">
              {fundingPct(risk.coins[coin].funding_7d)}
            </div>
            {risk.coins[coin].funding_flip_alert && (
              <span className="text-xs text-amber-400 font-mono">funding flip</span>
            )}
          </div>
        ))}
      </div>
      {risk.blended_funding_flip_alert && (
        <p className="text-sm text-amber-400 mt-3">
          Blended 7d funding has turned negative — bear-regime bleed. The book loses
          money net of the fee drag until this flips back.
        </p>
      )}
      {hasPostures ? (
        <>
          <table className="w-full text-sm font-mono tabular-nums mt-4">
            <thead>
              <tr className="text-ink-muted text-xs uppercase text-left">
                <th className="pb-2 font-sans">Posture</th>
                <th className="pb-2 text-right">BTC leverage</th>
                <th className="pb-2 text-right">BTC liq distance</th>
                <th className="pb-2 text-right">ETH leverage</th>
                <th className="pb-2 text-right">ETH liq distance</th>
              </tr>
            </thead>
            <tbody>
              {TIERS.map((tier) => {
                const btc = risk.coins.BTC.postures[tier];
                const eth = risk.coins.ETH.postures[tier];
                return (
                  <tr key={tier} className="border-t border-white/5">
                    <td className="py-1.5 font-sans">{tier}</td>
                    <td className="py-1.5 text-right">{btc ? `${btc.leverage.toFixed(1)}x` : "—"}</td>
                    <td className="py-1.5 text-right">{btc ? pct(btc.liq_distance) : "—"}</td>
                    <td className="py-1.5 text-right">{eth ? `${eth.leverage.toFixed(1)}x` : "—"}</td>
                    <td className="py-1.5 text-right">{eth ? pct(eth.liq_distance) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {flagged.length > 0 && (
            <p className="text-sm text-red-400 mt-3">
              High risk: at {(risk.headline_leverage_fraction * 100).toFixed(0)}% of
              Hyperliquid's live max leverage, <strong>{flagged.join(", ")}</strong>{" "}
              liquidation distance is under the{" "}
              {(risk.liq_distance_warn * 100).toFixed(0)}% pump-cushion threshold.
            </p>
          )}
        </>
      ) : (
        <p className="text-ink-muted text-sm mt-4">
          Leverage tiers unavailable this run (Hyperliquid unreachable) — funding alert
          above still reflects the last successful fetch.
        </p>
      )}
      <p className="text-xs text-ink-muted mt-3">
        Postures are % of Hyperliquid's live max leverage per coin, not what this
        paper book actually holds — the book models pure funding yield with no
        leverage. This is a what-if overlay: if an operator ran the short leg at that
        leverage, how far could price pump before liquidation.
      </p>
    </div>
  );
}
