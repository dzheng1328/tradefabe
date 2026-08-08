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
  live_equity_chart: { data: [], layout: {} },
  backtest_chart: { data: [], layout: {} },
  divergence_state: "ok",
  divergence_detail: "Live is tracking backtest within the expected band.",
  verdict: "ALIVE",
  corr_bench: 0.1,
  null_p95: 0.4,
  freq: "D",
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
  it("renders the blurb and stats once loaded", async () => {
    render(<DetailPanel name="tsmom_12m" />);
    await waitFor(() =>
      expect(screen.getByText(/trailing 12-month return/)).toBeInTheDocument()
    );
    expect(screen.getByText("0.80")).toBeInTheDocument(); // Sharpe
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
});
