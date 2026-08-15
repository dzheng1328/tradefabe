import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import GrowthValuesPanel from "./GrowthValuesPanel";

const ROWS = [
  { name: "tsmom_12m", value: 1.126, color: "#2a78d6" },
  { name: "turn_of_month_gen_7_2", value: 1.051, color: "#1baf7a" },
  { name: "60/40", value: 2.046, color: "#7d8877" },
];

describe("GrowthValuesPanel", () => {
  it("shows a placeholder before anything is clicked", () => {
    render(<GrowthValuesPanel date={null} rows={null} />);
    expect(screen.getByText(/click a point on the chart/i)).toBeInTheDocument();
  });

  it("renders every row sorted by value descending once populated", () => {
    render(<GrowthValuesPanel date="2026-08-14" rows={ROWS} />);
    expect(screen.getByText(/values at 2026-08-14/i)).toBeInTheDocument();
    const names = screen.getAllByText(/tsmom_12m|turn_of_month_gen_7_2|60\/40/).map((el) => el.textContent);
    expect(names).toEqual(["60/40", "tsmom_12m", "turn_of_month_gen_7_2"]);
  });

  it("filters rows by the search box", async () => {
    render(<GrowthValuesPanel date="2026-08-14" rows={ROWS} />);
    await userEvent.type(screen.getByPlaceholderText(/search/i), "tsmom");
    expect(screen.getByText("tsmom_12m")).toBeInTheDocument();
    expect(screen.queryByText("60/40")).not.toBeInTheDocument();
    expect(screen.queryByText("turn_of_month_gen_7_2")).not.toBeInTheDocument();
  });

  it("shows a no-match message when the search filters out everything", async () => {
    render(<GrowthValuesPanel date="2026-08-14" rows={ROWS} />);
    await userEvent.type(screen.getByPlaceholderText(/search/i), "nonexistent_strategy");
    expect(screen.getByText(/no match/i)).toBeInTheDocument();
  });

  it("disables the search box until rows are populated", () => {
    render(<GrowthValuesPanel date={null} rows={null} />);
    expect(screen.getByPlaceholderText(/search/i)).toBeDisabled();
  });
});
