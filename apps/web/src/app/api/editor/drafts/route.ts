const TIMEOUT_MS = 10_000;

function errorResponse(
  status: number,
  code: string,
  message: string,
  correlationId: string = crypto.randomUUID(),
) {
  return Response.json(
    { error: { code, message, correlation_id: correlationId } },
    { status },
  );
}

// Same-origin proxy for the key-protected draft list; the API has no CORS.
export async function GET(request: Request): Promise<Response> {
  const base = process.env.API_BASE_URL;
  if (!base) {
    return errorResponse(503, "not_configured", "API is not configured");
  }
  const headers = new Headers();
  const key = request.headers.get("x-editor-key");
  if (key !== null) headers.set("x-editor-key", key);
  const correlationId = crypto.randomUUID();
  try {
    const upstream = await fetch(`${base}/editor/drafts`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (err) {
    console.error(
      JSON.stringify({
        event: "draft_list_proxy_failed",
        error: err instanceof Error ? err.name : "unknown",
        correlation_id: correlationId,
      }),
    );
    return errorResponse(
      502,
      "upstream_unavailable",
      "Could not reach the API",
      correlationId,
    );
  }
}
