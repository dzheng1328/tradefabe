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

// ISO timestamp -> "MM-DD HH:MM", local time. Used where a table needs to sort on
// recency (e.g. the verdicts ledger) without showing a full timestamp.
export function dateTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
