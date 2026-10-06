// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ArticlePreview } from "./ArticlePreview";
import type { EditorDraft } from "@/lib/api";

const draft: EditorDraft = {
  card_id: "00000000-0000-0000-0000-000000000001",
  status: "drafted",
  template: "paper_breakdown",
  review_summary: "Single source. Claim 1 (supported): Second claim",
  draft: {
    title: "A smaller model matches a larger one",
    dek: "What the paper reports.",
    sections: [
      { heading: "The problem", paragraphs: ["First paragraph."] },
      { heading: "The approach", paragraphs: ["Second paragraph."] },
    ],
    claims: [
      {
        text: "First claim",
        evidence_span: "span one",
        document_indices: [0],
        status: "verified",
      },
      {
        text: "Second claim",
        evidence_span: "span two",
        document_indices: [1],
        status: "unverified",
      },
    ],
    sources: [
      { label: "arxiv.org", url: "https://arxiv.org/abs/1" },
      { label: "unsafe", url: "javascript:alert(1)" },
    ],
    cover: { src: null, alt: "Chart", credit: null },
  },
};

describe("ArticlePreview", () => {
  it("renders the template name, title and every section heading", () => {
    render(<ArticlePreview draft={draft} />);
    expect(screen.getByText("Paper breakdown")).toBeInTheDocument();
    expect(screen.getByText(draft.draft!.title)).toBeInTheDocument();
    for (const section of draft.draft!.sections) {
      expect(screen.getByText(section.heading)).toBeInTheDocument();
    }
  });

  it("marks each claim with its status and links its source by index", () => {
    render(<ArticlePreview draft={draft} />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.dataset.status)).toEqual([
      "verified",
      "unverified",
    ]);
    expect(screen.getByRole("link", { name: "arxiv.org" })).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/1",
    );
    expect(screen.queryByRole("link", { name: "unsafe" })).toBeNull();
  });

  it("shows the review summary", () => {
    render(<ArticlePreview draft={draft} />);
    expect(screen.getByLabelText("Review summary")).toHaveTextContent(
      "Single source.",
    );
  });

  it("says when a failed draft has no body", () => {
    render(
      <ArticlePreview draft={{ ...draft, status: "failed", draft: null }} />,
    );
    expect(screen.getByText("Drafting failed.")).toBeInTheDocument();
  });
});

afterEach(cleanup);
