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
// `compileOk`/`linkOk` let a test simulate a context that exists but rejects the
// shader (compile/link failure), which must fall back rather than throw.
function mockWebGL2Context({ compileOk = true, linkOk = true } = {}) {
  return {
    createShader: vi.fn(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    getShaderParameter: vi.fn(() => compileOk),
    getShaderInfoLog: vi.fn(() => "mock shader compile error"),
    deleteShader: vi.fn(),
    createProgram: vi.fn(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    getProgramParameter: vi.fn(() => linkOk),
    getProgramInfoLog: vi.fn(() => "mock program link error"),
    deleteProgram: vi.fn(),
    useProgram: vi.fn(),
    getUniformLocation: vi.fn(() => ({})),
    uniform1f: vi.fn(),
    uniform1i: vi.fn(),
    uniform2f: vi.fn(),
    uniform2fv: vi.fn(),
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

  it("redraws the static frame after a window resize under prefers-reduced-motion", () => {
    mockMatchMedia(true);
    const gl = mockWebGL2Context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl);
    render(<LiquidMetalField />);

    const drawArrays = gl.drawArrays as unknown as ReturnType<typeof vi.fn>;
    const callsAtMount = drawArrays.mock.calls.length;
    expect(callsAtMount).toBeGreaterThan(0);

    window.dispatchEvent(new Event("resize"));

    // canvas.width/height assignment inside resize() clears the drawing
    // buffer; the reduced-motion path must redraw so the frame persists
    // instead of going blank.
    expect(drawArrays.mock.calls.length).toBeGreaterThan(callsAtMount);
  });

  it("falls back instead of crashing when WebGL2 shader compile/link fails", () => {
    mockMatchMedia(false);
    // Context exists (getContext returns non-null), but getShaderParameter /
    // getProgramParameter report failure -- compileShader/createProgram throw
    // in this case, and the effect must catch that and fall back rather than
    // white-screen the app.
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      mockWebGL2Context({ compileOk: false, linkOk: true }),
    );

    let container: HTMLElement;
    expect(() => {
      ({ container } = render(<LiquidMetalField />));
    }).not.toThrow();

    expect(container!.querySelector(".liquid-metal-fallback")).not.toBeNull();
    expect(container!.querySelector("canvas")).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
  });

  it("throttles pointermove to at most one ripple sample per animation frame", () => {
    mockMatchMedia(false);
    const gl = mockWebGL2Context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl);

    // Capture the loop callback instead of letting rAF auto-invoke, so the
    // test can control exactly when "one frame" elapses relative to however
    // many pointermove events fire in between.
    let rafCallback: FrameRequestCallback | null = null;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      rafCallback = cb;
      return 1;
    });

    render(<LiquidMetalField />);
    expect(rafCallback).not.toBeNull();

    // Draws are now throttled to TARGET_FPS (30, i.e. ~33.3ms apart) -- space these
    // synthetic timestamps well past that interval so each call actually draws
    // instead of being skipped as "too soon since the last draw".
    const FRAME_GAP_MS = 40;

    // Consume the initial frame queued at mount so the buffer below reflects
    // only the pointermove events fired after this point.
    rafCallback!(0);

    const uniform1i = gl.uniform1i as unknown as ReturnType<typeof vi.fn>;
    uniform1i.mockClear();

    // Fire many raw pointermove events -- far more than one -- before the
    // next animation frame is allowed to run.
    for (let i = 0; i < 20; i++) {
      window.dispatchEvent(new MouseEvent("pointermove", { clientX: 100 + i, clientY: 50 }));
    }

    // Still zero frames consumed since the events: no ripple should have
    // reached the GPU-bound uniform yet.
    expect(uniform1i).not.toHaveBeenCalled();

    // Now let exactly one animation frame run.
    rafCallback!(FRAME_GAP_MS);

    // u_rippleCount (set via uniform1i) must reflect exactly one new ripple
    // added for this frame, not 20 -- proving the 20 raw events collapsed to
    // a single sample consumed once per frame, matching the ripple buffer's
    // starting-empty state (0 -> 1), not (0 -> 20 then clamped).
    expect(uniform1i).toHaveBeenCalledTimes(1);
    expect(uniform1i).toHaveBeenCalledWith(expect.anything(), 1);
  });

  it("skips the draw call when the next frame arrives before the FPS-throttle interval", () => {
    mockMatchMedia(false);
    const gl = mockWebGL2Context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl);

    let rafCallback: FrameRequestCallback | null = null;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      rafCallback = cb;
      return 1;
    });

    render(<LiquidMetalField />);
    rafCallback!(0); // initial draw, establishes lastDrawMs = 0

    const drawArrays = gl.drawArrays as unknown as ReturnType<typeof vi.fn>;
    const callsAfterFirstDraw = drawArrays.mock.calls.length;
    expect(callsAfterFirstDraw).toBeGreaterThan(0);

    rafCallback!(5); // 5ms later -- well under the ~33.3ms (30fps) interval
    expect(drawArrays.mock.calls.length).toBe(callsAfterFirstDraw);

    rafCallback!(40); // 40ms after the last draw -- past the interval, must draw
    expect(drawArrays.mock.calls.length).toBeGreaterThan(callsAfterFirstDraw);
  });

  it("stops drawing while the document is hidden and resumes when it's visible again", () => {
    mockMatchMedia(false);
    const gl = mockWebGL2Context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl);
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});

    render(<LiquidMetalField />);
    const callsAtMount = rafSpy.mock.calls.length;

    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(cancelSpy).toHaveBeenCalled();

    const cancelCallsWhenHidden = cancelSpy.mock.calls.length;
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    document.dispatchEvent(new Event("visibilitychange"));

    // Resuming schedules a new frame without cancelling again.
    expect(rafSpy.mock.calls.length).toBeGreaterThan(callsAtMount);
    expect(cancelSpy.mock.calls.length).toBe(cancelCallsWhenHidden);
  });

  it("caps the canvas resolution to 1x device pixel ratio even on a HiDPI display", () => {
    mockMatchMedia(false);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockWebGL2Context());
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 3 });

    const { container } = render(<LiquidMetalField />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    expect(canvas.width).toBe(window.innerWidth);
    expect(canvas.height).toBe(window.innerHeight);
  });
});
