import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ResearchLab from "./ResearchLab";

vi.mock("./ResearchOverview", () => ({ default: () => <div>Overview content</div> }));
vi.mock("./VerdictsTable", () => ({ default: () => <div>Verdicts content</div> }));
vi.mock("./StrategyDetail", () => ({ default: () => <div>Detail content</div> }));
vi.mock("./Diagnostics", () => ({ default: () => <div>Diagnostics content</div> }));
vi.mock("./PiggybackLab", () => ({ default: () => <div>Piggyback content</div> }));

describe("ResearchLab", () => {
  it("shows the Overview tab by default and not the others", () => {
    render(<ResearchLab />);
    expect(screen.getByText("Overview content")).toBeInTheDocument();
    expect(screen.queryByText("Verdicts content")).not.toBeInTheDocument();
  });

  it("mounts only the clicked tab's content", async () => {
    render(<ResearchLab />);
    await userEvent.click(screen.getByRole("button", { name: "Verdicts" }));
    expect(screen.getByText("Verdicts content")).toBeInTheDocument();
    expect(screen.queryByText("Overview content")).not.toBeInTheDocument();
  });
});
