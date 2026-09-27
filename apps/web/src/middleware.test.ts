import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { COOKIE_NAME, signSession } from "@/lib/editorAuth";
import { middleware } from "./middleware";

const ORIGINAL_ENV = { ...process.env };

describe("editor auth middleware", () => {
  beforeEach(() => {
    process.env.EDITOR_UI_PASSWORD = "test-password";
    delete process.env.EDITOR_COOKIE_SECRET;
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  it("redirects to login when there is no cookie", async () => {
    const request = new NextRequest(new URL("http://localhost/editor/signals"));
    const response = await middleware(request);
    expect([307, 308]).toContain(response.status);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/editor/login");
    expect(location.searchParams.get("next")).toBe("/editor/signals");
  });

  it("passes through when the cookie is valid", async () => {
    const cookieValue = await signSession("test-password", Date.now());
    const request = new NextRequest(
      new URL("http://localhost/editor/signals"),
      { headers: { cookie: `${COOKIE_NAME}=${cookieValue}` } },
    );
    const response = await middleware(request);
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("never redirects requests to /editor/login", async () => {
    const request = new NextRequest(new URL("http://localhost/editor/login"));
    const response = await middleware(request);
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("passes through non-editor paths untouched", async () => {
    const home = await middleware(
      new NextRequest(new URL("http://localhost/")),
    );
    expect(home.status).toBe(200);
    expect(home.headers.get("location")).toBeNull();

    const api = await middleware(
      new NextRequest(new URL("http://localhost/api/cards/x/decision")),
    );
    expect(api.status).toBe(200);
    expect(api.headers.get("location")).toBeNull();
  });
});
