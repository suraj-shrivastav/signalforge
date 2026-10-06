// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Header } from "@/components/layout/Header";
import { metadata } from "@/app/editor/layout";
import PublicLayout from "@/app/(public)/layout";
import { GET } from "@/app/(public)/feed.xml/route";

const src = join(__dirname, "..", "..");
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

describe("public sources", () => {
  const all = [
    ...files(join(src, "app/(public)")),
    ...files(join(src, "components/layout")),
  ].filter((f) => /\.(ts|tsx)$/.test(f) && !f.endsWith(".test.tsx"));
  it("scans real files", () => expect(all.length).toBeGreaterThan(5));
  it.each(all)("%s has no forbidden terms", (f) => {
    expect(readFileSync(f, "utf8")).not.toMatch(
      /model|\bAI\b|AI-generated|written by AI|author(ship)?|generated|\bLLM\b|\bGPT\b|prompt_version/i,
    );
  });
  // Article drafts carry editor-only fields; public code must never read them.
  it.each(all)("%s reads no editor-only draft fields", (f) => {
    expect(readFileSync(f, "utf8")).not.toMatch(
      /review_?summary|evidence_?span|cost_?usd|editor\/drafts|\btemplate\b/i,
    );
  });
});

describe("Header", () => {
  it("toggles the mobile menu", async () => {
    render(<Header />);
    const btn = screen.getByRole("button", { name: "Open menu" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(btn).toHaveAttribute("aria-controls", "site-nav");
    await userEvent.click(btn);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("link", { name: "Search" })).toBeInTheDocument();
  });
});

describe("public layout", () => {
  it("puts the skip link first in tab order", async () => {
    render(<PublicLayout>x</PublicLayout>);
    await userEvent.tab();
    expect(screen.getByText("Skip to content")).toHaveFocus();
  });
});

describe("feed.xml", () => {
  it("returns an Atom feed", async () => {
    const res = GET();
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("application/atom+xml");
    const doc = new DOMParser().parseFromString(
      await res.text(),
      "application/xml",
    );
    expect(doc.getElementsByTagName("parsererror")).toHaveLength(0);
  });
});

describe("editor metadata", () => {
  it("is noindex", () => {
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });
});

afterEach(cleanup);
