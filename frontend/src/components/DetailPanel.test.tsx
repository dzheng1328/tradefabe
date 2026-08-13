import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DetailPanel from "./DetailPanel";

const DETAIL_RESPONSE = {
  name: "tsmom_12m",
  kind: "equity",
  blurb: "Sign of the trailing 12-month return.",
  retirement_note: null,
  stats: { Sharpe: 0.8, Sortino: 1.1, Calmar: 0.5, MaxDD: -0.12, CAGR: 0.06, Vol: 0.1 },
  live_start: "2026-01-01T00:00:00",
  bt_start: "2018-01-02T00:00:00",
  available_windows: ["1D", "1W", "1M", "ALL"],
  live_equity_chart: {
    data: [{ y: [100000, 101200, null, 103241] }],
    layout: {},
  },
  backtest_chart: { data: [], layout: {} },
  divergence_state: "ok",
  divergence_detail: "Live is tracking backtest within the expected band.",
  verdict: "ALIVE",
  corr_bench: 0.1,
  null_p95: 0.4,
  freq: "D",
  accrual_only: false,
  cost_bps: 5,
  deployment: {
    cash: 100000, gross: 0, net: 0, equity: 100000,
    cash_pct: 1, gross_pct: 0, net_pct: 0,
    n_unpriced: 0, n_held: 0, priced_at: null, is_short_funded: false,
  },
  positions: [],
  positions_asof: null,
  trades: [],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(DETAIL_RESPONSE) })
  ) as unknown as typeof fetch;
});

afterEach(() => {
  // vi.restoreAllMocks() only reverts vi.spyOn spies to their original
  // implementation -- it does not clear call history for a plain vi.fn() created
  // inside a vi.mock() factory (like playDataLanded/playRangeChange below), so
  // their call counts silently accumulated across every test in this file.
  // vi.clearAllMocks() is what actually resets .mock.calls for those.
  vi.clearAllMocks();
});

vi.mock("../lib/sound", () => ({ playDataLanded: vi.fn(), playRangeChange: vi.fn() }));

