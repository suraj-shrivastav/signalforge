import type { Metadata } from "next";
import { safeHref } from "@/lib/format";
import type { PublicArticle, PublicSummary } from "@/lib/public";
import { SITE_NAME } from "@/lib/site";

const GOOD_STATUSES = ["verified", "supported"];
const NEWS_WINDOW_MS = 2 * 24 * 60 * 60 * 1000;

export function articleUrl(site: string, slug: string): string {
  return `${site}/articles/${encodeURIComponent(slug)}`;
}

export type KeyFact = {
  text: string;
  sources: { label: string; url: string }[];
};

// Verified or supported claims with the sources that state them: the answer-first block.
export function keyFacts(article: PublicArticle): KeyFact[] {
  return article.claims
    .filter((c) => GOOD_STATUSES.includes(c.status))
    .map((claim) => ({
      text: claim.text,
      sources: claim.source_indices.flatMap((i) => {
        const source = article.sources[i];
        return source && safeHref(source.url) ? [source] : [];
      }),
    }));
}

function authorType(byline: string): "Organization" | "Person" {
  return /editorial|team|staff|desk|newsroom/i.test(byline)
    ? "Organization"
    : "Person";
}

export function socialImageUrl(site: string, slug: string): string {
  return `${articleUrl(site, slug)}/og.png`;
}

// BreadcrumbList for the visible trail: Home, then the article.
export function breadcrumbJsonLd(
  article: PublicArticle,
  site: string,
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: `${site}/` },
      {
        "@type": "ListItem",
        position: 2,
        name: article.title,
        item: articleUrl(site, article.slug),
      },
    ],
  };
}

export function articleJsonLd(
  article: PublicArticle,
  site: string,
): Record<string, unknown> {
  const url = articleUrl(site, article.slug);
  const citations = article.sources.flatMap((s) =>
    safeHref(s.url)
      ? [{ "@type": "CreativeWork", name: s.label, url: s.url }]
      : [],
  );
  return {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: article.title,
    description: article.meta_description,
    datePublished: article.published_at,
    dateModified: article.modified_at,
    author: { "@type": authorType(article.byline), name: article.byline },
    publisher: { "@type": "Organization", name: SITE_NAME, url: site },
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    url,
    inLanguage: "en",
    isAccessibleForFree: true,
    // A PNG card for every article (see opengraph-image-card.tsx); the SVG cover is not a valid
    // social or search thumbnail.
    image: [socialImageUrl(site, article.slug)],
    ...(citations.length ? { citation: citations } : {}),
  };
}

// JSON-LD goes inside a script tag: escape "<" so the payload cannot close it.
export function jsonLdString(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

export function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

// The same article as plain Markdown, for agents: claims keep their sources.
export function articleMarkdown(article: PublicArticle, site: string): string {
  const lines = [
    `# ${article.title}`,
    "",
    `> ${article.dek}`,
    "",
    `By ${article.byline}. Published ${article.published_at}. Updated ${article.modified_at}.`,
    `Canonical: ${articleUrl(site, article.slug)}`,
    "",
  ];
  const facts = keyFacts(article);
  if (facts.length) {
    lines.push("## Key facts", "");
    for (const fact of facts) {
      const refs = fact.sources.map((s) => `[${s.label}](${s.url})`).join(", ");
      lines.push(`- ${fact.text}${refs ? ` (${refs})` : ""}`);
    }
    lines.push("");
  }
  for (const section of article.sections) {
    lines.push(
      `## ${section.heading}`,
      "",
      ...section.paragraphs.flatMap((p) => [p, ""]),
    );
  }
  if (article.editor_analysis) {
    lines.push("## Editor's analysis", "", article.editor_analysis, "");
  }
  lines.push("## Sources", "");
  article.sources.forEach((s, i) =>
    lines.push(`${i + 1}. [${s.label}](${s.url})`),
  );
  lines.push("", `_${article.process_note}_`, "");
  return lines.join("\n");
}

export function atomFeed(items: PublicSummary[], site: string): string {
  const updated = items.reduce(
    (latest, a) => (a.modified_at > latest ? a.modified_at : latest),
    items[0]?.modified_at ?? "1970-01-01T00:00:00Z",
  );
  const entries = items
    .map((a) => {
      const url = articleUrl(site, a.slug);
      return `  <entry>
    <title>${escapeXml(a.title)}</title>
    <id>${escapeXml(url)}</id>
    <link rel="alternate" type="text/html" href="${escapeXml(url)}"/>
    <published>${escapeXml(a.published_at)}</published>
    <updated>${escapeXml(a.modified_at)}</updated>
    <summary>${escapeXml(a.meta_description)}</summary>
  </entry>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>${SITE_NAME}</title>
  <id>${escapeXml(site)}/feed.xml</id>
  <link rel="self" href="${escapeXml(site)}/feed.xml"/>
  <link rel="alternate" href="${escapeXml(site)}/"/>
  <updated>${escapeXml(updated)}</updated>
${entries}
</feed>
`;
}

// Google News sitemap: only articles from the last two days, at most 1,000.
export function newsSitemap(
  items: PublicSummary[],
  site: string,
  now: Date,
): string {
  const recent = items
    .filter((a) => now.getTime() - Date.parse(a.published_at) <= NEWS_WINDOW_MS)
    .slice(0, 1000);
  const urls = recent
    .map(
      (a) => `  <url>
    <loc>${escapeXml(articleUrl(site, a.slug))}</loc>
    <news:news>
      <news:publication>
        <news:name>${SITE_NAME}</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>${escapeXml(a.published_at)}</news:publication_date>
      <news:title>${escapeXml(a.title)}</news:title>
    </news:news>
  </url>`,
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
${urls}
</urlset>
`;
}

// Search, social and agent metadata for an article page. Kept here, not in the page, so it
// is unit-tested and the public page source stays free of authorship wording.
export function articleMetadata(
  article: PublicArticle,
  site: string,
): Metadata {
  const url = articleUrl(site, article.slug);
  const image = socialImageUrl(site, article.slug);
  return {
    title: article.seo_title,
    description: article.meta_description,
    authors: [{ name: article.byline }],
    alternates: {
      canonical: url,
      types: {
        "text/markdown": `${url}/md`,
        "application/json": `${url}/json`,
      },
    },
    openGraph: {
      type: "article",
      siteName: SITE_NAME,
      title: article.seo_title,
      description: article.meta_description,
      url,
      publishedTime: article.published_at,
      modifiedTime: article.modified_at,
      authors: [article.byline],
      images: [
        { url: image, width: 1200, height: 630, alt: article.cover.alt },
      ],
    },
    twitter: {
      card: "summary_large_image",
      images: [image],
      title: article.seo_title,
      description: article.meta_description,
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
        "max-video-preview": -1,
      },
    },
  };
}
