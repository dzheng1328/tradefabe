import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Diagnostics from "./Diagnostics";

const LUCK_FLOOR_RESPONSE = { chart: { data: [], layout: {} }, label: "Daily-rebalanced — carry_btc_eth" };
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
});
