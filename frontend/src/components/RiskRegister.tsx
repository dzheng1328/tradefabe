type Entry = {
  key: string; title: string; category: string; likelihood: string; impact: string;
  detail: string; source: string | null; url: string | null; measured: boolean;
};

const SEVERITY_COLOR: Record<string, string> = {
  "total loss": "text-red-400", severe: "text-amber-400",
  moderate: "text-amber-400", operational: "text-ink-muted",
};

export default function RiskRegister({ entries }: { entries: Entry[] }) {
  return (
    <div>
      {entries.map((r) => (
        <details key={r.key} className="border-t border-white/5 py-3">
          <summary className="text-sm text-ink cursor-pointer">{r.title}</summary>
          <div className="mt-2 text-xs font-mono">
            <span className={SEVERITY_COLOR[r.category] ?? "text-ink-muted"}>{r.category}</span>
            {" · "}
            <span className={r.measured ? "text-accent" : "text-ink-muted"}>
              {r.measured ? "measured" : "cited"}
            </span>
          </div>
          <p className="text-sm text-ink mt-2"><strong>How often:</strong> {r.likelihood}</p>
          <p className="text-sm text-ink mt-1"><strong>If it happens:</strong> {r.impact}</p>
          <p className="text-xs text-ink-muted mt-2">{r.detail}</p>
          {r.source && (
            <p className="text-xs text-ink-muted mt-2">
              Source:{" "}
              {r.url ? (
                <a href={r.url} className="underline" target="_blank" rel="noreferrer">
                  {r.source}
                </a>
              ) : (
                r.source
              )}
            </p>
          )}
        </details>
      ))}
      <p className="text-xs text-ink-muted mt-3">
        Cited entries carry a real source; measured entries are computed from this
        lab's own data. Neither is a forecast — a base rate is what happened to a
        population, not a probability for this book. Absence of a bad case in a
        3-year sample is not evidence one cannot occur.
      </p>
    </div>
  );
}
