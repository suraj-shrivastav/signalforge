// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DraftsBoard } from "./DraftsBoard";
import { parseDraftList } from "@/lib/api";

const ID = "00000000-0000-0000-0000-000000000001";
const SUMMARY = {
  card_id: ID,
  status: "needs_more_info",
  template: "explainer",
  title: "A draft title",
  signal_title: "Signal",
  claim_counts: { verified: 2, unverified: 1, bogus: 9 },
  created_at: "2026-10-03T00:00:00Z",
};
const DRAFT = {
  card_id: ID,
  status: "needs_more_info",
  template: "explainer",
  review_summary: "Publish gate: length",
  draft: {
    title: "A draft title",
    dek: "Dek",
    sections: [{ heading: "Section one", paragraphs: ["P"] }],
    claims: [],
    sources: [],
    cover: { src: null, alt: "Alt", credit: null },
  },
};

function stubFetch(byUrl: Record<string, Response>) {
  const fn = vi.fn((url: string) => Promise.resolve(byUrl[url].clone()));
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("parseDraftList", () => {
  it("keeps only known claim statuses", () => {
    expect(parseDraftList([SUMMARY])[0].claim_counts).toEqual({
      verified: 2,
      unverified: 1,
    });
  });
  it("rejects a non-list", () => {
    expect(() => parseDraftList({})).toThrow();
  });
});

describe("DraftsBoard", () => {
  it("loads the list with the key, then opens a draft", async () => {
    const fn = stubFetch({
      "/api/editor/drafts": Response.json([SUMMARY]),
      [`/api/editor/drafts/${ID}`]: Response.json(DRAFT),
    });
    render(<DraftsBoard />);
    const load = screen.getByRole("button", { name: "Load drafts" });
    expect(load).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Editor key"), "k");
    await userEvent.click(load);
    expect(
      await screen.findByText("needs more info · 2 verified, 1 unverified"),
    ).toBeInTheDocument();
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("x-editor-key")).toBe("k");
    await userEvent.click(
      screen.getByRole("button", { name: /A draft title/ }),
    );
    expect(await screen.findByText("Section one")).toBeInTheDocument();
    expect(screen.getByLabelText("Review summary")).toHaveTextContent(
      "Publish gate",
    );
  });

  it("explains an empty list and a bad key", async () => {
    stubFetch({ "/api/editor/drafts": Response.json([]) });
    render(<DraftsBoard />);
    await userEvent.type(screen.getByLabelText("Editor key"), "k");
    await userEvent.click(screen.getByRole("button", { name: "Load drafts" }));
    expect(await screen.findByText(/No drafts yet/)).toBeInTheDocument();
    cleanup();
    stubFetch({
      "/api/editor/drafts": Response.json(
        { error: { code: "unauthorized", message: "no" } },
        { status: 401 },
      ),
    });
    render(<DraftsBoard />);
    await userEvent.type(screen.getByLabelText("Editor key"), "bad");
    await userEvent.click(screen.getByRole("button", { name: "Load drafts" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter a valid editor key.",
    );
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
