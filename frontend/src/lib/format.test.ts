import { describe, expect, it } from "vitest";
import { fmt, money, pct } from "./format";

describe("fmt", () => {
  it("formats a ratio to two decimals", () => {
    expect(fmt(0.8)).toBe("0.80");
  });
  it("formats a percent to one decimal", () => {
    expect(fmt(-0.12, "pct")).toBe("-12.0%");
  });
  it("renders an em dash for null/undefined", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(undefined)).toBe("—");
  });
});

describe("money", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(money(103241)).toBe("$103,241");
  });
  it("renders an em dash for null, never $NaN or $-0", () => {
    expect(money(null)).toBe("—");
  });
  it("prefixes the sign before the dollar sign for negative values", () => {
    expect(money(-500)).toBe("-$500");
  });
});

describe("pct", () => {
  it("formats a fraction as a signed percent", () => {
    expect(pct(0.0875)).toBe("+8.8%");
    expect(pct(-0.05)).toBe("-5.0%");
  });
  it("renders an em dash for null", () => {
    expect(pct(null)).toBe("—");
  });
});
