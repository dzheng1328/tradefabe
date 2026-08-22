import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Intro from "./Intro";

const STORAGE_KEY = "tradefabe.intro.shown";

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

vi.mock("../lib/sound", () => ({ playIntroSettle: vi.fn() }));

beforeEach(() => {
  sessionStorage.clear();
  mockMatchMedia(false);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Intro", () => {
  it("shows the overlay on first mount this session", () => {
    render(<Intro />);
    expect(document.querySelector(".intro-overlay")).not.toBeNull();
  });

  it("does not show again once sessionStorage records it was already shown", () => {
    sessionStorage.setItem(STORAGE_KEY, "1");
    render(<Intro />);
    expect(document.querySelector(".intro-overlay")).toBeNull();
  });

  it("skips straight to the settled end-state under prefers-reduced-motion", () => {
    mockMatchMedia(true);
    render(<Intro />);
    expect(document.querySelector(".intro-overlay")).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("1");
  });

  it("adds the settling class once the hold phase ends, before it unmounts", async () => {
    render(<Intro />);
    expect(document.querySelector(".intro-overlay--settling")).toBeNull();
    await act(async () => {
      // bloomStart(950) + bloomGrow(1500) + hold(1100) = 3550ms
      vi.advanceTimersByTime(3550);
    });
    expect(document.querySelector(".intro-overlay--settling")).not.toBeNull();
  });

  it("removes itself, marks the session, and plays the settle sting once the sequence completes", async () => {
    const { playIntroSettle } = await import("../lib/sound");
    render(<Intro />);
    await act(async () => {
      // bloomStart(950) + bloomGrow(1500) + hold(1100) + fade(650) = 4200ms
      vi.advanceTimersByTime(4200);
    });
    expect(document.querySelector(".intro-overlay")).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("1");
    expect(playIntroSettle).toHaveBeenCalledTimes(1);
  });
});
