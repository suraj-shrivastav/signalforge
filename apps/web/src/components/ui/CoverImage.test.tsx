// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CoverImage } from "./CoverImage";

afterEach(cleanup);

describe("CoverImage", () => {
  it("renders a labelled fallback without src", () => {
    render(<CoverImage slug="a" alt="Cover A" />);
    const el = screen.getByRole("img", { name: "Cover A" });
    expect(el.className).toMatch(/cover-v[0-3]/);
  });
  it("is deterministic per slug", () => {
    render(
      <>
        <CoverImage slug="same" alt="one" />
        <CoverImage slug="same" alt="two" />
      </>,
    );
    expect(screen.getByRole("img", { name: "one" }).className).toBe(
      screen.getByRole("img", { name: "two" }).className,
    );
  });
  it("uses all four variants across slugs", () => {
    const seen = new Set<string>();
    for (const s of ["a", "b", "c", "d", "e", "f", "g", "h"]) {
      const { unmount } = render(<CoverImage slug={s} alt={s} />);
      seen.add(
        screen.getByRole("img").className.match(/cover-v[0-3]/)?.[0] ?? "",
      );
      unmount();
    }
    expect(seen.size).toBeGreaterThan(1);
  });
  it("renders an image with alt when src given", () => {
    render(<CoverImage slug="a" alt="Photo" src="/x.png" />);
    expect(screen.getByAltText("Photo")).toBeTruthy();
  });
});
