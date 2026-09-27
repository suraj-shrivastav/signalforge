import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "../app/api/cards/[id]/decision/route";

const decision = {
  decision: "accepted",
  reason_tags: [],
  note: "",
  decision_ms: 10,
};
const ID = "0b9c0f6e-0000-4000-8000-000000000001";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

function stubFetch(res: Response | Error) {
  const fn = vi.fn(async () => {
    if (res instanceof Error) throw res;
    return res;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

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

  it("returns 503 not_configured when the base URL is unset", async () => {
    vi.stubEnv("API_BASE_URL", "");
    const fn = stubFetch(Response.json({}));
    const res = await POST(req(), { params: Promise.resolve({ id: ID }) });
    expect(res.status).toBe(503);
    expect((await res.json()).error.code).toBe("not_configured");
    expect(fn).not.toHaveBeenCalled();
  });

  it("maps a timeout to 502 and never logs the key", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    stubFetch(new DOMException("timed out secret-key", "TimeoutError"));
    const res = await POST(req(), { params: Promise.resolve({ id: ID }) });
    expect(res.status).toBe(502);
    const cid = (await res.json()).error.correlation_id;
    const logged = JSON.stringify(log.mock.calls);
    expect(logged).not.toContain("secret-key");
    expect(logged).toContain(cid);
  });

  it("rejects an oversized body with 413 (declared and streamed)", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    const fn = stubFetch(Response.json({}));
    const big = "x".repeat(17 * 1024);
    const r1 = new Request("http://web/x", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "content-length": "99999",
      },
      body: "{}",
    });
    expect(
      (await POST(r1, { params: Promise.resolve({ id: ID }) })).status,
    ).toBe(413);
    const r2 = new Request("http://web/x", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: big,
    });
    expect(
      (await POST(r2, { params: Promise.resolve({ id: ID }) })).status,
    ).toBe(413);
    expect(fn).not.toHaveBeenCalled();
  });

  it("forwards only content-type and the key, not cookies", async () => {
    vi.stubEnv("API_BASE_URL", "http://api");
    const fn = stubFetch(Response.json({}, { status: 201 }));
    const r = new Request("http://web/x", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-editor-key": "secret-key",
        cookie: "sid=1",
        authorization: "Bearer z",
      },
      body: JSON.stringify(decision),
    });
    await POST(r, { params: Promise.resolve({ id: ID }) });
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    const h = new Headers(init.headers);
    expect(h.get("content-type")).toBe("application/json");
    expect(h.get("cookie")).toBeNull();
    expect(h.get("authorization")).toBeNull();
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

it("route handler does not use dangerouslySetInnerHTML", () => {
  const src = readFileSync(
    join(__dirname, "../app/api/cards/[id]/decision/route.ts"),
    "utf8",
  );
  expect(src).not.toContain("dangerouslySetInnerHTML");
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
    ...files(join(root, "app/editor/triage")),
  ].filter((f) => f.endsWith(".tsx") && !f.includes("ArticlePreview"));

  it("finds the triage files", () => expect(all.length).toBeGreaterThan(3));

  it.each(all)("%s has no dangerouslySetInnerHTML, className or style", (f) => {
    const src = readFileSync(f, "utf8");
    expect(src).not.toMatch(
      /dangerouslySetInnerHTML|className|style\s*=|\.css["']/,
    );
    expect(src).toContain("TODO(design)");
  });
});