describe("DetailPanel", () => {
  it("shows the ring-loader while loading, not a plain Loading… flash", async () => {
    const { container } = render(<DetailPanel name="tsmom_12m" />);
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    expect(container.querySelector("canvas.ring-loader")).not.toBeNull();
    await waitFor(() => expect(screen.getByText("Sign", { exact: false })).toBeInTheDocument());
    expect(container.querySelector("canvas.ring-loader")).toBeNull();
  });

  it("renders the blurb and stats once loaded", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() =>
      expect(screen.getByText("Sign", { exact: false })).toBeInTheDocument()
    );
    expect(screen.getByText("0.80")).toBeInTheDocument(); // Sharpe
  });

  it("shows the latest equity as an oversized hero number, reading it from the chart's last finite point", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("Sign", { exact: false })).toBeInTheDocument());
    expect(screen.getByText("$103,241")).toBeInTheDocument();
    expect(screen.getByText("$103,241").className).toMatch(/tf-equity-hero/);
  });

  it("reads the equity hero number from Plotly's compressed typed-array format too (real API responses use this, not a plain array)", async () => {
    // Float64 [100000, 107500] little-endian, base64-encoded -- what the real
    // /api/books/:name/detail endpoint actually sends via plotly's to_json().
    const bytes = new Uint8Array(new Float64Array([100000, 107500]).buffer);
    const bdata = btoa(String.fromCharCode(...bytes));
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            ...DETAIL_RESPONSE,
            live_equity_chart: { data: [{ y: { dtype: "f8", bdata } }], layout: {} },
          }),
      })
    ) as unknown as typeof fetch;
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("Sign", { exact: false })).toBeInTheDocument());
    expect(screen.getByText("$107,500")).toBeInTheDocument();
  });

  it("reveals the blurb word-by-word", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("Sign", { exact: false })).toBeInTheDocument());
    const words = screen.getAllByText(/^\S+$/, { selector: ".tf-word" });
    expect(words.length).toBe(DETAIL_RESPONSE.blurb.split(" ").length);
  });

  it("stamps the verdict badge with a one-time animation on first render this session", async () => {
    sessionStorage.clear();
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("ALIVE")).toBeInTheDocument());
    expect(screen.getByText("ALIVE").className).toMatch(/tf-verdict-stamp/);
  });

  it("does not re-stamp a verdict badge already stamped this session", async () => {
    sessionStorage.setItem("tradefabe.verdictStamped", JSON.stringify(["tsmom_12m"]));
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("ALIVE")).toBeInTheDocument());
    expect(screen.getByText("ALIVE").className).not.toMatch(/tf-verdict-stamp/);
  });

  it("gives a retired book's panel a frozen treatment", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            ...DETAIL_RESPONSE,
            retirement_note: { at: "2026-07-01", reason: "superseded" },
          }),
      })
    ) as unknown as typeof fetch;
    const { container } = render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText(/Retired/)).toBeInTheDocument());
    expect(container.querySelector(".tf-frozen")).not.toBeNull();
  });

  it("does not give a live book's panel the frozen treatment", async () => {
    const { container } = render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("Sign", { exact: false })).toBeInTheDocument());
    expect(container.querySelector(".tf-frozen")).toBeNull();
  });

  it("shows a live freshness ticker near the equity number that counts up as time passes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DetailPanel name="tsmom_12m" />);
    await vi.waitFor(() => expect(screen.getByText("$103,241")).toBeInTheDocument());
    expect(screen.getByTestId("freshness")).toHaveTextContent("as of 0s ago");
    await vi.advanceTimersByTimeAsync(5000);
    expect(screen.getByTestId("freshness")).toHaveTextContent("as of 5s ago");
    vi.useRealTimers();
  });

  it("pulses the divergence badge when the state is diverging", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ ...DETAIL_RESPONSE, divergence_state: "diverging", divergence_detail: "live is off-band" }),
      })
    ) as unknown as typeof fetch;
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText(/diverging/)).toBeInTheDocument());
    expect(screen.getByText(/diverging/).className).toMatch(/tf-divergence-pulse/);
  });

  it("does not pulse the divergence badge when the state is ok", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText(/^ok/)).toBeInTheDocument());
    expect(screen.getByText(/^ok/).className).not.toMatch(/tf-divergence-pulse/);
  });

  it("refetches the detail with the new window when a range option is clicked", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("1W")).toBeInTheDocument());
    await userEvent.click(screen.getByText("1W"));
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("window=1W"))).toBe(true);
    });
  });

  it("refetches when the name prop changes", async () => {
    const { rerender } = render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1));
    rerender(<DetailPanel name="carry_btc_eth" />);
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("/books/carry_btc_eth/detail"))).toBe(true);
    });
  });

  it("plays the data-landed sound once on initial load, not again on a window refetch", async () => {
    const { playDataLanded } = await import("../lib/sound");
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(playDataLanded).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByText("1W"));
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("window=1W"))).toBe(true);
    });
    expect(playDataLanded).toHaveBeenCalledTimes(1);
  });

  it("plays the range-change sound when a range option is clicked", async () => {
    const { playRangeChange } = await import("../lib/sound");
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("1W")).toBeInTheDocument());
    await userEvent.click(screen.getByText("1W"));
    expect(playRangeChange).toHaveBeenCalled();
  });

  it("plays a sound and scrolls the section into view when the backtest-history disclosure opens", async () => {
    const { playRangeChange } = await import("../lib/sound");
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() =>
      expect(screen.getByText("Backtest history & live tracking check")).toBeInTheDocument()
    );
    const scrollIntoViewSpy = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoViewSpy;

    await userEvent.click(screen.getByText("Backtest history & live tracking check"));

    expect(playRangeChange).toHaveBeenCalled();
    // Deferred two animation frames past the click -- see handleBacktestToggle.
    await waitFor(() => expect(scrollIntoViewSpy).toHaveBeenCalled());
  });

  it("does not replay the sound when the backtest-history disclosure is closed again", async () => {
    const { playRangeChange } = await import("../lib/sound");
    render(<DetailPanel name="tsmom_12m" />);
    const summary = await screen.findByText("Backtest history & live tracking check");
    HTMLElement.prototype.scrollIntoView = vi.fn();

    await userEvent.click(summary); // open
    expect(playRangeChange).toHaveBeenCalledTimes(1);
    await userEvent.click(summary); // close
    expect(playRangeChange).toHaveBeenCalledTimes(1);
  });

  it("renders capital-deployed stats, positions, and trade log for an equity book", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            ...DETAIL_RESPONSE,
            accrual_only: false,
            cost_bps: 5,
            deployment: {
              cash: 20000, gross: 90000, net: 80000, equity: 100000,
              cash_pct: 0.2, gross_pct: 0.9, net_pct: 0.8,
              n_unpriced: 0, n_held: 1, priced_at: "2026-08-12", is_short_funded: false,
            },
            positions: [{ ticker: "SPY", units: 10, last_price: 450, value: 4500, weight: 0.045 }],
            positions_asof: "2026-08-12",
            trades: [],
          }),
      })
    ) as unknown as typeof fetch;
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() => expect(screen.getByText("$100,000")).toBeInTheDocument());
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText(/No fills recorded yet/)).toBeInTheDocument();
  });

  it("shows the accrual-only caption instead of deployment/positions for a delta-neutral equity book", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            ...DETAIL_RESPONSE,
            accrual_only: true, cost_bps: null, deployment: null, positions: null,
            positions_asof: null, trades: [],
          }),
      })
    ) as unknown as typeof fetch;
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() =>
      expect(screen.getByText(/no cash\/gross\/net breakdown/)).toBeInTheDocument()
    );
  });

  it("renders the risk-monitor panel and risk register for the carry book", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            ...DETAIL_RESPONSE,
            kind: "carry",
            carry_meta: { net_yield: 0.12, pct_days_positive: 0.87 },
            book_state: { equity: 105000, last_run: "2026-08-12" },
            carry_risk: {
              generated_at: "2026-08-13T00:00:00", funding_window_days: 7,
              coins: {
                BTC: { funding_7d: 0.001, funding_flip_alert: false, max_leverage: 40,
                       maint_margin: 0.0125, postures: {} },
                ETH: { funding_7d: 0.001, funding_flip_alert: false, max_leverage: 25,
                       maint_margin: 0.02, postures: {} },
              },
              blended_funding_7d: 0.001, blended_funding_flip_alert: false,
              headline_leverage_fraction: 0.25, liq_distance_warn: 0.25,
              high_risk_alert: { BTC: false, ETH: false },
            },
            risk_register: [
              { key: "op", title: "Operational / data bugs", category: "operational",
                likelihood: "Several.", impact: "Wrong numbers.", detail: "See CLAUDE.md.",
                source: null, url: null, measured: true },
            ],
          }),
      })
    ) as unknown as typeof fetch;
    render(<DetailPanel name="carry_btc_eth" />);
    await waitFor(() => expect(screen.getByText("Operational / data bugs")).toBeInTheDocument());
    expect(screen.getByText(/trailing 7d funding/)).toBeInTheDocument();
  });
});
