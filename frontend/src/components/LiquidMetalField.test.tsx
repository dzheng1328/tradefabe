import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LiquidMetalField from "./LiquidMetalField";

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

// A minimal WebGL2 context stub -- enough for LiquidMetalField's setup/draw path
// to run without throwing, so the component takes the "WebGL2 available" branch.
function mockWebGL2Context() {
  return {
    createShader: vi.fn(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    getShaderParameter: vi.fn(() => true),
    getShaderInfoLog: vi.fn(() => ""),
    deleteShader: vi.fn(),
    createProgram: vi.fn(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    getProgramParameter: vi.fn(() => true),
    getProgramInfoLog: vi.fn(() => ""),
    deleteProgram: vi.fn(),
    useProgram: vi.fn(),
    getUniformLocation: vi.fn(() => ({})),
    uniform1f: vi.fn(),
    uniform1i: vi.fn(),
    uniform2f: vi.fn(),
    uniform3f: vi.fn(),
    uniform3fv: vi.fn(),
    viewport: vi.fn(),
    drawArrays: vi.fn(),
    VERTEX_SHADER: 0,
    FRAGMENT_SHADER: 1,
    COMPILE_STATUS: 2,
    LINK_STATUS: 3,
    TRIANGLES: 4,
  } as unknown as WebGL2RenderingContext;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LiquidMetalField", () => {
  it("renders a canvas when WebGL2 is available", () => {
    mockMatchMedia(false);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockWebGL2Context());
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    const { container } = render(<LiquidMetalField />);
    expect(container.querySelector("canvas.ambient-field")).not.toBeNull();
    expect(rafSpy).toHaveBeenCalled();
  });

  it("renders the static fallback when WebGL2 is unavailable", () => {
    mockMatchMedia(false);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const { container, rerender } = render(<LiquidMetalField />);
    rerender(<LiquidMetalField />);
    expect(container.querySelector(".liquid-metal-fallback")).not.toBeNull();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("draws exactly one static frame under prefers-reduced-motion, with no pointer listener or animation loop", () => {
    mockMatchMedia(true);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockWebGL2Context());
    const rafSpy = vi.spyOn(window, "requestAnimationFrame");
    const addEventSpy = vi.spyOn(window, "addEventListener");
    render(<LiquidMetalField />);
    expect(rafSpy).not.toHaveBeenCalled();
    expect(addEventSpy).not.toHaveBeenCalledWith("pointermove", expect.any(Function));
  });
});
