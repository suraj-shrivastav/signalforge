import { describe, expect, it } from "vitest";
import { decisionElapsedMs } from "./decisionTiming";

describe("decisionElapsedMs", () => {
  it("measures elapsed time", () => {
    expect(decisionElapsedMs(5_000, 2_000)).toBe(3_000);
  });
  it("clamps negative and huge values", () => {
    expect(decisionElapsedMs(1_000, 2_000)).toBe(0);
    expect(decisionElapsedMs(10_000_000, 0)).toBe(3_600_000);
  });
  it("measures sequential cards from the previous decision", () => {
    const mount = 0;
    const first = decisionElapsedMs(10_000, mount);
    const second = decisionElapsedMs(25_000, 10_000);
    expect([first, second]).toEqual([10_000, 15_000]);
  });
});
