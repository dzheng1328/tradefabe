import { beforeEach, describe, expect, it } from "vitest";
import { isSoundEnabled, setSoundEnabled } from "./sound";

describe("sound mute toggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to enabled", () => {
    expect(isSoundEnabled()).toBe(true);
  });

  it("persists a mute choice across calls", () => {
    setSoundEnabled(false);
    expect(isSoundEnabled()).toBe(false);
    setSoundEnabled(true);
    expect(isSoundEnabled()).toBe(true);
  });
});
