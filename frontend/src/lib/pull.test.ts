import { describe, it, expect } from "vitest";
import { pullOffset, pullTriggersRefresh, PULL_THRESHOLD } from "./pull";

describe("pull resistance (#99)", () => {
  it("applies the 0.4 rubber-band factor", () => {
    expect(pullOffset(100)).toBe(40);
    expect(pullOffset(50)).toBe(20);
  });

  it("caps the offset at 80", () => {
    expect(pullOffset(200)).toBe(80); // 200*0.4 = 80 exactly
    expect(pullOffset(250)).toBe(80);
    expect(pullOffset(10000)).toBe(80);
  });

  it("clamps a non-positive pull to 0", () => {
    expect(pullOffset(0)).toBe(0);
    expect(pullOffset(-40)).toBe(0);
  });

  it("triggers refresh only at/above the 60px threshold offset", () => {
    expect(PULL_THRESHOLD).toBe(60);
    expect(pullTriggersRefresh(pullOffset(150))).toBe(true); // 150*0.4 = 60
    expect(pullTriggersRefresh(pullOffset(149))).toBe(false); // 59.6 < 60
    expect(pullTriggersRefresh(pullOffset(100))).toBe(false); // 40 < 60
  });
});
