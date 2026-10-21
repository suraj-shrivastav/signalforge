const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TIMEOUT_MS = 10_000;
const MAX_BODY_BYTES = 16 * 1024;

async function readCapped(request: Request): Promise<string | null> {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) return null;
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(chunks));
}

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

// Same-origin proxy for the key-protected draft edit and review writes.
export async function POST(
  request: Request,
  ctx: { params: Promise<{ id: string; action: string }> },
): Promise<Response> {
  const { id, action } = await ctx.params;
  if (!UUID_RE.test(id)) {
    return errorResponse(400, "invalid_card_id", "Card id must be a UUID");
  }
  if (action !== "sentence" && action !== "review") {
    return errorResponse(404, "unknown_action", "Unknown draft action");
  }
  const base = process.env.API_BASE_URL;
  if (!base) {
    return errorResponse(503, "not_configured", "API is not configured");
  }
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const key = request.headers.get("x-editor-key");
  if (contentType) headers.set("content-type", contentType);
  if (key !== null) headers.set("x-editor-key", key);
  const body = await readCapped(request);
  if (body === null) {
    return errorResponse(413, "payload_too_large", "Request body too large");
  }
  const correlationId = crypto.randomUUID();
  try {
    const upstream = await fetch(`${base}/editor/drafts/${id}/${action}`, {
      method: "POST",
      headers,
      body,
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
  } catch (err) {
    console.error(
      JSON.stringify({
        event: "draft_action_proxy_failed",
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
