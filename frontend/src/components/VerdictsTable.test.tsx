import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import VerdictsTable from "./VerdictsTable";

const VERDICTS_RESPONSE = {
  rows: [
    { strategy: "carry_btc_eth", freq: "D", oos_sharpe: 1.14, oos_sortino: 1.5,
      oos_calmar: 2.1, oos_maxdd: -0.062, corr_bench: 0.1, null_p95: 0.65, verdict: "ALIVE" },
    { strategy: "tsmom_gen_382d", freq: "M", oos_sharpe: 0.59, oos_sortino: 0.78,
      oos_calmar: 0.25, oos_maxdd: -0.113, corr_bench: 0.39, null_p95: 0.65, verdict: "DEAD" },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(VERDICTS_RESPONSE) })
  ) as unknown as typeof fetch;
});

describe("VerdictsTable", () => {
  it("renders one row per strategy with a colored verdict", async () => {
    render(<VerdictsTable onSelect={() => {}} />);
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    expect(screen.getByText("ALIVE")).toBeInTheDocument();
    expect(screen.getByText("DEAD")).toBeInTheDocument();
  });

  it("calls onSelect with the strategy name when a row is clicked", async () => {
    const onSelect = vi.fn();
    render(<VerdictsTable onSelect={onSelect} />);
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    await userEvent.click(screen.getByText("carry_btc_eth"));
    expect(onSelect).toHaveBeenCalledWith("carry_btc_eth");
  });

  it("shows an error message instead of crashing when the fetch fails", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: "boom" }) })
    ) as unknown as typeof fetch;

    render(<VerdictsTable onSelect={() => {}} />);
    await waitFor(() => expect(screen.getByText(/couldn't load/i)).toBeInTheDocument());
  });
});
