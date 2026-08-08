import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RowList from "./RowList";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const FAMILY_RESPONSE = {
  families: [
    {
      family: "A", label: "Trend",
      books: [
        { book: "tsmom_12m", equity: 103241, return: 0.032, last_run: "2026-08-06",
          retired_at: null, family: "A", color: "#2a78d6", introduced: "2026-01-01",
          return_today: 0.012, monitor_only: false, sparkline: [100000, 100500, 101000] },
      ],
    },
    {
      family: "D", label: "Carry",
      books: [
        { book: "carry_btc_eth", equity: 112003, return: 0.12, last_run: "2026-08-06",
          retired_at: null, family: "D", color: "#1baf7a", introduced: "2025-05-01",
          return_today: 0.001, monitor_only: false, sparkline: [110000, 111500, 112003] },
      ],
    },
  ],
};

const UP_FOR_REVIEW_RESPONSE = { books: [] };

function mockFetchSequence() {
  return vi.fn((url: string) => {
    if (url.includes("up_for_review")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(FAMILY_RESPONSE) });
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  globalThis.fetch = mockFetchSequence();
  navigateMock.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

vi.mock("../lib/sound", () => ({ playSelect: vi.fn() }));

describe("RowList", () => {
  it("renders family-grouped rows by default", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText("carry_btc_eth")).toBeInTheDocument();
    expect(screen.getByText("Trend")).toBeInTheDocument();
  });

  it("refetches with the flat sort when a non-Family option is chosen", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const select = screen.getByLabelText(/sort by/i);
    await userEvent.selectOptions(select, "Total return");
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("sort=total_return"))).toBe(true);
    });
  });

  it("refetches with show_monitor_only=false when the checkbox is unchecked", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const checkbox = screen.getByLabelText(/show monitor-only/i);
    await userEvent.click(checkbox);
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
      expect(calls.some((u) => String(u).includes("show_monitor_only=false"))).toBe(true);
    });
  });

  it("redirects to a still-visible book when the selected one is filtered out", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("up_for_review")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
      }
      // tsmom_12m (the currently-selected book) is absent -- as if it was just
      // filtered out by unchecking "Show monitor-only".
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            families: [
              {
                family: "D", label: "Carry",
                books: [
                  { book: "carry_btc_eth", equity: 112003, return: 0.12, last_run: "2026-08-06",
                    retired_at: null, family: "D", color: "#1baf7a", introduced: "2025-05-01",
                    return_today: 0.001, monitor_only: false, sparkline: [110000, 111500, 112003] },
                ],
              },
            ],
          }),
      });
    }) as unknown as typeof fetch;

    render(
      <MemoryRouter>
        <RowList selectedName="tsmom_12m" />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    expect(navigateMock).toHaveBeenCalledWith("/books/carry_btc_eth", { replace: true });
  });

  it("plays the select sound when a row is clicked", async () => {
    const { playSelect } = await import("../lib/sound");
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    await userEvent.click(screen.getByText("tsmom_12m"));
    expect(playSelect).toHaveBeenCalled();
  });
});
