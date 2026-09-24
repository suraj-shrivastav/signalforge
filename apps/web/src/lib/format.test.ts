import { describe, expect, it } from "vitest";
import { formatRelative, hostOf, safeHref } from "./format";

const now = new Date("2026-09-24T12:00:00Z");

describe("formatRelative", () => {
  it("uses minutes, hours and days", () => {
    expect(formatRelative(now, "2026-09-24T11:59:30Z")).toBe("just now");
    expect(formatRelative(now, "2026-09-24T11:15:00Z")).toBe("45m ago");
    expect(formatRelative(now, "2026-09-24T07:00:00Z")).toBe("5h ago");
    expect(formatRelative(now, "2026-09-21T12:00:00Z")).toBe("3d ago");
  });
});

describe("hostOf", () => {
  it("strips www and falls back to the input", () => {
    expect(hostOf("https://www.example.com/a")).toBe("example.com");
    expect(hostOf("not a url")).toBe("not a url");
  });
});

describe("safeHref", () => {
  it("allows only http and https", () => {
    expect(safeHref("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("nope")).toBeNull();
  });
});
