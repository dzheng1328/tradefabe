import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatTile from "./StatTile";

describe("StatTile", () => {
  it("renders a label and value with the depth/border-glow treatment", () => {
    const { container } = render(<StatTile label="Sharpe" value="0.80" />);
    expect(screen.getByText("Sharpe")).toBeInTheDocument();
    expect(screen.getByText("0.80")).toBeInTheDocument();
    expect(container.querySelector(".tf-stat-tile")).not.toBeNull();
  });
});
