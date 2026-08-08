import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Nav from "./Nav";
import { isSoundEnabled, setSoundEnabled } from "../lib/sound";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Nav", () => {
  it("shows the brand glyph next to the tradefabe wordmark", () => {
    const { container } = render(<Nav />);
    expect(screen.getByText("tradefabe")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("toggles the persisted sound setting when clicked", async () => {
    render(<Nav />);
    expect(screen.getByText("Sound: on")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Sound: on"));
    expect(screen.getByText("Sound: off")).toBeInTheDocument();
    expect(isSoundEnabled()).toBe(false);
  });

  it("pulses the sound toggle when a sound plays, then stops after the pulse duration", async () => {
    vi.useFakeTimers();
    setSoundEnabled(true);
    render(<Nav />);
    const toggle = screen.getByText("Sound: on");
    expect(toggle.className).not.toMatch(/sound-toggle-pulse/);

    // Simulate a real play call notifying listeners (Nav subscribed on mount).
    const { playSelect } = await import("../lib/sound");
    act(() => {
      playSelect();
    });
    expect(toggle.className).toMatch(/sound-toggle-pulse/);

    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(toggle.className).not.toMatch(/sound-toggle-pulse/);
  });

  it("stops listening for sound events after unmount", async () => {
    vi.useFakeTimers();
    setSoundEnabled(true);
    const { unmount } = render(<Nav />);
    unmount();
    const { playSelect } = await import("../lib/sound");
    // Must not throw from a setState call on an unmounted component.
    expect(() => playSelect()).not.toThrow();
  });
});
