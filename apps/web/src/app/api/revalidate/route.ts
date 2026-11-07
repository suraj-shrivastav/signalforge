import { timingSafeEqual } from "node:crypto";
import { revalidateTag } from "next/cache";
import { ARTICLES_TAG } from "@/lib/public";

function errorResponse(status: number, code: string, message: string) {
  return Response.json({ error: { code, message } }, { status });
}

function secretMatches(given: string, expected: string): boolean {
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

// Called by the pipeline right after a publish. Expires the cached article list and articles.
export async function POST(request: Request): Promise<Response> {
  const expected = process.env.REVALIDATE_SECRET;
  if (!expected) {
    return errorResponse(
      503,
      "not_configured",
      "Revalidation is not configured",
    );
  }
  const given = request.headers.get("x-revalidate-secret") ?? "";
  if (!secretMatches(given, expected)) {
    return errorResponse(401, "unauthorized", "Invalid revalidate secret");
  }
  // expire: 0 means the next request blocks on fresh data; stale content is never served.
  revalidateTag(ARTICLES_TAG, { expire: 0 });
  return Response.json({ revalidated: ARTICLES_TAG });
}
