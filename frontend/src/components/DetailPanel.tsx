import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode, SyntheticEvent } from "react";
import { motion } from "framer-motion";
import type { Data } from "plotly.js";
import RangeControl from "./RangeControl";
import RingLoader from "./RingLoader";
import StatTile from "./StatTile";
import DeploymentStats from "./DeploymentStats";
import PositionsTable from "./PositionsTable";
import TradeLog from "./TradeLog";
import CarryRiskPanel from "./CarryRiskPanel";
import RiskRegister from "./RiskRegister";
import { prefersReducedMotion, SPRING } from "../lib/motion";
import { playDataLanded, playRangeChange } from "../lib/sound";
import { fmt, money } from "../lib/format";

// plotly.js alone is ~1.5MB gzipped -- lazy-loading keeps it out of the initial
// bundle (RowList/Nav/routing shell) and fetches it only once a book is actually
// opened, which is also the earliest point a real figure exists to render.
const PlotlyChart = lazy(() => import("./PlotlyChart"));

type DetailResponse = {
  name: string;
  kind: "equity" | "carry";
  blurb: string;
  retirement_note: { at: string; reason: string } | null;
  stats: Record<"Sharpe" | "Sortino" | "Calmar" | "MaxDD" | "CAGR" | "Vol", number | null>;
  live_start: string;
  bt_start: string | null;
  available_windows: string[];
  live_equity_chart: { data: Data[]; layout: Record<string, unknown> };
  backtest_chart: { data: Data[]; layout: Record<string, unknown> };
  divergence_state: "insufficient" | "ok" | "diverging";
  divergence_detail: string;
  verdict?: string;
  corr_bench?: number | null;
  null_p95?: number | null;
  freq?: string;
  carry_meta?: Record<string, number | null>;
  accrual_only?: boolean;
  cost_bps?: number | null;
  deployment?: {
    cash: number | null; gross: number | null; net: number | null; equity: number | null;
    cash_pct: number | null; gross_pct: number | null; net_pct: number | null;
    n_unpriced: number; n_held: number; priced_at: string | null; is_short_funded: boolean;
  } | null;
  positions?: {
    ticker: string; units: number | null; last_price: number | null;
    value: number | null; weight: number | null;
  }[] | null;
  positions_asof?: string | null;
  trades?: {
    ts: string | null; ticker: string | null; side: string | null; shares: number | null;
    price: number | null; notional: number | null; position_after: number | null;
  }[];
  book_state?: { equity: number | null; last_run: string | null } | null;
  carry_risk?: Parameters<typeof CarryRiskPanel>[0]["risk"];
  risk_register?: Parameters<typeof RiskRegister>[0]["entries"];
};

// Plotly's newer to_json() compresses numeric traces into a typed-array form
// (`{dtype, bdata}`, base64) instead of a plain JS array -- the real API sends this
// shape (react-plotly.js decodes it internally when rendering the chart, but our own
// direct read of `y` for the hero number below needs to do the same).
type PlotlyTypedArray = { dtype: string; bdata: string };

const TYPED_ARRAY_CTORS: Record<string, { new (buffer: ArrayBuffer): { [i: number]: number; length: number } }> = {
  f8: Float64Array, f4: Float32Array,
  i1: Int8Array, u1: Uint8Array,
  i2: Int16Array, u2: Uint16Array,
  i4: Int32Array, u4: Uint32Array,
};

function decodePlotlyArray(y: unknown): (number | null)[] {
  if (Array.isArray(y)) return y;
  if (y && typeof y === "object" && "bdata" in y && "dtype" in y) {
    const { dtype, bdata } = y as PlotlyTypedArray;
    const binary = atob(bdata);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const Ctor = TYPED_ARRAY_CTORS[dtype] ?? Float64Array;
    return Array.from(new Ctor(bytes.buffer));
  }
  return [];
}

