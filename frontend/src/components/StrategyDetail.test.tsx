import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StrategyDetail from "./StrategyDetail";

const STRATEGY_RESPONSE = {
  name: "carry_btc_eth", blurb: "Delta-neutral funding carry.", verdict: "ALIVE",
  freq: "D", corr_bench: 0.1, null_p95: 0.65, has_returns: true,
  stats: { Sharpe: 1.14, Sortino: 1.5, Calmar: 2.1, MaxDD: -0.062, CAGR: 0.12, Vol: 0.08 },
  chart: { data: [], layout: {} },
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(STRATEGY_RESPONSE) })
  ) as unknown as typeof fetch;
});

describe("StrategyDetail", () => {
  it("shows an empty state with nothing selected", () => {
    render(<StrategyDetail selected={null} />);
    expect(screen.getByText(/pick a strategy/i)).toBeInTheDocument();
  });

  it("renders blurb, verdict, and stats once a strategy is selected", async () => {
    render(<StrategyDetail selected="carry_btc_eth" />);
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    expect(screen.getByText("Delta-neutral funding carry.")).toBeInTheDocument();
    expect(screen.getByText("ALIVE")).toBeInTheDocument();
    expect(screen.getByText("1.14")).toBeInTheDocument();
  });

  it("shows an error message instead of crashing when the fetch fails", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: "unknown strategy" }) })
    ) as unknown as typeof fetch;

    render(<StrategyDetail selected="not_a_real_strategy" />);
    await waitFor(() => expect(screen.getByText(/couldn't load/i)).toBeInTheDocument());
  });
});
