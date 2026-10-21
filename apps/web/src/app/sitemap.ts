import type { MetadataRoute } from "next";
import { fetchPublicArticlesSafe } from "@/lib/public";
import { articleUrl } from "@/lib/seo";
import { siteUrl } from "@/lib/site";

// Read at request time: SITE_URL and the article list are not known at build. The fetch
// data cache (5 minutes) keeps API load low.
export const dynamic = "force-dynamic";

// lastModified is the article's real modified_at: Google ignores a lastmod it cannot trust.
// priority and changeFrequency are omitted because Google ignores them.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const site = siteUrl();
  const articles = await fetchPublicArticlesSafe(200);
  const newest = articles[0]?.modified_at;
  return [
    { url: `${site}/`, ...(newest ? { lastModified: new Date(newest) } : {}) },
    ...articles.map((a) => ({
      url: articleUrl(site, a.slug),
      lastModified: new Date(a.modified_at),
    })),
  ];
}