// Idea #17's hero number reads straight off the same trace react-plotly.js draws --
// no separate backend field to keep in sync with the chart it sits above.
function latestEquity(chart: DetailResponse["live_equity_chart"]): number | null {
  const ys = decodePlotlyArray((chart.data[0] as { y?: unknown } | undefined)?.y);
  for (let i = ys.length - 1; i >= 0; i--) {
    const v = ys[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) return v;
  }
  return null;
}

// Idea #16: the blurb reveals word-by-word rather than popping in whole.
function BlurbReveal({ text }: { text: string }) {
  const words = text.split(" ");
  return (
    <p className="text-ink-muted mt-1">
      {words.map((word, i) => (
        <span key={i}>
          <motion.span
            className="tf-word inline-block"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: prefersReducedMotion() ? 0 : i * 0.03 }}
          >
            {word}
          </motion.span>
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </p>
  );
}

// Idea #18: section headers get a subtle entrance. Uses a translateX + opacity
// (compositor-only) rather than an animated letter-spacing, which would reflow the
// text's layout on every frame (fixing-motion-performance rule 2: default to
// transform/opacity for motion).
// Idea #35: the verdict badge (DEAD/ALIVE) gets a one-time "stamp" animation the
// first time it's rendered THIS SESSION per book -- sessionStorage, not
// localStorage, since a stamp should replay on a fresh visit, just not on every
// re-render/refetch within one sitting (matches Intro.tsx's session-gate shape).
const VERDICT_STAMPED_KEY = "tradefabe.verdictStamped";

function consumeVerdictStamp(book: string): boolean {
  let stamped: string[] = [];
  try {
    stamped = JSON.parse(sessionStorage.getItem(VERDICT_STAMPED_KEY) ?? "[]");
  } catch {
    stamped = [];
  }
  if (stamped.includes(book)) return false;
  sessionStorage.setItem(VERDICT_STAMPED_KEY, JSON.stringify([...stamped, book]));
  return true;
}

function VerdictBadge({ book, verdict }: { book: string; verdict: string }) {
  const [stamp] = useState(() => consumeVerdictStamp(book));
  return (
    <span
      className={`font-mono ${stamp ? "tf-verdict-stamp" : ""} ${
        verdict === "ALIVE" ? "text-accent" : "text-red-400"
      }`}
    >
      {verdict}
    </span>
  );
}

// Idea #26: a live "as of Xs ago" ticker next to the equity number, so staleness is
// legible without a page refresh. Ticks off when the CURRENT response actually
// landed, not `live_start` (the book's own start date, unrelated to fetch recency).
function FreshnessTicker({ landedAt }: { landedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const secondsAgo = Math.max(0, Math.floor((now - landedAt) / 1000));
  const label = secondsAgo < 60 ? `${secondsAgo}s ago` : `${Math.floor(secondsAgo / 60)}m ago`;
  return (
    <span data-testid="freshness" className="text-xs font-mono tabular-nums text-ink-muted">
      as of {label}
    </span>
  );
}

function SectionHeader({ children }: { children: ReactNode }) {
  return (
    <motion.span
      className="tf-section-header text-sm text-ink inline-block"
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={SPRING}
    >
      {children}
    </motion.span>
  );
}

export default function DetailPanel({ name }: { name: string }) {
  const [data, setData] = useState<DetailResponse | null>(null);
  const [window, setWindow] = useState("ALL");
  const [dataLandedAt, setDataLandedAt] = useState(0);
  // True from a name change until that book's first response lands -- distinguishes
  // "just opened this book" (plays the landed sound) from "changed the range window on
  // a book already open" (RangeControl's own click sound already covers that feedback;
  // playing both would double up).
  const isInitialLoad = useRef(true);
  const backtestDetailsRef = useRef<HTMLDetailsElement>(null);
  // Idea #24's shared layoutId can only ever have one live owner: RowList's selected
  // sparkline never unmounts, so if this chart wrapper held the same layoutId forever
  // too, framer-motion would treat it as a permanent duplicate and hide one copy
  // outright (reproduced live -- the selected row's own sparkline vanished). Claiming
  // the id only for the one-time grow animation, then handing it back to the row once
  // the SPRING transition has settled, keeps exactly one owner at rest.
  const [morphing, setMorphing] = useState(true);

  useEffect(() => {
    setData(null);
    setWindow("ALL");
    isInitialLoad.current = true;
    setMorphing(true);
  }, [name]);

  useEffect(() => {
    if (!data) return;
    const id = setTimeout(() => setMorphing(false), 450);
    return () => clearTimeout(id);
  }, [data]);

  // Native <details> fires onToggle for both open AND close -- only the reveal gets
  // a sound (idea #43's "about to play" spirit: closing isn't a new thing appearing).
  // The chart it reveals sits right at/below the fold, so without the scroll it's easy
  // to miss that anything happened at all.
  //
  // The backtest PlotlyChart is already mounted (React renders <Suspense> content
  // regardless of <details>'s native open/closed display), just hidden -- so opening
  // reveals a real container size for the first time, and react-plotly.js's own
  // ResizeObserver relayouts it right then. Starting a smooth-scroll animation in that
  // same tick let the scroll and Plotly's resize/redraw fight over layout on every
  // frame and pegged the main thread hard enough to freeze the tab (reproduced twice
  // live). Deferring two animation frames lets that resize settle before scrolling.
  function handleBacktestToggle(e: SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open) return;
    playRangeChange();
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        backtestDetailsRef.current?.scrollIntoView({
          behavior: prefersReducedMotion() ? "auto" : "smooth",
          block: "start",
        });
      });
    });
  }

  useEffect(() => {
    fetch(`http://localhost:8000/api/books/${name}/detail?window=${window}`)
      .then((res) => res.json())
      .then((body: DetailResponse) => {
        setData(body);
        setDataLandedAt(Date.now());
        if (isInitialLoad.current) {
          playDataLanded();
          isInitialLoad.current = false;
        }
      });
  }, [name, window]);

  // Idea #20 replaces the plain "Loading…" text with Phase 0's ring loader. Idea
  // #23's crossfade rides on the same mechanism already used when switching books:
  // this motion.div is keyed by `name`, so React remounts it fresh on selection
  // change and its own initial/animate fade-in (below) crossfades the new content
  // in, rather than a hard, instant swap.
  if (!data) {
    return (
      <div className="flex justify-center py-12">
        <RingLoader />
      </div>
    );
  }

  const statEntries: [string, number | null][] = [
    ["Sharpe", data.stats.Sharpe], ["Sortino", data.stats.Sortino],
    ["Calmar", data.stats.Calmar], ["Max Drawdown", data.stats.MaxDD],
    ["CAGR", data.stats.CAGR], ["Vol (ann.)", data.stats.Vol],
  ];

  return (
    <motion.div
      key={name}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={SPRING}
      className={data.retirement_note ? "tf-frozen" : undefined}
    >
      <h2 className="text-2xl font-bold text-ink">{name}</h2>
      <BlurbReveal text={data.blurb} />

      {latestEquity(data.live_equity_chart) !== null && (
        <div className="mt-3 flex items-baseline gap-3">
          <div className="tf-equity-hero font-mono tabular-nums font-bold text-ink text-5xl">
            {latestEquity(data.live_equity_chart)!.toLocaleString(undefined, {
              style: "currency",
              currency: "USD",
              maximumFractionDigits: 0,
            })}
          </div>
          {dataLandedAt > 0 && <FreshnessTicker landedAt={dataLandedAt} />}
        </div>
      )}

      {data.retirement_note && (
        <div className="bg-surface bg-topo bg-repeat rounded-card p-4 mt-4 text-sm">
          Retired {data.retirement_note.at} — {data.retirement_note.reason}
        </div>
      )}

      <div className="grid grid-cols-6 gap-4 mt-6 pb-6 border-b border-white/5">
        {statEntries.map(([label, kind]) => (
          <StatTile
            key={label}
            label={label}
            value={fmt(kind, label === "Max Drawdown" || label === "CAGR" || label === "Vol (ann.)" ? "pct" : "ratio")}
          />
        ))}
      </div>

      {data.kind === "equity" ? (
        <p className="text-xs text-ink-muted mt-2 font-mono">
          Verdict: <VerdictBadge book={name} verdict={data.verdict ?? "—"} /> · corr to 60/40:{" "}
          {fmt(data.corr_bench)} · noise floor: {fmt(data.null_p95)} · rebalance {data.freq}
        </p>
      ) : (
        <p className="text-xs text-ink-muted mt-2 font-mono">
          Net yield: {fmt(data.carry_meta?.net_yield, "pct")} · % days positive:{" "}
          {fmt(data.carry_meta?.pct_days_positive, "pct")}
        </p>
      )}

      <div className="mt-6 pt-6 border-t border-white/5">
        <div className="flex items-center justify-between">
          <SectionHeader>Live paper equity</SectionHeader>
          <RangeControl options={data.available_windows} value={window} onChange={setWindow} />
        </div>
        <motion.div layoutId={morphing ? `sparkline-${name}` : undefined} transition={SPRING}>
          <Suspense fallback={<div className="h-[340px]" />}>
            <PlotlyChart figure={data.live_equity_chart} />
          </Suspense>
        </motion.div>
      </div>

      <details
        ref={backtestDetailsRef}
        className="mt-6 pt-6 border-t border-white/5"
        onToggle={handleBacktestToggle}
      >
        <summary className="text-sm text-ink cursor-pointer">
          <SectionHeader>Backtest history & live tracking check</SectionHeader>
        </summary>
        <Suspense fallback={<div className="h-[340px]" />}>
          <PlotlyChart figure={data.backtest_chart} />
        </Suspense>
        <p className="text-xs text-ink-muted mt-2">
          <span
            className={`font-mono ${data.divergence_state === "diverging" ? "tf-divergence-pulse text-red-400" : ""}`}
          >
            {data.divergence_state}
          </span>
          : {data.divergence_detail}
        </p>
      </details>

      <div className="mt-6 pt-6 border-t border-white/5">
        {data.kind === "equity" ? (
          <>
            <SectionHeader>Capital deployed</SectionHeader>
            {data.accrual_only ? (
              <p className="text-ink-muted text-sm mt-3">
                This book is delta-neutral carry: its value moves from funding accrual,
                not discrete positions, so there's no cash/gross/net breakdown to show
                here — the live equity chart above is the real number.
              </p>
            ) : (
              <>
                <div className="mt-3">
                  <DeploymentStats deployment={data.deployment!} />
                </div>
                <div className="mt-6">
                  <SectionHeader>Current positions</SectionHeader>
                  <div className="mt-3">
                    <PositionsTable positions={data.positions ?? null} positionsAsof={data.positions_asof ?? null} />
                  </div>
                </div>
              </>
            )}
          </>
        ) : null}

        {data.kind === "equity" && (
          <div className="mt-6 pt-6 border-t border-white/5">
            <SectionHeader>Trade log</SectionHeader>
            <div className="mt-3">
              <TradeLog
                trades={data.trades ?? []}
                accrualOnly={data.accrual_only ?? false}
                costBps={data.cost_bps ?? null}
              />
            </div>
          </div>
        )}

        {data.kind === "carry" && (
          <>
            <SectionHeader>Book state</SectionHeader>
            <p className="text-sm text-ink mt-2">
              Equity <strong className="font-mono">{money(data.book_state?.equity ?? null)}</strong>
              {" · "}last run <strong className="font-mono">{data.book_state?.last_run ?? "—"}</strong>
            </p>

            <div className="mt-6 pt-6 border-t border-white/5">
              <SectionHeader>Risk monitor — funding-flip alert + short-leg liquidation distance</SectionHeader>
              <div className="mt-3">
                <CarryRiskPanel risk={data.carry_risk ?? null} />
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-white/5">
              <SectionHeader>Risk register — what the ~12%/yr is actually paying for</SectionHeader>
              <div className="mt-3">
                <RiskRegister entries={data.risk_register ?? []} />
              </div>
            </div>
          </>
        )}
      </div>
    </motion.div>
  );
}
