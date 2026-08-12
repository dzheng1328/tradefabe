// Reusable depth/border-glow stat tile (idea #33). Introduced for DetailPanel's
// Sharpe/Sortino/Calmar/MaxDD/CAGR/Vol row; Phase 4 (sub-project 2b) reuses this
// verbatim for the positions "Capital deployed" stat row -- keep this generic
// (label/value only), not DetailPanel-specific.
export default function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="tf-stat-tile rounded-lg border border-white/5 bg-surface/60 px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_3px_rgba(0,0,0,0.3)] transition-colors hover:border-accent/30">
      <div className="text-xs text-ink-muted uppercase">{label}</div>
      <div className="text-xl text-ink font-mono tabular-nums">{value}</div>
    </div>
  );
}
