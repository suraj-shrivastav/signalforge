import { describe, expect, it } from "vitest";
import { parseSignalList } from "./api";

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
