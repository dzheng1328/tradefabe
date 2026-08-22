import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BrandGlyph from "./BrandGlyph";

describe("BrandGlyph", () => {
  it("renders the twin-corsage bloom mark from the shared favicon source", () => {
    const { container } = render(<BrandGlyph />);
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("src", "/favicon.svg");
  });

  it("is decorative -- hidden from assistive tech since it sits next to the wordmark text", () => {
    const { container } = render(<BrandGlyph />);
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("alt", "");
    expect(img).toHaveAttribute("aria-hidden", "true");
  });

  it("forwards a className so call sites control size and color", () => {
    const { container } = render(<BrandGlyph className="w-4 h-4 text-accent" />);
    expect(container.querySelector("img")).toHaveClass("w-4", "h-4", "text-accent");
  });
});
