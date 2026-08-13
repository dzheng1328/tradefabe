// Shared numeric formatting for the detail-panel sections -- mirrors
// tradefabe.dashboard's fmt()/money() exactly (same rounding, same em-dash-for-unknown
// convention) so a value never reads differently between the two stacks.

export function fmt(v: number | null | undefined, kind: "ratio" | "pct" = "ratio"): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return kind === "ratio" ? v.toFixed(2) : `${(v * 100).toFixed(1)}%`;
}

export function money(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}
