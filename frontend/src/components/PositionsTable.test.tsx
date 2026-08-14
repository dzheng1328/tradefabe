import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PositionsTable from "./PositionsTable";

const POSITIONS = [
  { ticker: "SPY", units: 12.5, last_price: 450.2, value: 5627.5, weight: 0.056 },
  { ticker: "IEF", units: -8.0, last_price: 95.1, value: -760.8, weight: -0.008 },
];

describe("PositionsTable", () => {
  it("renders one row per position with ticker, units, price, value, weight", () => {
    render(<PositionsTable positions={POSITIONS} positionsAsof="2026-08-12" />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("IEF")).toBeInTheDocument();
    expect(screen.getByText("$5,628")).toBeInTheDocument();
  });

  it("shows an em dash for an unpriced position rather than $NaN", () => {
    render(
      <PositionsTable
        positions={[{ ticker: "XYZ", units: 5, last_price: null, value: 0, weight: 0 }]}
        positionsAsof="2026-08-12"
      />
    );
    // Check that "XYZ" is present and that "—" appears (for unpriced last_price)
    expect(screen.getByText("XYZ")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows an empty-state caption when there are no positions", () => {
    render(<PositionsTable positions={[]} positionsAsof="2026-08-12" />);
    expect(screen.getByText(/No open positions/)).toBeInTheDocument();
  });

  it("shows an empty-state caption when positions is null", () => {
    render(<PositionsTable positions={null} positionsAsof={null} />);
    expect(screen.getByText(/No open positions/)).toBeInTheDocument();
  });
});
