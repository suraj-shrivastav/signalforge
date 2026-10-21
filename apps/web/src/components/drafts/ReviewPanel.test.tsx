// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReviewPanel } from "./ReviewPanel";
import type { EditorDraft } from "@/lib/api";

const FLAG = {
  section: 0,
  paragraph: 0,
  text: "Bad one.",
  kind: "uncited" as const,
  detail: "uncited sentence",
};

const draft: EditorDraft = {
  card_id: "00000000-0000-0000-0000-000000000001",
  status: "drafted",
  template: "explainer",
  review_summary: "",
  failure_reason: null,
  review_status: "pending",
  review_note: "",
  published_slug: null,
  draft: {
    title: "T",
    dek: "D",
    sections: [{ heading: "H", paragraphs: ["Good. Bad one."] }],
    claims: [],
    sources: [],
    cover: { src: null, alt: "a", credit: null },
    flags: [FLAG],
  },
};

function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn(async () => Response.json(body, { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReviewPanel", () => {
  it("blocks approval while a flag is unresolved", () => {
    render(<ReviewPanel draft={draft} editorKey="k" onUpdated={() => {}} />);
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("deletes a flagged sentence through the sentence action", async () => {
    const updated = { ...draft, draft: { ...draft.draft!, flags: [] } };
    const fetchMock = respondWith(updated);
    const onUpdated = vi.fn();
    render(<ReviewPanel draft={draft} editorKey="k" onUpdated={onUpdated} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await vi.waitFor(() => expect(onUpdated).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe(`/api/editor/drafts/${draft.card_id}/sentence`);
    expect(JSON.parse(init.body as string)).toEqual({
      section: 0,
      paragraph: 0,
      text: "Bad one.",
      replacement: null,
    });
  });

  it("shows the server's reason when a decision is refused", async () => {
    respondWith(
      {
        error: {
          code: "conflict",
          message: "Resolve every flagged sentence first",
        },
      },
      409,
    );
    render(<ReviewPanel draft={draft} editorKey="k" onUpdated={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Request revision" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("offers Publish only for an approved, unpublished draft", () => {
    const approved = { ...draft, review_status: "approved" as const };
    const { rerender } = render(
      <ReviewPanel draft={approved} editorKey="k" onUpdated={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Publish" })).toBeEnabled();
    rerender(
      <ReviewPanel
        draft={{ ...approved, published_slug: "my-article" }}
        editorKey="k"
        onUpdated={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(
      screen.getByRole("link", { name: "/articles/my-article" }),
    ).toBeInTheDocument();
  });

  it("unpublishes a published article through the proxy and refreshes", async () => {
    const calls: string[] = [];
    const onUpdated = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(url);
        return url.endsWith("/unpublish")
          ? Response.json({ slug: "my-article", status: "unpublished" })
          : Response.json({ ...draft, review_status: "approved" });
      }),
    );
    render(
      <ReviewPanel
        draft={{
          ...draft,
          review_status: "approved",
          published_slug: "my-article",
        }}
        editorKey="k"
        onUpdated={onUpdated}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Unpublish" }));
    await vi.waitFor(() => expect(onUpdated).toHaveBeenCalled());
    expect(calls[0]).toBe("/api/editor/articles/my-article/unpublish");
  });

  it("hides the controls once the draft is decided", () => {
    render(
      <ReviewPanel
        draft={{ ...draft, review_status: "approved" }}
        editorKey="k"
        onUpdated={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.getByText(/Status: approved/)).toBeInTheDocument();
  });
});
