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
  const coords = vals.map((v, i) => [i * step, h - ((v - min) / span) * h]);
  const d = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
  const [endX, endY] = coords[coords.length - 1];
  return (
    <svg width={w} height={h} className="inline-block">
      <path d={d} fill="none" stroke="#9fe870" strokeWidth={1.5} />
      <circle cx={endX} cy={endY} r={1.75} fill="#9fe870" />
    </svg>
  );
}

// Idea #24: the shared layoutId lives on this wrapper, not the Sparkline SVG itself,
// and only for a brief window right after selection -- matching Framer's own
// lightbox-demo pattern (thumbnail grid stays mounted forever; the layoutId is handed
// off to whichever instance is "active" so exactly one element owns it at a time).
// DetailPanel's chart-area wrapper claims the same `sparkline-<book>` id for the same
// brief window on open, so the id transfers from the row's sparkline to the chart and
// back to a plain, un-shared sparkline once the SPRING settles.
//
// The row's own local timer (not a prop driven by DetailPanel) is what makes the
// hand-back actually work: if `layoutId` were computed straight from `selected` (true
// for the whole time a book stays open), this component's own props would never
// change again after the initial claim, so it would never re-render once DetailPanel
// dropped its side -- and Framer leaves a claimed-but-abandoned layoutId node exactly
// where it last animated it: `opacity: 0` with a transform pinned at the chart's
// rect, permanently invisible (reproduced live, then confirmed via the node's own
// inline style before this fix). Timing out 50ms after DetailPanel's own release
// (see DetailPanel.tsx) guarantees the chart fully lets go first.
const MORPH_CLAIM_MS = 500;

function SparklineSlot({ book, selected, points }: { book: string; selected: boolean; points: (number | null)[] }) {
  const [claiming, setClaiming] = useState(false);

  useEffect(() => {
    if (!selected) {
      setClaiming(false);
      return;
    }
    setClaiming(true);
    const id = setTimeout(() => setClaiming(false), MORPH_CLAIM_MS);
    return () => clearTimeout(id);
  }, [selected, book]);

  return (
    <motion.span
      layoutId={claiming ? `sparkline-${book}` : undefined}
      transition={SPRING}
      className="shrink-0"
    >
      <Sparkline points={points} />
    </motion.span>
  );
}

// Books this browser has already rendered at least once -- idea #44's burst is a
// one-time "hey, something new appeared" signal, not decoration on every visit.
const SEEN_BOOKS_KEY = "tradefabe.seenBooks";

