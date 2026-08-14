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
    // Not-yet-activated tabs aren't mounted at all.
    expect(screen.queryByText("Verdicts content")).not.toBeInTheDocument();
  });

  it("lazily mounts a tab's content on first activation", async () => {
    render(<ResearchLab />);
    expect(screen.queryByText("Verdicts content")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verdicts" }));
    expect(screen.getByText("Verdicts content")).toBeInTheDocument();
  });

  it("hides (but does not unmount) a previously-activated tab when switching away", async () => {
    render(<ResearchLab />);
    await userEvent.click(screen.getByRole("button", { name: "Verdicts" }));
    expect(screen.getByText("Verdicts content")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(screen.getByText("Overview content")).toBeInTheDocument();
    // Verdicts stays mounted (fetch cache preserved), just hidden via CSS.
    const verdicts = screen.getByText("Verdicts content");
    expect(verdicts).toBeInTheDocument();
    expect(verdicts.parentElement).toHaveStyle({ display: "none" });
  });

  it("does not refire a tab's fetch on a second activation", async () => {
    vi.doUnmock("./VerdictsTable");
    vi.resetModules();
    const { default: FreshResearchLab } = await import("./ResearchLab");

    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("verdicts")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ rows: [] }) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            meta: { source: "cache", start: "2020", end: "2026", oos_start: "2018", n_assets: 1 },
            stats: { n_tested: 1, n_alive: 1, n_dead: 0, luck_floor_p95: null, best_strategy: "x", best_sharpe: null, bench_sharpe: null },
            strategies: [],
            growth_chart: { data: [], layout: {} },
            correlation_heatmap: { data: [], layout: {} },
          }),
      });
    }) as unknown as typeof fetch;

    render(<FreshResearchLab />);
    await userEvent.click(screen.getByRole("button", { name: "Verdicts" }));
    await userEvent.click(screen.getByRole("button", { name: "Overview" }));
    await userEvent.click(screen.getByRole("button", { name: "Verdicts" }));

    const verdictsCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([url]: [string]) => url.includes("verdicts")
    );
    expect(verdictsCalls.length).toBe(1);
  });
});
