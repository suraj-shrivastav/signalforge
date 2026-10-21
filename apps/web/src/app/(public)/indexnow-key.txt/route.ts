export const dynamic = "force-dynamic";

// IndexNow proves site ownership by serving the key at a known URL. Set INDEXNOW_KEY to the
// same value the API uses. Without it there is nothing to serve.
export function GET(): Response {
  const key = process.env.INDEXNOW_KEY;
  if (!key) return new Response("Not found", { status: 404 });
  return new Response(key, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
