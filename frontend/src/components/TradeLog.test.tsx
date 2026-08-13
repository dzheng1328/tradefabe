import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TradeLog from "./TradeLog";

const TRADES = [
  {
    ts: "2026-08-12T14:30:00", ticker: "SPY", side: "BUY", shares: 5.2,
    price: 450.2, notional: 2341.04, position_after: 12.5,
  },
];

describe("TradeLog", () => {
  it("renders one row per fill", () => {
    render(<TradeLog trades={TRADES} accrualOnly={false} costBps={5} />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(screen.getByText(/1 fill/)).toBeInTheDocument();
  });

  it("shows the accrual-only caption instead of an empty-log message", () => {
    render(<TradeLog trades={[]} accrualOnly={true} costBps={null} />);
    expect(screen.getByText(/delta-neutral carry/)).toBeInTheDocument();
  });

  it("shows the not-yet-filled caption for a non-accrual book with no trades", () => {
    render(<TradeLog trades={[]} accrualOnly={false} costBps={5} />);
    expect(screen.getByText(/No fills recorded yet/)).toBeInTheDocument();
  });
});
