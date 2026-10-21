import { fetchPublicArticlesSafe } from "@/lib/public";
import { atomFeed } from "@/lib/seo";
import { siteUrl } from "@/lib/site";

// Read at request time: SITE_URL and the article list are not known at build. The fetch
// data cache (5 minutes) keeps API load low.
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const items = await fetchPublicArticlesSafe(50);
  return new Response(atomFeed(items, siteUrl()), {
    headers: { "Content-Type": "application/atom+xml; charset=utf-8" },
  });
}
