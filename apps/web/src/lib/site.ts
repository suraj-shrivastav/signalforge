export const SITE_NAME = "SignalForge";

// Public origin used for canonical URLs, sitemaps and feeds. Set SITE_URL in production.
export function siteUrl(): string {
  const raw = process.env.SITE_URL ?? "http://localhost:3000";
  return raw.replace(/\/+$/, "");
}

// Only block training crawlers when AI_TRAINING_CRAWLERS=block. Search and retrieval
// crawlers are always allowed (see docs/pipeline/seo-geo-strategy.md section 3.3).
export function blockTrainingCrawlers(): boolean {
  return process.env.AI_TRAINING_CRAWLERS === "block";
}
