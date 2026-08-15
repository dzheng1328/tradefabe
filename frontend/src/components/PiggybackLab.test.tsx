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

const RECOMMEND_RESPONSE = {
  recommendations: [
    { strategy: "tsmom_12m", resulting_sharpe: 0.51, resulting_calmar: 0.3, delta_sharpe: 0.1 },
    { strategy: "xsec_momentum", resulting_sharpe: 0.4, resulting_calmar: 0.2, delta_sharpe: 0.05 },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    if (url.includes("piggyback/recommend")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(RECOMMEND_RESPONSE) });
    }
    if (url.includes("piggyback")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(PIGGYBACK_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) });
  }) as unknown as typeof fetch;
});

describe("PiggybackLab", () => {
  it("starts with an empty sleeve and shows a recommended-to-start list", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("Recommended to start with")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText(/pick one from the recommended list/i)).toBeInTheDocument();
  });

  it("adds a strategy from the recommended list and simulates the sleeve", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await userEvent.click(screen.getByText("tsmom_12m"));
    await waitFor(() => expect(screen.getByText(/0\.02/)).toBeInTheDocument(), { timeout: 1000 });
    expect(screen.getByText("Recommended next")).toBeInTheDocument();
  });

  it("adds a strategy via the search bar", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByLabelText("Add a strategy")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Add a strategy"), "xsec");
    const match = await screen.findByRole("button", { name: "xsec_momentum" });
    await userEvent.click(match);
    await waitFor(() => expect(screen.getByText(/xsec_momentum ×/)).toBeInTheDocument());
  });

  it("lets the user remove a sleeve strategy", async () => {
    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await userEvent.click(screen.getByText("tsmom_12m"));
    const chip = await screen.findByText(/tsmom_12m ×/);
    await userEvent.click(chip);
    await waitFor(() => expect(screen.queryByText(/tsmom_12m ×/)).not.toBeInTheDocument());
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
      if (url.includes("piggyback/recommend")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(RECOMMEND_RESPONSE) });
      }
      if (url.includes("piggyback")) {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: "boom" }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(OVERVIEW_RESPONSE) });
    }) as unknown as typeof fetch;

    render(<PiggybackLab />);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await userEvent.click(screen.getByText("tsmom_12m"));
    await waitFor(() => expect(screen.getByText(/couldn't simulate this sleeve/i)).toBeInTheDocument());
  });
});
