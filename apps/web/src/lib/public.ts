// Server-side reads of published articles. Parsing is an allow-list: unknown fields are dropped.

export type PublicCover = {
  src: string | null;
  alt: string;
  credit: string | null;
};
export type PublicSource = { label: string; url: string };
export type PublicClaim = {
  text: string;
  status: string;
  source_indices: number[];
};
export type PublicSection = { heading: string; paragraphs: string[] };

export type PublicSummary = {
  slug: string;
  title: string;
  dek: string;
  meta_description: string;
  published_at: string;
  modified_at: string;
  cover: PublicCover;
};

export type PublicArticle = PublicSummary & {
  seo_title: string;
  byline: string;
  process_note: string;
  editor_analysis: string;
  sections: PublicSection[];
  claims: PublicClaim[];
  sources: PublicSource[];
};

const REVALIDATE_S = 300;
const TIMEOUT_MS = 10_000;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function str(v: unknown): string {
  if (typeof v !== "string") throw new Error("Malformed article response");
  return v;
}
function list(v: unknown): unknown[] {
  if (!Array.isArray(v)) throw new Error("Malformed article response");
  return v;
}
function rec(v: unknown): Record<string, unknown> {
  if (!isRecord(v)) throw new Error("Malformed article response");
  return v;
}

function parseCover(value: unknown): PublicCover {
  const c = rec(value);
  return {
    src: typeof c.src === "string" ? c.src : null,
    alt: str(c.alt),
    credit: typeof c.credit === "string" ? c.credit : null,
  };
}

export function parseSummary(value: unknown): PublicSummary {
  const a = rec(value);
  return {
    slug: str(a.slug),
    title: str(a.title),
    dek: str(a.dek),
    meta_description: str(a.meta_description),
    published_at: str(a.published_at),
    modified_at: str(a.modified_at),
    cover: parseCover(a.cover),
  };
}

export function parseArticle(value: unknown): PublicArticle {
  const a = rec(value);
  return {
    ...parseSummary(a),
    seo_title: str(a.seo_title),
    byline: str(a.byline),
    process_note: str(a.process_note),
    editor_analysis: str(a.editor_analysis),
    sections: list(a.sections).map((s) => {
      const section = rec(s);
      return {
        heading: str(section.heading),
        paragraphs: list(section.paragraphs).map(str),
      };
    }),
    claims: list(a.claims).map((c) => {
      const claim = rec(c);
      return {
        text: str(claim.text),
        status: str(claim.status),
        source_indices: list(claim.source_indices).filter(
          (i): i is number => typeof i === "number",
        ),
      };
    }),
    sources: list(a.sources).map((s) => {
      const source = rec(s);
      return { label: str(source.label), url: str(source.url) };
    }),
  };
}

function apiBase(): string {
  const base = process.env.API_BASE_URL;
  if (!base) throw new Error("API_BASE_URL is not set");
  return base;
}

// null when the article does not exist or is unpublished.
export async function fetchPublicArticle(
  slug: string,
): Promise<PublicArticle | null> {
  const response = await fetch(
    `${apiBase()}/articles/${encodeURIComponent(slug)}`,
    {
      next: { revalidate: REVALIDATE_S },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    },
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return parseArticle(await response.json());
}

export async function fetchPublicArticles(
  limit = 50,
): Promise<PublicSummary[]> {
  const response = await fetch(`${apiBase()}/articles?limit=${limit}`, {
    next: { revalidate: REVALIDATE_S },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return list(await response.json()).map(parseSummary);
}

// Pages and feeds must still render when the API is down: no articles beats a 500.
export async function fetchPublicArticlesSafe(
  limit = 50,
): Promise<PublicSummary[]> {
  try {
    return await fetchPublicArticles(limit);
  } catch {
    return [];
  }
}
