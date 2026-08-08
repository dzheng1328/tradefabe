import { describe, expect, it } from "vitest";
import { applyDarkTheme } from "./plotlyDarkTheme";

describe("applyDarkTheme", () => {
  it("overrides the light-theme background and font colors", () => {
    const light = {
      paper_bgcolor: "#fcfcfb",
      plot_bgcolor: "#fcfcfb",
      font: { family: "IBM Plex Mono, monospace", size: 11, color: "#2b2a27" },
      xaxis: { gridcolor: "#e5e4e0" },
      yaxis: { gridcolor: "#e5e4e0" },
      height: 340,
    };
    const dark = applyDarkTheme(light);
    expect(dark.paper_bgcolor).toBe("#181c15");
    expect(dark.plot_bgcolor).toBe("#181c15");
    expect((dark.font as { color: string }).color).toBe("#7d8877");
    expect((dark.xaxis as { gridcolor: string }).gridcolor).not.toBe("#e5e4e0");
    expect((dark.yaxis as { gridcolor: string }).gridcolor).not.toBe("#e5e4e0");
  });

  it("preserves layout keys it doesn't own, like height", () => {
    const dark = applyDarkTheme({ height: 340, showlegend: false });
    expect(dark.height).toBe(340);
    expect(dark.showlegend).toBe(false);
  });
});
