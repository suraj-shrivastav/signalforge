// Server-side reads of published articles. Parsing is an allow-list: unknown fields are dropped.

export type PublicCover = {
  src: string | null;
  alt: string;
  credit: string | null;
};
export type PublicFigure = { src: string; alt: string; caption: string };
export type PublicSource = { label: string; url: string };
export type PublicClaim = {
  text: string;
  status: string;
  source_indices: number[];
};
// A source table copied by the pipeline; `source` says which page it came from.
export type PublicTable = {
  caption: string;
  header: string[];
  rows: string[][];
  source: PublicSource | null;
};
export type PublicSection = {
  heading: string;
  paragraphs: string[];
  table?: PublicTable | null;
};

export type PublicHeadline = {
  value: string;
  unit: string;
  direction: "up" | "down" | "none";
  takeaway: string;
};

export type PublicSummary = {
  slug: string;
  title: string;
  dek: string;
  meta_description: string;
  published_at: string;
  modified_at: string;
  cover: PublicCover;
  kind: string | null;
  source_label: string;
  headline: PublicHeadline | null;
};

export type PublicArticle = PublicSummary & {
  seo_title: string;
  byline: string;
  process_note: string;
  editor_analysis: string;
  sections: PublicSection[];
  claims: PublicClaim[];
  sources: PublicSource[];
  figure: PublicFigure | null;
};

const REVALIDATE_S = 300;
// POST /api/revalidate expires this tag right after a publish, so readers see new articles at once.
export const ARTICLES_TAG = "articles";
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

// A malformed table is left out rather than failing the whole article.
function parseTable(value: unknown): PublicTable | null {
  if (!isRecord(value)) return null;
  try {
    const header = list(value.header).map(str);
    const rows = list(value.rows).map((row) => list(row).map(str));
    if (header.length < 2 || rows.length < 1) return null;
    if (rows.some((row) => row.length !== header.length)) return null;
    const source = isRecord(value.source)
      ? { label: str(value.source.label), url: str(value.source.url) }
      : null;
    return {
      caption: typeof value.caption === "string" ? value.caption : "",
      header,
      rows,
      source,
    };
  } catch {
    return null;
  }
}

function parseCover(value: unknown): PublicCover {
  const c = rec(value);
  return {
    src: typeof c.src === "string" ? c.src : null,
    alt: str(c.alt),
    credit: typeof c.credit === "string" ? c.credit : null,
  };
}

// Absent on old articles; a malformed headline is dropped rather than failing the article.
function parseHeadline(value: unknown): PublicHeadline | null {
  if (!isRecord(value)) return null;
  try {
    const d = value.direction;
    return {
      value: str(value.value),
      unit: typeof value.unit === "string" ? value.unit : "",
      direction: d === "up" || d === "down" ? d : "none",
      takeaway: typeof value.takeaway === "string" ? value.takeaway : "",
    };
  } catch {
    return null;
  }
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
    kind: typeof a.kind === "string" ? a.kind : null,
    source_label: typeof a.source_label === "string" ? a.source_label : "",
    headline: parseHeadline(a.headline),
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
        table: parseTable(section.table),
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
    figure: isRecord(a.figure)
      ? {
          src: str(a.figure.src),
          alt: str(a.figure.alt),
          caption: typeof a.figure.caption === "string" ? a.figure.caption : "",
        }
      : null,
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
      next: { revalidate: REVALIDATE_S, tags: [ARTICLES_TAG] },
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
    next: { revalidate: REVALIDATE_S, tags: [ARTICLES_TAG] },
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