function readSeenBooks(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_BOOKS_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

// The one strategy that's cleared doctrine (STRATEGIES.md) -- idea #31's subtly
// distinct row treatment. Hardcoded, not verdict-driven: doctrine promotion is a
// deliberate human/harness event (see DOCTRINE.md v1.5/v1.6), not something a row
// list should infer live.
const FEATURED_BOOK = "carry_btc_eth";

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

// Which % this list is currently showing per row: "today" (change since the prior
// close, only meaningful when explicitly sorted that way) or "total" (return since
// each book's own inception, relative to its $100k starting capital -- the only
// number that's comparable across books of very different ages, so it's the default
// for every other sort mode).
type DeltaMode = "today" | "total";

function rowDelta(r: BookRow, mode: DeltaMode): number | null {
  return mode === "today" ? r.return_today ?? r.return : r.return;
}

// toFixed(1) on a genuine-but-tiny negative (e.g. -0.0004) prints the confusing
// "-0.0%" -- reads as a loss at a glance, but is actually indistinguishable from flat
// at this precision. Round first, then normalize -0 to 0 before formatting.
function formatPct(delta: number): string {
  const rounded = Math.round(delta * 1000) / 10;
  return `${rounded === 0 ? 0 : rounded}%`;
}

function Row({
  r, selected, isNew, deltaMode, indented = false, trailingBadge,
}: {
  r: BookRow; selected: boolean; isNew: boolean; deltaMode: DeltaMode; indented?: boolean;
  trailingBadge?: import("react").ReactNode;
}) {
  const delta = rowDelta(r, deltaMode);
  const retired = r.retired_at !== null;
  return (
    <Link to={`/books/${r.book}`} className="block no-underline" data-book={r.book} onClick={playSelect}>
      <motion.div
        layout="position"
        whileHover={{ backgroundColor: "rgba(159,232,112,0.06)" }}
        animate={{
          backgroundColor: selected ? "rgba(159,232,112,0.12)" : "rgba(0,0,0,0)",
        }}
        transition={SPRING}
        className={`tf-row flex items-center gap-3 px-4 py-2 h-14 text-sm border-b border-white/5 transition-transform hover:-translate-y-px hover:shadow-[0_4px_16px_rgba(0,0,0,0.35)] ${
          isNew ? "tf-book-burst" : ""
        } ${indented ? "pl-8" : ""} ${retired ? "opacity-50" : ""}`}
      >
        <span className="text-ink truncate min-w-0 flex-1 flex items-center gap-2">
          {r.book}
          {r.book === FEATURED_BOOK && (
            <span className="tf-featured-chip text-[10px] leading-none px-1.5 py-0.5 rounded-full border border-accent text-accent shrink-0">
              cleared
            </span>
          )}
          {retired && (
            <span
              title={`Retired ${r.retired_at}`}
              className="text-[10px] leading-none px-1.5 py-0.5 rounded-full border border-ink-muted text-ink-muted shrink-0"
            >
              retired
            </span>
          )}
        </span>
        {trailingBadge}
        <span className="text-ink-muted font-mono text-xs shrink-0">
          {formatIntroduced(r.introduced)}
        </span>
        <SparklineSlot book={r.book} selected={selected} points={r.sparkline} />
        <span className="text-ink-muted font-mono tabular-nums shrink-0">
          ${r.equity?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "—"}
        </span>
        <span
          className={`font-mono tabular-nums shrink-0 w-14 text-right ${
            delta != null && delta >= 0 ? "text-accent" : "text-red-400"
          }`}
        >
          {delta != null ? formatPct(delta) : "—"}
        </span>
      </motion.div>
    </Link>
  );
}

// A cluster's signature: books whose equity, total return, AND full sparkline are all
// identical -- i.e. their live paper curves have been genuinely indistinguishable so
// far, not just "close." Sparkline is included (not just equity) so two books that
// happen to match today but diverged yesterday are NOT collapsed.
function curveSignature(r: BookRow): string {
  const eq = r.equity == null ? null : Math.round(r.equity * 100);
  const ret = r.return == null ? null : Math.round(r.return * 10000);
  const spark = r.sparkline.map((v) => (v == null ? null : Math.round(v * 100)));
  return JSON.stringify([eq, ret, spark]);
}

// Groups rows that share a curveSignature, preserving first-seen order both across
// groups and within a group -- the server's own sort order stays intact for whichever
// book of each cluster is picked as the representative.
function clusterRows(rows: BookRow[]): BookRow[][] {
  const order: string[] = [];
  const groups = new Map<string, BookRow[]>();
  for (const r of rows) {
    const sig = curveSignature(r);
    if (!groups.has(sig)) {
      groups.set(sig, []);
      order.push(sig);
    }
    groups.get(sig)!.push(r);
  }
  return order.map((sig) => groups.get(sig)!);
}

function ClusterRow({
  group, selectedName, newBooks, deltaMode,
}: { group: BookRow[]; selectedName: string | null; newBooks: Set<string>; deltaMode: DeltaMode }) {
  const containsSelected = group.some((r) => r.book === selectedName);
  const [expanded, setExpanded] = useState(containsSelected);

  useEffect(() => {
    if (containsSelected) setExpanded(true);
  }, [containsSelected]);

  if (group.length === 1) {
    const r = group[0];
    return <Row r={r} selected={r.book === selectedName} isNew={newBooks.has(r.book)} deltaMode={deltaMode} />;
  }

  const [head, ...rest] = group;
  const badge = (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setExpanded((v) => !v);
      }}
      className="text-[10px] uppercase tracking-wide text-ink-muted hover:text-accent px-1.5 py-0.5 rounded-full border border-white/10 shrink-0"
    >
      {expanded ? "hide" : `+${rest.length} identical`}
    </button>
  );
  return (
    <div>
      <Row
        r={head}
        selected={head.book === selectedName}
        isNew={newBooks.has(head.book)}
        deltaMode={deltaMode}
        trailingBadge={badge}
      />
      {expanded &&
        rest.map((r) => (
          <Row
            key={r.book}
            r={r}
            selected={r.book === selectedName}
            isNew={newBooks.has(r.book)}
            deltaMode={deltaMode}
            indented
          />
        ))}
    </div>
  );
}

