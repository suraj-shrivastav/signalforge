const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const TIMEOUT_MS = 10_000;

function errorResponse(status: number, code: string, message: string) {
  return Response.json({ error: { code, message } }, { status });
}

// Same-origin proxy for the key-protected unpublish write.
export async function POST(
  request: Request,
  ctx: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await ctx.params;
  if (!SLUG_RE.test(slug) || slug.length > 200) {
    return errorResponse(400, "invalid_slug", "Invalid article slug");
  }
  const base = process.env.API_BASE_URL;
  if (!base) {
    return errorResponse(503, "not_configured", "API is not configured");
  }
  const headers = new Headers();
  const key = request.headers.get("x-editor-key");
  if (key !== null) headers.set("x-editor-key", key);
  try {
    const upstream = await fetch(`${base}/editor/articles/${slug}/unpublish`, {
      method: "POST",
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return errorResponse(
      502,
      "upstream_unavailable",
      "Could not reach the API",
    );
  }
}
