import type { MetadataRoute } from "next";
import { blockTrainingCrawlers, siteUrl } from "@/lib/site";

// Search and retrieval crawlers that put articles in answers: always allowed.
const SEARCH_AGENTS = [
  "Googlebot",
  "Bingbot",
  "OAI-SearchBot",
  "PerplexityBot",
  "Claude-SearchBot",
  "Claude-User",
];
// Crawlers that collect training data. Allowed unless AI_TRAINING_CRAWLERS=block.
const TRAINING_AGENTS = ["GPTBot", "ClaudeBot", "Google-Extended"];
const PRIVATE_PATHS = ["/editor", "/api/", "/design", "/search"];

// Read at request time: SITE_URL and the article list are not known at build. The fetch
// data cache (5 minutes) keeps API load low.
export const dynamic = "force-dynamic";

export default function robots(): MetadataRoute.Robots {
  const site = siteUrl();
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: PRIVATE_PATHS },
      { userAgent: SEARCH_AGENTS, allow: "/", disallow: PRIVATE_PATHS },
      ...(blockTrainingCrawlers()
        ? [{ userAgent: TRAINING_AGENTS, disallow: "/" }]
        : []),
    ],
    sitemap: [`${site}/sitemap.xml`, `${site}/news-sitemap.xml`],
  };
}
