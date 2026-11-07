import { beforeEach, describe, expect, it, vi } from "vitest";

const { revalidateTag } = vi.hoisted(() => ({ revalidateTag: vi.fn() }));
vi.mock("next/cache", () => ({ revalidateTag }));

import { POST } from "./route";

function req(secret?: string): Request {
  return new Request("http://x/api/revalidate", {
    method: "POST",
    headers: secret ? { "x-revalidate-secret": secret } : {},
  });
}

describe("POST /api/revalidate", () => {
  beforeEach(() => {
    revalidateTag.mockClear();
    vi.stubEnv("REVALIDATE_SECRET", "s3cret");
  });

  it("503 when no secret is configured", async () => {
    vi.stubEnv("REVALIDATE_SECRET", "");
    expect((await POST(req("s3cret"))).status).toBe(503);
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it("401 on a missing or wrong secret", async () => {
    expect((await POST(req())).status).toBe(401);
    expect((await POST(req("nope"))).status).toBe(401);
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it("expires the articles tag on a valid secret", async () => {
    const res = await POST(req("s3cret"));
    expect(res.status).toBe(200);
    expect(revalidateTag).toHaveBeenCalledWith("articles", { expire: 0 });
  });
});
