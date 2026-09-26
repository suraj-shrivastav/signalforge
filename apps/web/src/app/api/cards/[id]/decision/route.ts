const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TIMEOUT_MS = 10_000;

function errorResponse(status: number, code: string, message: string) {
  return Response.json(
    { error: { code, message, correlation_id: crypto.randomUUID() } },
    { status },
  );
}

// Same-origin proxy: the API has no CORS, so browsers write through here.
export async function POST(
  request: Request,
  ctx: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await ctx.params;
  if (!UUID_RE.test(id)) {
    return errorResponse(400, "invalid_card_id", "Card id must be a UUID");
  }
  const base = process.env.API_BASE_URL;
  if (!base) {
    return errorResponse(502, "upstream_unavailable", "API is not configured");
  }
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const key = request.headers.get("x-editor-key");
  if (contentType) headers.set("content-type", contentType);
  if (key !== null) headers.set("x-editor-key", key);
  try {
    const upstream = await fetch(`${base}/cards/${id}/decision`, {
      method: "POST",
      headers,
      body: await request.text(),
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
