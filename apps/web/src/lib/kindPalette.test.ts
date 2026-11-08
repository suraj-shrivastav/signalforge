import { describe, expect, it } from "vitest";
import { contrastRatio } from "./contrast";
import { KIND_PALETTE, heroText, kindPalette } from "./kindPalette";
import { parseSummary } from "./public";

describe("kindPalette", () => {
  it("returns the design table values", () => {
    expect(kindPalette("paper")).toEqual({ bg: "#dccdef", fg: "#14201a" });
    expect(kindPalette("benchmark")).toEqual({ bg: "#f6e0a4", fg: "#14201a" });
    expect(kindPalette("model")).toEqual({ bg: "#f4c9cc", fg: "#14201a" });
    expect(kindPalette("release")).toEqual({ bg: "#c3d5ef", fg: "#14201a" });
    expect(kindPalette("tool")).toEqual({ bg: "#bfe0d2", fg: "#14201a" });
    expect(kindPalette("discussion")).toEqual({ bg: "#f1e4d3", fg: "#14201a" });
    expect(kindPalette("news")).toEqual({ bg: "#e8eee4", fg: "#14201a" });
  });
  it("uses the none row for null and unknown kinds", () => {
    const none = { bg: "#e8eee4", fg: "#14201a" };
    expect(kindPalette(null)).toEqual(none);
    expect(kindPalette("bogus")).toEqual(none);
    expect(kindPalette("toString")).toEqual(none);
  });
  it.each(Object.entries(KIND_PALETTE))(
    "%s contrast is at least 4.5",
    (_k, p) => {
      expect(contrastRatio(p.fg, p.bg)).toBeGreaterThanOrEqual(4.5);
    },
  );
});

describe("heroText", () => {
  it("prefers the headline value", () => {
    expect(heroText("t", { value: "24%" })).toBe("24%");
  });
  it("uses the text before a colon when 2 to 24 characters", () => {
    expect(heroText("Qwen3: a new model family", null)).toBe("Qwen3");
  });
  it("else the first 3 words without leading filler", () => {
    expect(heroText("How agents learn to plan ahead", null)).toBe(
      "agents learn to",
    );
  });
});

const base = {
  slug: "s",
  title: "t",
  dek: "d",
  meta_description: "m",
  published_at: "p",
  modified_at: "q",
  cover: { src: null, alt: "a", credit: null },
};

describe("parseSummary new fields", () => {
  it("tolerates absence on old articles", () => {
    const s = parseSummary(base);
    expect(s.kind).toBeNull();
    expect(s.source_label).toBe("");
    expect(s.headline).toBeNull();
  });
  it("parses and drops unknown fields", () => {
    const s = parseSummary({
      ...base,
      kind: "paper",
      source_label: "arXiv",
      headline: {
        value: "24%",
        unit: "fewer errors",
        direction: "down",
        takeaway: "x",
        claim_index: 3,
      },
    });
    expect(s.kind).toBe("paper");
    expect(s.source_label).toBe("arXiv");
    expect(s.headline).toEqual({
      value: "24%",
      unit: "fewer errors",
      direction: "down",
      takeaway: "x",
    });
  });
  it("rejects a headline whose value is not a string", () => {
    const s = parseSummary({
      ...base,
      headline: { value: 24, unit: "u", direction: "up", takeaway: "t" },
    });
    expect(s.headline).toBeNull();
  });
  it("coerces a bad direction to none", () => {
    const s = parseSummary({
      ...base,
      headline: {
        value: "2x",
        unit: "u",
        direction: "sideways",
        takeaway: "t",
      },
    });
    expect(s.headline?.direction).toBe("none");
  });
});
