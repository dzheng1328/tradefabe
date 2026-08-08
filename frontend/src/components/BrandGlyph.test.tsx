import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BrandGlyph from "./BrandGlyph";

describe("BrandGlyph", () => {
  it("renders a crossed-square mark: one square outline and two diagonals", () => {
    const { container } = render(<BrandGlyph />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.querySelectorAll("rect")).toHaveLength(1);
    expect(svg?.querySelectorAll("line")).toHaveLength(2);
  });

  it("is decorative -- hidden from assistive tech since it sits next to the wordmark text", () => {
    const { container } = render(<BrandGlyph />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("forwards a className so call sites control size and color", () => {
    const { container } = render(<BrandGlyph className="w-4 h-4 text-accent" />);
    expect(container.querySelector("svg")).toHaveClass("w-4", "h-4", "text-accent");
  });
});
