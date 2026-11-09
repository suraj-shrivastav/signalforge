import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { contrastRatio, readTokens } from "./contrast";
import { KIND_PALETTE } from "./kindPalette";

const css = readFileSync(
  join(process.cwd(), "src", "app", "globals.css"),
  "utf8",
);
const tokens = readTokens(css);

const PAIRS: [string, string][] = [
  ["ink", "page-bg"],
  ["ink", "surface-bg"],
  ["muted", "page-bg"],
  ["muted", "surface-bg"],
  ["on-accent", "accent"],
];

describe("contrastRatio", () => {
  it("is 21 for black on white", () => {
    expect(contrastRatio("#" + "000000", "#" + "ffffff")).toBeCloseTo(21, 5);
  });
  it("is symmetric", () => {
    expect(contrastRatio("#" + "336699", "#" + "ffffff")).toBeCloseTo(
      contrastRatio("#" + "ffffff", "#" + "336699"),
      10,
    );
  });
});

describe("readTokens", () => {
  it("reads both themes", () => {
    expect(Object.keys(tokens.light)).toContain("ink");
    expect(tokens.dark["page-bg"]).not.toBe(tokens.light["page-bg"]);
  });
});

describe.each(["light", "dark"] as const)("%s theme contrast", (theme) => {
  it.each(PAIRS)("%s on %s is at least 4.5", (fg, bg) => {
    const t = tokens[theme];
    expect(t[fg], `${fg} missing`).toBeDefined();
    expect(t[bg], `${bg} missing`).toBeDefined();
    expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
  });
});

describe("kind palette contrast", () => {
  it.each(Object.entries(KIND_PALETTE))("%s is at least 4.5", (_kind, p) => {
    expect(contrastRatio(p.fg, p.bg)).toBeGreaterThanOrEqual(4.5);
  });
});
