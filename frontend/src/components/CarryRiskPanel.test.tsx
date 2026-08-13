import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CarryRiskPanel from "./CarryRiskPanel";

const RISK = {
  generated_at: "2026-08-13T04:19:37", funding_window_days: 7,
  coins: {
    BTC: {
      funding_7d: 0.0011, funding_flip_alert: false, max_leverage: 40, maint_margin: 0.0125,
      postures: {
        "10%": { leverage: 4, liq_distance: 0.2375 },
        "25%": { leverage: 10, liq_distance: 0.0875 },
        "50%": { leverage: 20, liq_distance: 0.0375 },
        "100%": { leverage: 40, liq_distance: 0.0125 },
      },
    },
    ETH: {
      funding_7d: -0.0005, funding_flip_alert: true, max_leverage: 25, maint_margin: 0.02,
      postures: {
        "10%": { leverage: 2.5, liq_distance: 0.38 },
        "25%": { leverage: 6.25, liq_distance: 0.14 },
        "50%": { leverage: 12.5, liq_distance: 0.06 },
        "100%": { leverage: 25, liq_distance: 0.02 },
      },
    },
  },
  blended_funding_7d: 0.0003, blended_funding_flip_alert: false,
  headline_leverage_fraction: 0.25, liq_distance_warn: 0.25,
  high_risk_alert: { BTC: false, ETH: true },
};

describe("CarryRiskPanel", () => {
  it("shows an empty-state caption when risk is null", () => {
    render(<CarryRiskPanel risk={null} />);
    expect(screen.getByText(/No risk report yet/)).toBeInTheDocument();
  });

  it("renders both coins' 7d funding", () => {
    render(<CarryRiskPanel risk={RISK} />);
    expect(screen.getByText("+0.1%")).toBeInTheDocument(); // BTC
    expect(screen.getByText("-0.1%")).toBeInTheDocument(); // ETH, rounds to -0.1%
  });

  it("shows a funding-flip badge only for the coin that flipped", () => {
    render(<CarryRiskPanel risk={RISK} />);
    expect(screen.getAllByText("funding flip")).toHaveLength(1);
  });

  it("shows the high-risk warning naming only the flagged coin", () => {
    render(<CarryRiskPanel risk={RISK} />);
    const warning = screen.getByText(/High risk/);
    expect(warning.textContent).toMatch(/ETH/);
    expect(warning.textContent).not.toMatch(/BTC/);
  });
});
