// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { PublicTable } from "@/lib/public";
import { ArticleTable } from "./ArticleTable";

afterEach(cleanup);

const table: PublicTable = {
  caption: "Word error rate",
  header: ["Model", "WER", "RTFx"],
  rows: [
    ["Granite", "5.06", "280"],
    ["Whisper", "7.40", "145"],
  ],
  source: { label: "IBM model card", url: "https://huggingface.co/ibm" },
};

describe("ArticleTable", () => {
  it("renders a real table with caption, column headers and row headers", () => {
    render(<ArticleTable table={table} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("Word error rate").tagName).toBe("CAPTION");
    const columns = screen.getAllByRole("columnheader");
    expect(columns.map((c) => c.textContent)).toEqual(["Model", "WER", "RTFx"]);
    expect(columns.every((c) => c.getAttribute("scope") === "col")).toBe(true);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);
    const rowHeader = within(rows[1]).getByRole("rowheader");
    expect(rowHeader.textContent).toBe("Granite");
    expect(rowHeader.getAttribute("scope")).toBe("row");
    expect(
      within(rows[2])
        .getAllByRole("cell")
        .map((c) => c.textContent),
    ).toEqual(["7.40", "145"]);
  });

  it("scrolls sideways instead of widening the page", () => {
    const { container } = render(<ArticleTable table={table} />);
    const wrapper = container.querySelector("table")?.parentElement;
    expect(wrapper?.className).toContain("overflow-x-auto");
  });

  it("names the source with a safe link", () => {
    render(<ArticleTable table={table} />);
    const link = screen.getByRole("link", { name: "IBM model card" });
    expect(link.getAttribute("href")).toBe("https://huggingface.co/ibm");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("shows an unsafe source as plain text, not a link", () => {
    render(
      <ArticleTable
        table={{
          ...table,
          source: { label: "Bad", url: "javascript:alert(1)" },
        }}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/Bad/)).toBeTruthy();
  });

  it("renders cell text as text, never as markup", () => {
    const { container } = render(
      <ArticleTable
        table={{
          ...table,
          rows: [
            ["<b>bold</b>", "1", "2"],
            ["x", "<script>1</script>", "3"],
          ],
        }}
      />,
    );
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("<b>bold</b>")).toBeTruthy();
  });

  it("omits the caption and the source line when there are none", () => {
    const { container } = render(
      <ArticleTable table={{ ...table, caption: "", source: null }} />,
    );
    expect(container.querySelector("caption")).toBeNull();
    expect(container.querySelector("figcaption")).toBeNull();
  });
});
