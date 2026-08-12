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
  localStorage.clear();
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

  it("shows each book's introduced date, formatted m.d.yy to match the Streamlit dashboard", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(screen.getByText("1.1.26")).toBeInTheDocument();
    expect(screen.getByText("5.1.25")).toBeInTheDocument();
  });

  it("draws a per-family underline under each family header", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".family-underline")).toHaveLength(2);
  });

  it("gives rows a hover-lift treatment", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const row = container.querySelector(".tf-row");
    expect(row?.className).toMatch(/hover:-translate-y-px/);
  });

  function mockFetchWithReview(reviewBooks: unknown[]) {
    return vi.fn((url: string) => {
      if (url.includes("up_for_review")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ books: reviewBooks }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(FAMILY_RESPONSE) });
    }) as unknown as typeof fetch;
  }

  const REVIEW_BOOKS = [{ book: "tsmom_12m", days_live: 40, verdict: "DEAD" }, { book: "carry_btc_eth", days_live: 90, verdict: "ALIVE" }];

  it("does not pulse the up-for-review badge on a first-ever visit (nothing to compare)", async () => {
    localStorage.clear();
    globalThis.fetch = mockFetchWithReview(REVIEW_BOOKS);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Up for review/)).toBeInTheDocument());
    expect(container.querySelector(".review-badge-pulse")).toBeNull();
  });

  it("pulses the up-for-review badge when the count changed since the last visit", async () => {
    localStorage.setItem("tradefabe.reviewCount", "0");
    globalThis.fetch = mockFetchWithReview(REVIEW_BOOKS);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Up for review/)).toBeInTheDocument());
    expect(container.querySelector(".review-badge-pulse")).not.toBeNull();
  });

  it("does not pulse the up-for-review badge when the count matches the last visit", async () => {
    localStorage.setItem("tradefabe.reviewCount", String(REVIEW_BOOKS.length));
    globalThis.fetch = mockFetchWithReview(REVIEW_BOOKS);
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Up for review/)).toBeInTheDocument());
    expect(container.querySelector(".review-badge-pulse")).toBeNull();
  });

  it("re-renders rows in the server's new order after a sort switch, for FLIP to animate", async () => {
    let sort = "family";
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("up_for_review")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(UP_FOR_REVIEW_RESPONSE) });
      }
      sort = new URL(url).searchParams.get("sort") ?? sort;
      const books =
        sort === "total_return"
          ? [FAMILY_RESPONSE.families[1].books[0], FAMILY_RESPONSE.families[0].books[0]]
          : [FAMILY_RESPONSE.families[0].books[0], FAMILY_RESPONSE.families[1].books[0]];
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ books }) });
    }) as unknown as typeof fetch;

    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const namesBefore = [...container.querySelectorAll("[data-book]")].map((el) => el.getAttribute("data-book"));
    expect(namesBefore).toEqual(["tsmom_12m", "carry_btc_eth"]);

    await userEvent.selectOptions(screen.getByLabelText(/sort by/i), "Total return");
    await waitFor(() => {
      const namesAfter = [...container.querySelectorAll("[data-book]")].map((el) => el.getAttribute("data-book"));
      expect(namesAfter).toEqual(["carry_btc_eth", "tsmom_12m"]);
    });
  });

  it("gives carry_btc_eth a featured chip, the one strategy cleared by doctrine", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("carry_btc_eth")).toBeInTheDocument());
    const carryRow = screen.getByText("carry_btc_eth").closest(".tf-row");
    expect(carryRow?.querySelector(".tf-featured-chip")).not.toBeNull();
    const tsmomRow = screen.getByText("tsmom_12m").closest(".tf-row");
    expect(tsmomRow?.querySelector(".tf-featured-chip")).toBeNull();
  });

  it("shows ghost skeleton rows while loading, not a plain Loading… flash", async () => {
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    expect(container.querySelectorAll(".tf-skeleton-row").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".tf-skeleton-row")).toHaveLength(0);
  });

  it("marks the sparkline's last point with an end-dot", async () => {
    render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    const row = screen.getByText("tsmom_12m").closest(".tf-row");
    expect(row?.querySelector("svg circle")).not.toBeNull();
  });

  it("bursts a book that has never been seen before, tracked via localStorage", async () => {
    localStorage.clear();
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".tf-book-burst")).toHaveLength(2);
  });

  it("does not burst a book already recorded as seen in localStorage", async () => {
    localStorage.setItem("tradefabe.seenBooks", JSON.stringify(["tsmom_12m", "carry_btc_eth"]));
    const { container } = render(
      <MemoryRouter>
        <RowList selectedName={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("tsmom_12m")).toBeInTheDocument());
    expect(container.querySelectorAll(".tf-book-burst")).toHaveLength(0);
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
