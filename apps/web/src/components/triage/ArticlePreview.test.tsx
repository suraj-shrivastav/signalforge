// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ArticlePreview } from "./ArticlePreview";
import { mockArticle } from "@/lib/mock/article";

describe("ArticlePreview", () => {
  it("renders the sample caption, title and every section heading", () => {
    render(<ArticlePreview article={mockArticle} />);
    expect(screen.getByText(/preview draft/i)).toBeInTheDocument();
    expect(screen.getByText(mockArticle.title)).toBeInTheDocument();
    for (const section of mockArticle.sections) {
      expect(screen.getByText(section.heading)).toBeInTheDocument();
    }
  });

  it("links every claim to its source", () => {
    render(<ArticlePreview article={mockArticle} />);
    for (const claim of mockArticle.claims) {
      expect(
        screen.getByRole("link", { name: claim.sourceLabel }),
      ).toHaveAttribute("href", claim.sourceUrl);
    }
  });

  it("contains no em dash or en dash", () => {
    const text = document.body.textContent ?? "";
    render(<ArticlePreview article={mockArticle} />);
    expect(document.body.textContent).not.toMatch(/[—–]/);
  });
});
