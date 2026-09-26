import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkTokens } from "./check-tokens.mjs";

type Violation = { file: string; line: number; rule: string };

function makeTree(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "tokens-"));
  mkdirSync(join(dir, "src"), { recursive: true });
  for (const [name, body] of Object.entries(files)) {
    writeFileSync(join(dir, "src", name), body);
  }
  return dir;
}

describe("checkTokens", () => {
  it("reports each violation with file and line", () => {
    const dir = makeTree({
      "bad.tsx": [
        'export const A = () => <div className="bg-[#fff]" />;',
        'export const B = () => <div className="w-[13px]" />;',
        'export const C = () => <div style={{ color: "#123456" }} />;',
        'export const D = "#141414";',
      ].join("\n"),
    });
    const found: Violation[] = checkTokens(dir);
    const lines = found.map((v) => v.line);
    for (const n of [1, 2, 3, 4]) expect(lines).toContain(n);
    expect(found.every((v) => v.file.endsWith("bad.tsx") && v.rule)).toBe(true);
  });

  it("passes a clean component", () => {
    const dir = makeTree({
      "ok.tsx": 'export const A = () => <div className="bg-page p-4" />;\n',
    });
    expect(checkTokens(dir)).toEqual([]);
  });

  it("exempts globals.css", () => {
    const dir = makeTree({ "globals.css": ":root { --ink: #141414; }\n" });
    expect(checkTokens(dir)).toEqual([]);
  });
});
