import { fetchPublicArticlesSafe } from "@/lib/public";
import { newsSitemap } from "@/lib/seo";
import { siteUrl } from "@/lib/site";

// Read at request time: SITE_URL and the article list are not known at build. The fetch
// data cache (5 minutes) keeps API load low.
export const dynamic = "force-dynamic";

// Google News sitemap: articles from the last two days only.
export async function GET(): Promise<Response> {
  const items = await fetchPublicArticlesSafe(200);
  return new Response(newsSitemap(items, siteUrl(), new Date()), {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
}
