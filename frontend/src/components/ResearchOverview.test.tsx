import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ResearchOverview from "./ResearchOverview";

const OVERVIEW_RESPONSE = {
  meta: { source: "cache", start: "2007-01-03", end: "2026-08-13", oos_start: "2018-01-01", n_assets: 15 },
  stats: {
    n_tested: 477, n_alive: 4, n_dead: 473, luck_floor_p95: 0.65,
    best_strategy: "carry_btc_eth", best_sharpe: 1.14, bench_sharpe: 0.58,
  },
  strategies: ["tsmom_12m", "carry_btc_eth"],
  growth_chart: { data: [], layout: {} },
  correlation_heatmap: { data: [], layout: {} },
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) })
  ) as unknown as typeof fetch;
});

describe("ResearchOverview", () => {
  it("renders the eyebrow stats once data lands", async () => {
    render(<ResearchOverview />);
    await waitFor(() => expect(screen.getByText("477")).toBeInTheDocument());
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("473")).toBeInTheDocument();
  });

  it("shows an error message instead of crashing when the fetch fails", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: "boom" }) })
    ) as unknown as typeof fetch;

    render(<ResearchOverview />);
    await waitFor(() => expect(screen.getByText(/couldn't load/i)).toBeInTheDocument());
  });

  it("shows an error message when fetch itself rejects", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("network down"))) as unknown as typeof fetch;

    render(<ResearchOverview />);
    await waitFor(() => expect(screen.getByText(/couldn't load/i)).toBeInTheDocument());
  });
});
