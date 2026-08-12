import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RingLoader from "./RingLoader";

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RingLoader", () => {
  it("renders a canvas element", () => {
    mockMatchMedia(false);
    const { container } = render(<RingLoader />);
    expect(container.querySelector("canvas.ring-loader")).not.toBeNull();
  });

  it("does not start a requestAnimationFrame loop under prefers-reduced-motion", () => {
    mockMatchMedia(true);
    const rafSpy = vi.spyOn(window, "requestAnimationFrame");
    render(<RingLoader />);
    expect(rafSpy).not.toHaveBeenCalled();
  });
});
