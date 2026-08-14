import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Diagnostics from "./Diagnostics";

const LUCK_FLOOR_RESPONSE = {
  chart: { data: [], layout: {} },
  label: "Daily-rebalanced — carry_btc_eth",
  shape: "per_strategy",
};
const LUCK_FLOOR_PER_FREQUENCY_RESPONSE = {
  chart: { data: [], layout: {} },
  label: "Daily-rebalanced",
  shape: "per_frequency",
};
const DRAWDOWN_RESPONSE = { chart: { data: [], layout: {} }, max_drawdown: -0.062 };

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    if (url.includes("luck_floor")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LUCK_FLOOR_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(DRAWDOWN_RESPONSE) });
  }) as unknown as typeof fetch;
});

describe("Diagnostics", () => {
  it("shows an empty state with nothing selected", () => {
    render(<Diagnostics selected={null} />);
    expect(screen.getByText(/pick a strategy/i)).toBeInTheDocument();
  });

  it("fetches luck floor and drawdown for the selected strategy", async () => {
    render(<Diagnostics selected="carry_btc_eth" />);
    await waitFor(() => expect(screen.getByText(/Daily-rebalanced/)).toBeInTheDocument());
    expect(screen.getByText(/-6.2%/)).toBeInTheDocument();
  });

  it("shows the per-strategy caption when shape is per_strategy", async () => {
    render(<Diagnostics selected="carry_btc_eth" />);
    await waitFor(() =>
      expect(screen.getByText(/random rotations of this strategy's own signal/i)).toBeInTheDocument()
    );
  });

  it("shows the per-frequency caption when shape is per_frequency", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("luck_floor")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(LUCK_FLOOR_PER_FREQUENCY_RESPONSE) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(DRAWDOWN_RESPONSE) });
    }) as unknown as typeof fetch;

    render(<Diagnostics selected="carry_kronos_vol" />);
    await waitFor(() =>
      expect(screen.getByText(/shared distribution across all/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/random rotations of this strategy's own signal/i)).not.toBeInTheDocument();
  });

  it("shows an unavailable message when luck floor 400s (e.g. hourly-family strategies with no null distribution)", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("luck_floor")) {
        return Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ detail: "no distribution" }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(DRAWDOWN_RESPONSE) });
    }) as unknown as typeof fetch;

    render(<Diagnostics selected="funding_timing_1h" />);
    await waitFor(() =>
      expect(screen.getByText(/no luck-floor distribution available/i)).toBeInTheDocument()
    );
  });

  it("shows an unavailable message when drawdown 400s (e.g. kronos-family strategies with no full_returns column)", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("drawdown")) {
        return Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ detail: "no backtest curve" }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LUCK_FLOOR_RESPONSE) });
    }) as unknown as typeof fetch;

    render(<Diagnostics selected="carry_kronos_vol" />);
    await waitFor(() =>
      expect(screen.getByText(/no backtest curve available/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/NaN%/)).not.toBeInTheDocument();
  });
});
