import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchQueue, parseSignalList, postDecision } from "./api";
import { formatScore } from "./format";

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

const assessment = {
  is_relevant: true,
  relevance_score: 0.83,
  category: "tooling",
  summary: "A summary",
  why_it_matters: "A reason",
};

describe("assessment parsing", () => {
  it("accepts signals with and without an assessment", () => {
    const list = parseSignalList({
      items: [item, { ...item, assessment }],
      next_cursor: null,
    });
    expect(list.items[0].assessment).toBeUndefined();
    expect(list.items[1].assessment?.category).toBe("tooling");
  });

  it("treats a null assessment as absent", () => {
    const list = parseSignalList({
      items: [{ ...item, assessment: null }],
      next_cursor: null,
    });
    expect(list.items[0].assessment).toBeUndefined();
  });

  it("rejects a malformed assessment", () => {
    expect(() =>
      parseSignalList({
        items: [
          { ...item, assessment: { ...assessment, relevance_score: "x" } },
        ],
        next_cursor: null,
      }),
    ).toThrow();
    expect(() =>
      parseSignalList({
        items: [{ ...item, assessment: "nope" }],
        next_cursor: null,
      }),
    ).toThrow();
  });
});

describe("formatScore", () => {
  it("formats a fraction as a percentage", () => {
    expect(formatScore(0.83)).toBe("83%");
    expect(formatScore(1)).toBe("100%");
  });
});

const card = {
  id: "0b9c0f6e-0000-4000-8000-000000000001",
  what_happened: "<script>alert(1)</script>",
  why_it_matters: "w",
  novelty: 0.5,
  signal_strength: 0.5,
  coverage_gap: "g",
  suggested_angle: "a",
  format: "explainer",
  evergreen_score: 0.4,
  confidence: 0.9,
  risk_flags: [],
  signal: { id: "s1", title: "T", source: "hn", canonical_url: "https://x.io" },
  score: 0.7,
  wildcard: false,
  status: "proposed",
  created_at: "2026-09-27T10:00:00Z",
};
const decision = {
  decision: "accepted" as const,
  reason_tags: [],
  note: "",
  decision_ms: 10,
};
const ID = card.id;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function stubFetch(res: Response | Error) {
  const fn = vi.fn(async () => {
    if (res instanceof Error) throw res;
    return res;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("fetchQueue", () => {
  it("parses a valid response", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    stubFetch(Response.json([card]));
    const cards = await fetchQueue();
    expect(cards[0].what_happened).toBe("<script>alert(1)</script>");
  });

  it("rejects a malformed card", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    stubFetch(Response.json([{ ...card, novelty: "x" }]));
    await expect(fetchQueue()).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError with status and code on the standard error body", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    stubFetch(
      Response.json(
        {
          error: {
            code: "internal_error",
            message: "boom",
            correlation_id: "c",
          },
        },
        { status: 500 },
      ),
    );
    await expect(fetchQueue()).rejects.toMatchObject({
      status: 500,
      code: "internal_error",
    });
  });

  it("throws ApiError when the error body is not JSON", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    stubFetch(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(fetchQueue()).rejects.toMatchObject({ status: 502 });
  });
});

describe("postDecision", () => {
  it("sends the key header and JSON body to the same-origin route", async () => {
    const fn = stubFetch(Response.json({}, { status: 201 }));
    await postDecision(ID, decision, "k");
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`/api/cards/${ID}/decision`);
    expect(new Headers(init.headers).get("x-editor-key")).toBe("k");
    expect(JSON.parse(init.body as string)).toEqual(decision);
  });

  it("throws on 401", async () => {
    stubFetch(
      Response.json(
        { error: { code: "unauthorized", message: "no", correlation_id: "c" } },
        { status: 401 },
      ),
    );
    await expect(postDecision(ID, decision, "bad")).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });
  });
});
