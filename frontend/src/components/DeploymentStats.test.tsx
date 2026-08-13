import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DeploymentStats from "./DeploymentStats";

const DEPLOYMENT = {
  cash: 20000, gross: 90000, net: 80000, equity: 100000,
  cash_pct: 0.2, gross_pct: 0.9, net_pct: 0.8,
  n_unpriced: 0, n_held: 3, priced_at: "2026-08-12", is_short_funded: false,
};

describe("DeploymentStats", () => {
  it("renders the four capital-deployed figures", () => {
    render(<DeploymentStats deployment={DEPLOYMENT} />);
    expect(screen.getByText(/\$20,000/)).toBeInTheDocument(); // cash
    expect(screen.getByText(/\$90,000/)).toBeInTheDocument(); // gross
    expect(screen.getByText(/\$80,000/)).toBeInTheDocument(); // net
    expect(screen.getByText(/\$100,000/)).toBeInTheDocument(); // equity
  });

  it("shows the vol-targeting caption when not short-funded", () => {
    render(<DeploymentStats deployment={DEPLOYMENT} />);
    expect(screen.getByText(/Vol-targeted sizing/)).toBeInTheDocument();
  });

  it("shows the short-funded caption instead when is_short_funded is true", () => {
    render(<DeploymentStats deployment={{ ...DEPLOYMENT, is_short_funded: true, net: -10000 }} />);
    expect(screen.getByText(/net short/)).toBeInTheDocument();
    expect(screen.queryByText(/Vol-targeted sizing/)).not.toBeInTheDocument();
  });

  it("warns when some positions could not be priced", () => {
    render(<DeploymentStats deployment={{ ...DEPLOYMENT, n_unpriced: 2, n_held: 3 }} />);
    expect(screen.getByText(/2 of 3 held position/)).toBeInTheDocument();
  });

  it("does not warn when everything is priced", () => {
    render(<DeploymentStats deployment={DEPLOYMENT} />);
    expect(screen.queryByText(/could not be priced/)).not.toBeInTheDocument();
  });
});