export default function RowList({ selectedName }: { selectedName: string | null }) {
  const [sortLabel, setSortLabel] = useState("Family");
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [review, setReview] = useState<ReviewRow[]>([]);
  const [reviewCountPulsed, setReviewCountPulsed] = useState(false);
  const [newBooks, setNewBooks] = useState<Set<string>>(new Set());
  const navigate = useNavigate();

  useEffect(() => {
    const sort = SORT_OPTIONS[sortLabel];
    fetch(`http://localhost:8000/api/books/summary?sort=${sort}`)
      .then((res) => res.json())
      .then((body: SummaryResponse) => {
        setData(body);
        const allBooks = "families" in body ? body.families.flatMap((f) => f.books) : body.books;
        const seen = readSeenBooks();
        setNewBooks(new Set(allBooks.map((b) => b.book).filter((name) => !seen.has(name))));
        localStorage.setItem(SEEN_BOOKS_KEY, JSON.stringify(allBooks.map((b) => b.book)));
        const stillVisible = selectedName !== null && allBooks.some((b) => b.book === selectedName);
        if (!stillVisible) {
          const first = allBooks[0];
          if (first) navigate(`/books/${first.book}`, { replace: true });
        }
      });
  }, [sortLabel, selectedName, navigate]);

  useEffect(() => {
    fetch("http://localhost:8000/api/books/up_for_review")
      .then((res) => res.json())
      .then((body: { books: ReviewRow[] }) => {
        setReview(body.books);
        const key = "tradefabe.reviewCount";
        const prev = localStorage.getItem(key);
        setReviewCountPulsed(prev !== null && Number(prev) !== body.books.length);
        localStorage.setItem(key, String(body.books.length));
      });
  }, []);

  if (!data) {
    return (
      <div className="p-4 pt-2">
        {Array.from({ length: 6 }, (_, i) => (
          <div
            key={i}
            className="tf-skeleton-row flex items-center gap-3 h-14 border-b border-white/5"
          >
            <span className="h-3 w-32 rounded bg-surface animate-pulse" />
            <span className="ml-auto h-3 w-16 rounded bg-surface animate-pulse" />
          </div>
        ))}
      </div>
    );
  }

  const sortControl = (
    <label className="flex items-center gap-2 text-xs uppercase text-ink-muted shrink-0">
      Sort by
      <select
        aria-label="Sort by"
        value={sortLabel}
        onChange={(e) => setSortLabel(e.target.value)}
        className="bg-transparent text-ink-muted uppercase text-xs tracking-wide border-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:text-ink"
      >
        {Object.keys(SORT_OPTIONS).map((label) => (
          <option key={label} value={label} className="normal-case bg-surface text-ink">
            {label}
          </option>
        ))}
      </select>
    </label>
  );

  const deltaMode: DeltaMode = sortLabel === "Return today" ? "today" : "total";

  return (
    <div>
      {review.length > 0 && (
        <details className="px-4 pb-2 text-xs text-ink-muted">
          <summary>
            Up for review (
            <span className={reviewCountPulsed ? "review-badge-pulse" : undefined}>{review.length}</span>
            )
          </summary>
          <ul className="mt-2 space-y-1">
            {review.map((r) => (
              <li key={r.book}>{r.book} — {r.days_live}d live, {r.verdict}</li>
            ))}
          </ul>
        </details>
      )}

      {"families" in data
        ? data.families.map((fam, i) => (
            <div key={fam.family}>
              <div className="px-4 pt-2 pb-1 flex items-center justify-between gap-4">
                <span className="relative text-xs uppercase text-ink-muted">
                  {fam.label}
                  <span className="family-underline absolute -bottom-1 left-0 h-px w-6 bg-accent origin-left animate-underline-draw" />
                </span>
                {i === 0 && sortControl}
              </div>
              {clusterRows(fam.books).map((group) => (
                <ClusterRow
                  key={group[0].book}
                  group={group}
                  selectedName={selectedName}
                  newBooks={newBooks}
                  deltaMode={deltaMode}
                />
              ))}
            </div>
          ))
        : (
            <>
              <div className="px-4 pt-2 pb-1 flex items-center justify-end">{sortControl}</div>
              {(() => {
                // Backend already sorts retired last regardless of sort_key (see
                // dashboard.sort_books_flat's own "_retired" primary sort key) -- this
                // just draws the same "Retired" divider the family view gets for free
                // from its own trailing group, so retired books read as a distinct
                // section here too instead of trailing off silently.
                const active = data.books.filter((b) => b.retired_at === null);
                const retired = data.books.filter((b) => b.retired_at !== null);
                return (
                  <>
                    {clusterRows(active).map((group) => (
                      <ClusterRow
                        key={group[0].book}
                        group={group}
                        selectedName={selectedName}
                        newBooks={newBooks}
                        deltaMode={deltaMode}
                      />
                    ))}
                    {retired.length > 0 && (
                      <div>
                        <div className="px-4 pt-2 pb-1">
                          <span className="relative text-xs uppercase text-ink-muted">
                            Retired
                            <span className="family-underline absolute -bottom-1 left-0 h-px w-6 bg-accent origin-left animate-underline-draw" />
                          </span>
                        </div>
                        {clusterRows(retired).map((group) => (
                          <ClusterRow
                            key={group[0].book}
                            group={group}
                            selectedName={selectedName}
                            newBooks={newBooks}
                            deltaMode={deltaMode}
                          />
                        ))}
                      </div>
                    )}
                  </>
                );
              })()}
            </>
          )}
    </div>
  );
}
