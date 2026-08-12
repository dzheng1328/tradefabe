import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ParticleField from "./ParticleField";

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

describe("ParticleField", () => {
  it("renders a single canvas hidden from assistive tech", () => {
    mockMatchMedia(false);
    const { container } = render(<ParticleField />);
    const canvases = container.querySelectorAll("canvas");
    expect(canvases).toHaveLength(1);
    expect(canvases[0]).toHaveAttribute("aria-hidden", "true");
  });

  it("starts a continuous animation loop when motion is not reduced", () => {
    mockMatchMedia(false);
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    render(<ParticleField />);
    expect(rafSpy).toHaveBeenCalled();
  });

  it("renders one static frame under prefers-reduced-motion, never starting a loop", () => {
    mockMatchMedia(true);
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    render(<ParticleField />);
    expect(rafSpy).not.toHaveBeenCalled();
  });

  it("cancels the animation frame on unmount", () => {
    mockMatchMedia(false);
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(42);
    const cafSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const { unmount } = render(<ParticleField />);
    unmount();
    expect(cafSpy).toHaveBeenCalledWith(42);
  });
});
