// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { applyTheme, readStoredTheme, resolveTheme } from "./theme";

describe("theme", () => {
  it("reads stored theme with system fallback", () => {
    expect(readStoredTheme({ getItem: () => "dark" })).toBe("dark");
    expect(readStoredTheme({ getItem: () => null })).toBe("system");
    expect(readStoredTheme({ getItem: () => "bogus" })).toBe("system");
    expect(
      readStoredTheme({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toBe("system");
  });

  it("resolves system by preference", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("applies and removes data-theme", () => {
    applyTheme(document, "dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    applyTheme(document, "system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
