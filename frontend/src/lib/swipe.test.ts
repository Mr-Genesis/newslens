import { describe, it, expect } from "vitest";
import { swipeThresholds } from "./swipe";

describe("swipe thresholds (#104)", () => {
  it("commits horizontally at 40% width, vertically at 25% height", () => {
    expect(swipeThresholds(400, 800)).toEqual({ x: 160, y: -200 });
  });

  it("scales with orientation (wide landscape → larger x, smaller y)", () => {
    expect(swipeThresholds(1000, 400)).toEqual({ x: 400, y: -100 });
  });

  it("clamps non-positive dimensions to 0", () => {
    expect(swipeThresholds(0, -50)).toEqual({ x: 0, y: -0 });
  });
});
