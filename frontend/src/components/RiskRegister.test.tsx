import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import RiskRegister from "./RiskRegister";

const ENTRIES = [
  {
    key: "venue_failure", title: "Venue failure", category: "total loss",
    likelihood: "45% of 40 exchanges failed.", impact: "Total loss of posted margin.",
    detail: "Two independent samples agree.", source: "Moore & Christin (FC 2013)",
    url: "https://example.com/paper", measured: false,
  },
  {
    key: "operational", title: "Operational / data bugs", category: "operational",
    likelihood: "Several realised, all caught.", impact: "Wrong or stale numbers.",
    detail: "Realised examples in CLAUDE.md.", source: null, url: null, measured: true,
  },
];

describe("RiskRegister", () => {
  it("renders one collapsed entry per row, titles visible", () => {
    render(<RiskRegister entries={ENTRIES} />);
    expect(screen.getByText("Venue failure")).toBeInTheDocument();
    expect(screen.getByText("Operational / data bugs")).toBeInTheDocument();
    // jsdom has no UA stylesheet hiding non-open <details> content (unlike a real
    // browser), so presence-in-DOM can't signal collapsed state here -- assert the
    // native `open` attribute directly instead, which is what collapse actually is.
    expect(screen.getByText("Venue failure").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Operational / data bugs").closest("details")).not.toHaveAttribute("open");
  });

  it("reveals likelihood/impact/detail when an entry is opened", async () => {
    render(<RiskRegister entries={ENTRIES} />);
    await userEvent.click(screen.getByText("Venue failure"));
    const details = screen.getByText("Venue failure").closest("details") as HTMLElement;
    expect(details).toHaveAttribute("open");
    expect(within(details).getByText(/Two independent samples/)).toBeInTheDocument();
    expect(within(details).getByText(/45% of 40 exchanges/)).toBeInTheDocument();
  });

  it("shows a cited badge with a source link when a source is present", async () => {
    render(<RiskRegister entries={ENTRIES} />);
    await userEvent.click(screen.getByText("Venue failure"));
    const details = screen.getByText("Venue failure").closest("details") as HTMLElement;
    expect(within(details).getByText("cited")).toBeInTheDocument();
    expect(within(details).getByRole("link", { name: /Moore & Christin/ })).toHaveAttribute(
      "href", "https://example.com/paper"
    );
  });

  it("shows a measured badge and no source link when source is null", async () => {
    render(<RiskRegister entries={ENTRIES} />);
    await userEvent.click(screen.getByText("Operational / data bugs"));
    // Scoped to this entry's own <details> -- the OTHER (still-closed) entry's link is
    // still present elsewhere in the DOM for the same jsdom-hiding reason noted above,
    // so an unscoped queryByRole("link") would see it and give a false pass/fail here.
    const details = screen.getByText("Operational / data bugs").closest("details") as HTMLElement;
    expect(within(details).getByText("measured")).toBeInTheDocument();
    expect(within(details).queryByRole("link")).not.toBeInTheDocument();
  });
});
