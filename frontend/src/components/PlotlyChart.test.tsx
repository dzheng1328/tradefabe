import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlotlyChart from "./PlotlyChart";

describe("PlotlyChart", () => {
  it("renders nothing (no throw) when figure is undefined", () => {
    const { container } = render(<PlotlyChart figure={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a plot when figure has data", () => {
    const { container } = render(
      <PlotlyChart figure={{ data: [{ x: [1, 2], y: [3, 4], type: "scatter" }], layout: {} }} />
    );
    expect(container).not.toBeEmptyDOMElement();
  });
});
