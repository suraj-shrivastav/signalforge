import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchQueue, postDecision } from "./api";
import { POST } from "../app/api/cards/[id]/decision/route";

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
const ID = "0b9c0f6e-0000-4000-8000-000000000001";

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

describe("decision route handler", () => {
  const req = (key = "secret-key") =>
    new Request("http://web/api/cards/x/decision", {
      method: "POST",
      headers: { "content-type": "application/json", "x-editor-key": key },
      body: JSON.stringify(decision),
    });

  it("rejects an invalid UUID without calling upstream", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    const fn = stubFetch(Response.json({}));
    const res = await POST(req(), { params: Promise.resolve({ id: "../x" }) });
    expect(res.status).toBe(400);
    expect(fn).not.toHaveBeenCalled();
  });

  it("maps upstream failure to 502 without echoing the key", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    stubFetch(new Error("connect ECONNREFUSED secret-key"));
    const res = await POST(req(), { params: Promise.resolve({ id: ID }) });
    expect(res.status).toBe(502);
    const text = await res.text();
    expect(text).not.toContain("secret-key");
    expect(JSON.parse(text).error.code).toBe("upstream_unavailable");
  });

  it("passes through upstream status, body and forwards the key", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    const fn = stubFetch(
      Response.json({ error: { code: "unauthorized" } }, { status: 401 }),
    );
    const res = await POST(req(), { params: Promise.resolve({ id: ID }) });
    expect(res.status).toBe(401);
    expect((await res.json()).error.code).toBe("unauthorized");
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("x-editor-key")).toBe("secret-key");
  });
});

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

describe("triage markup is unstyled and safe", () => {
  const root = join(__dirname, "..");
  const all = [
    ...files(join(root, "components/triage")),
    ...files(join(root, "app/triage")),
  ].filter((f) => f.endsWith(".tsx"));

  it("finds the triage files", () => expect(all.length).toBeGreaterThan(3));

  it.each(all)("%s has no dangerouslySetInnerHTML, className or style", (f) => {
    const src = readFileSync(f, "utf8");
    expect(src).not.toMatch(/dangerouslySetInnerHTML|className|style=/);
    expect(src).toContain("TODO(design)");
  });
});
