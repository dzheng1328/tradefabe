import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { SPRING } from "../lib/motion";
import { playSelect } from "../lib/sound";

type BookRow = {
  book: string;
  equity: number | null;
  return: number | null;
  return_today: number | null;
  family: string;
  color: string;
  introduced: string | null;
  monitor_only: boolean;
  retired_at: string | null;
  sparkline: (number | null)[];
};

type FamilyGroup = { family: string; label: string; books: BookRow[] };
type SummaryResponse = { families: FamilyGroup[] } | { books: BookRow[] };

type ReviewRow = { book: string; days_live: number; verdict: string };

const SORT_OPTIONS: Record<string, string> = {
  Family: "family",
  "Recently added": "recent",
  "Return today": "return_today",
  "Total return": "total_return",
};

function Sparkline({ points }: { points: (number | null)[] }) {
  const vals = points.filter((v): v is number => v !== null);
  if (vals.length < 2) return <span className="w-10 inline-block" />;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const w = 40, h = 16;
  const step = w / (vals.length - 1);
  const d = vals
    .map((v, i) => `${i === 0 ? "M" : "L"}${i * step},${h - ((v - min) / span) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="inline-block">
      <path d={d} fill="none" stroke="#9fe870" strokeWidth={1.5} />
    </svg>
  );
}

// Matches app.py's `intro.strftime("%-m.%-d.%y")` (tf-book-date) so the two UIs agree
// on the same book's introduced date. Parsed from the ISO string's date digits
// directly rather than through `Date`, which parses a bare "YYYY-MM-DD" as UTC but a
// "YYYY-MM-DDTHH:MM:SS" (no zone) as local time -- inconsistent and timezone-sensitive.
function formatIntroduced(iso: string | null): string {
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  if (!match) return "—";
  const [, year, month, day] = match;
  return `${Number(month)}.${Number(day)}.${year.slice(-2)}`;
}

function Row({ r, selected }: { r: BookRow; selected: boolean }) {
  const delta = r.return_today ?? r.return;
  return (
    <Link to={`/books/${r.book}`} className="block no-underline" onClick={playSelect}>
      <motion.div
        whileHover={{ backgroundColor: "rgba(159,232,112,0.06)" }}
        animate={{
          backgroundColor: selected ? "rgba(159,232,112,0.12)" : "rgba(0,0,0,0)",
        }}
        transition={SPRING}
        className="flex items-center gap-3 px-4 py-2 h-14 text-sm border-b border-white/5"
      >
        <span className="text-ink truncate min-w-0 flex-1">{r.book}</span>
        <span className="text-ink-muted font-mono text-xs shrink-0">
          {formatIntroduced(r.introduced)}
        </span>
        <span className="shrink-0"><Sparkline points={r.sparkline} /></span>
        <span className="text-ink-muted font-mono tabular-nums shrink-0">
          ${r.equity?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "—"}
        </span>
        <span
          className={`font-mono tabular-nums shrink-0 w-14 text-right ${
            delta != null && delta >= 0 ? "text-accent" : "text-red-400"
          }`}
        >
          {delta != null ? `${(delta * 100).toFixed(1)}%` : "—"}
        </span>
      </motion.div>
    </Link>
  );
}

export default function RowList({ selectedName }: { selectedName: string | null }) {
  const [sortLabel, setSortLabel] = useState("Family");
  const [showMonitorOnly, setShowMonitorOnly] = useState(true);
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [review, setReview] = useState<ReviewRow[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const sort = SORT_OPTIONS[sortLabel];
    fetch(`http://localhost:8000/api/books/summary?sort=${sort}&show_monitor_only=${showMonitorOnly}`)
      .then((res) => res.json())
      .then((body: SummaryResponse) => {
        setData(body);
        const allBooks = "families" in body ? body.families.flatMap((f) => f.books) : body.books;
        const stillVisible = selectedName !== null && allBooks.some((b) => b.book === selectedName);
        if (!stillVisible) {
          const first = allBooks[0];
          if (first) navigate(`/books/${first.book}`, { replace: true });
        }
      });
  }, [sortLabel, showMonitorOnly, selectedName, navigate]);

  useEffect(() => {
    fetch("http://localhost:8000/api/books/up_for_review")
      .then((res) => res.json())
      .then((body: { books: ReviewRow[] }) => setReview(body.books));
  }, []);

  if (!data) return <p className="p-4 text-ink-muted">Loading…</p>;

  return (
    <div>
      <div className="p-4 flex items-center justify-between text-xs">
        <label className="flex items-center gap-2">
          Sort by
          <select
            aria-label="Sort by"
            value={sortLabel}
            onChange={(e) => setSortLabel(e.target.value)}
            className="bg-surface text-ink rounded px-1 py-0.5"
          >
            {Object.keys(SORT_OPTIONS).map((label) => (
              <option key={label} value={label}>{label}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            aria-label="Show monitor-only (backtest-DEAD) books"
            type="checkbox"
            checked={showMonitorOnly}
            onChange={(e) => setShowMonitorOnly(e.target.checked)}
          />
          Show monitor-only
        </label>
      </div>

      {review.length > 0 && (
        <details className="px-4 pb-2 text-xs text-ink-muted">
          <summary>Up for review ({review.length})</summary>
          <ul className="mt-2 space-y-1">
            {review.map((r) => (
              <li key={r.book}>{r.book} — {r.days_live}d live, {r.verdict}</li>
            ))}
          </ul>
        </details>
      )}

      {"families" in data
        ? data.families.map((fam) => (
            <div key={fam.family}>
              <div className="px-4 pt-3 pb-1 text-xs uppercase text-ink-muted">{fam.label}</div>
              {fam.books.map((r) => (
                <Row key={r.book} r={r} selected={r.book === selectedName} />
              ))}
            </div>
          ))
        : data.books.map((r) => (
            <Row key={r.book} r={r} selected={r.book === selectedName} />
          ))}
    </div>
  );
}
