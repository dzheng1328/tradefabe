import StatTile from "./StatTile";
import { fmt, money } from "../lib/format";

type Deployment = {
  cash: number | null; gross: number | null; net: number | null; equity: number | null;
  cash_pct: number | null; gross_pct: number | null; net_pct: number | null;
  n_unpriced: number; n_held: number; priced_at: string | null; is_short_funded: boolean;
};

export default function DeploymentStats({ deployment }: { deployment: Deployment }) {
  const d = deployment;
  return (
    <div>
      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Cash (undeployed)" value={`${money(d.cash)} · ${fmt(d.cash_pct, "pct")}`} />
        <StatTile label="Gross exposure" value={`${money(d.gross)} · ${fmt(d.gross_pct, "pct")}`} />
        <StatTile label="Net exposure" value={`${money(d.net)} · ${fmt(d.net_pct, "pct")}`} />
        <StatTile label="Total equity" value={money(d.equity)} />
      </div>
      {d.n_unpriced > 0 && (
        <p className="text-xs text-amber-400 mt-2">
          {d.n_unpriced} of {d.n_held} held position(s) could not be priced, so the
          figures above are incomplete. This is shown rather than silently summed to
          $0 - an unpriceable book is not an empty one.
        </p>
      )}
      <p className="text-xs text-ink-muted mt-2">
        Gross = sum of |position value| (both legs of a long/short book); net = long
        minus short (directional tilt).{" "}
        {d.is_short_funded ? (
          <>
            <strong className="text-ink">Cash exceeds equity because this book is net
            short</strong> — the short proceeds are cash. Nothing is borrowed and
            nothing is wrong.
          </>
        ) : (
          "Vol-targeted sizing deliberately leaves room in cash rather than forcing " +
          "100% deployment — that's a feature of the sizing, not a bug."
        )}
        {d.priced_at && ` Priced from the ledger's own marks as of ${d.priced_at} UTC.`}
      </p>
    </div>
  );
}
