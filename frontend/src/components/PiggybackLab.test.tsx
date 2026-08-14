// frontend/src/components/PiggybackLab.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PiggybackLab from "./PiggybackLab";

const OVERVIEW_RESPONSE = {
  meta: { source: "cache", start: "2007-01-03", end: "2026-08-13", oos_start: "2018-01-01", n_assets: 15 },
  stats: { n_tested: 2, n_alive: 1, n_dead: 1, luck_floor_p95: 0.65, best_strategy: "tsmom_12m", best_sharpe: 0.51, bench_sharpe: 0.58 },
  strategies: ["tsmom_12m", "xsec_momentum"],
  growth_chart: { data: [], layout: {} },
  correlation_heatmap: { data: [], layout: {} },
};

const PIGGYBACK_RESPONSE = {
  stats: { sharpe: 0.6, sharpe_delta: 0.02, calmar: 0.3, calmar_delta: 0.05, maxdd: -0.08, maxdd_delta: -0.01 },
  chart: { data: [], layout: {} },
};

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    if (url.includes("piggyback")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(PIGGYBACK_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) });
  }) as unknown as typeof fetch;
});

describe("PiggybackLab", () => {
  it("fetches the sleeve simulation once strategies are known and a sleeve is selected", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/0\.02/)).toBeInTheDocument(), { timeout: 1000 });
  });

  it("lets the user toggle a sleeve strategy off", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const checkbox = screen.getByLabelText("xsec_momentum");
    await userEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it("shows an error message instead of crashing when the strategy list fetch fails", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: "boom" }) })
    ) as unknown as typeof fetch;

    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText(/couldn't load the strategy list/i)).toBeInTheDocument());
  });

  it("shows an error message instead of crashing when the piggyback simulation fetch fails", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("piggyback")) {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: "boom" }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) });
    }) as unknown as typeof fetch;

    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText(/couldn't simulate this sleeve/i)).toBeInTheDocument());
  });
});
