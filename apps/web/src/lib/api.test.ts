import { describe, expect, it } from "vitest";
import { parseSignalList } from "./api";
import { formatScore } from "./format";

const item = {
  id: "0b9c0f6e-0000-4000-8000-000000000001",
  source: "hackernews",
  source_type: "community",
  canonical_url: "https://example.com/a",
  title: "A title",
  published_at: "2026-09-24T10:00:00Z",
  summary: "",
  metadata: { points: 50 },
};

describe("parseSignalList", () => {
  it("accepts a well-formed response", () => {
    const list = parseSignalList({ items: [item], next_cursor: null });
    expect(list.items[0].title).toBe("A title");
    expect(list.next_cursor).toBeNull();
  });

  it("rejects a response with the wrong shape", () => {
    expect(() =>
      parseSignalList({ items: [{ ...item, title: 5 }], next_cursor: null }),
    ).toThrow();
    expect(() => parseSignalList({ next_cursor: null })).toThrow();
    expect(() => parseSignalList("nope")).toThrow();
  });
});

const assessment = {
  is_relevant: true,
  relevance_score: 0.83,
  category: "tooling",
  summary: "A summary",
  why_it_matters: "A reason",
};

describe("assessment parsing", () => {
  it("accepts signals with and without an assessment", () => {
    const list = parseSignalList({
      items: [item, { ...item, assessment }],
      next_cursor: null,
    });
    expect(list.items[0].assessment).toBeUndefined();
    expect(list.items[1].assessment?.category).toBe("tooling");
  });

  it("treats a null assessment as absent", () => {
    const list = parseSignalList({
      items: [{ ...item, assessment: null }],
      next_cursor: null,
    });
    expect(list.items[0].assessment).toBeUndefined();
  });

  it("rejects a malformed assessment", () => {
    expect(() =>
      parseSignalList({
        items: [
          { ...item, assessment: { ...assessment, relevance_score: "x" } },
        ],
        next_cursor: null,
      }),
    ).toThrow();
    expect(() =>
      parseSignalList({
        items: [{ ...item, assessment: "nope" }],
        next_cursor: null,
      }),
    ).toThrow();
  });
});

describe("formatScore", () => {
  it("formats a fraction as a percentage", () => {
    expect(formatScore(0.83)).toBe("83%");
    expect(formatScore(1)).toBe("100%");
  });
});
