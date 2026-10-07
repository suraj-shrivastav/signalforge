export type Assessment = {
  is_relevant: boolean;
  relevance_score: number;
  category: string;
  summary: string;
  why_it_matters: string;
};

export type Signal = {
  id: string;
  source: string;
  source_type: string;
  canonical_url: string;
  title: string;
  published_at: string;
  summary: string;
  metadata: Record<string, unknown>;
  assessment?: Assessment;
};

export type SignalList = { items: Signal[]; next_cursor: string | null };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseAssessment(value: unknown): Assessment {
  if (!isRecord(value)) throw new Error("assessment is not an object");
  const { is_relevant, relevance_score, category, summary, why_it_matters } =
    value;
  if (
    typeof is_relevant !== "boolean" ||
    typeof relevance_score !== "number" ||
    typeof category !== "string" ||
    typeof summary !== "string" ||
    typeof why_it_matters !== "string"
  ) {
    throw new Error("assessment has an unexpected shape");
  }
  return { is_relevant, relevance_score, category, summary, why_it_matters };
}

function parseSignal(value: unknown): Signal {
  if (!isRecord(value)) throw new Error("signal is not an object");
  const {
    id,
    source,
    source_type,
    canonical_url,
    title,
    published_at,
    summary,
    metadata,
    assessment,
  } = value;
  if (
    typeof id !== "string" ||
    typeof source !== "string" ||
    typeof source_type !== "string" ||
    typeof canonical_url !== "string" ||
    typeof title !== "string" ||
    typeof published_at !== "string" ||
    typeof summary !== "string" ||
    !isRecord(metadata)
  ) {
    throw new Error("signal has an unexpected shape");
  }
  return {
    id,
    source,
    source_type,
    canonical_url,
    title,
    published_at,
    summary,
    metadata,
    ...(assessment == null ? {} : { assessment: parseAssessment(assessment) }),
  };
}

export function parseSignalList(json: unknown): SignalList {
  if (!isRecord(json) || !Array.isArray(json.items))
    throw new Error("unexpected response shape");
  const next = json.next_cursor;
  if (next !== null && typeof next !== "string")
    throw new Error("unexpected cursor");
  return { items: json.items.map(parseSignal), next_cursor: next };
}

const PAGE_SIZE = 20;
const TIMEOUT_MS = 10_000;

export async function fetchSignals(
  cursor?: string,
  relevantOnly = true,
): Promise<SignalList> {
  const base = process.env.API_BASE_URL;
  if (!base) throw new Error("API_BASE_URL is not set");
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (relevantOnly) params.set("relevant_only", "true");
  if (cursor) params.set("cursor", cursor);
  const response = await fetch(`${base}/signals?${params}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return parseSignalList(await response.json());
}

// Mirrors REASON_TAGS in src/signalforge/core/reason_tags.py.
export const REASON_TAGS = [
  "off_niche",
  "too_incremental",
  "duplicate",
  "already_covered",
  "low_quality_source",
  "great_angle",
  "timely",
  "evergreen",
  "needs_more_evidence",
] as const;
export type ReasonTag = (typeof REASON_TAGS)[number];

export type DecisionKind = "accepted" | "rejected" | "snoozed";

export type Decision = {
  decision: DecisionKind;
  reason_tags: ReasonTag[];
  note: string;
  decision_ms: number | null;
};

export type CardSignal = {
  id: string;
  title: string;
  source: string;
  canonical_url: string;
};

export type Card = {
  id: string;
  what_happened: string;
  why_it_matters: string;
  novelty: number;
  signal_strength: number;
  coverage_gap: string;
  suggested_angle: string;
  format: string;
  evergreen_score: number;
  confidence: number;
  risk_flags: string[];
  signal: CardSignal;
  score: number;
  wildcard: boolean;
  status: "proposed" | "snoozed";
  created_at: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function isString(v: unknown): v is string {
  return typeof v === "string";
}

function isNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function parseCardSignal(value: unknown): CardSignal {
  if (!isRecord(value))
    throw new ApiError(502, "bad_shape", "signal is not an object");
  const { id, title, source, canonical_url } = value;
  if (
    !isString(id) ||
    !isString(title) ||
    !isString(source) ||
    !isString(canonical_url)
  ) {
    throw new ApiError(502, "bad_shape", "card signal has an unexpected shape");
  }
  return { id, title, source, canonical_url };
}

export function parseCard(value: unknown): Card {
  const bad = () =>
    new ApiError(502, "bad_shape", "card has an unexpected shape");
  if (!isRecord(value)) throw bad();
  const v = value;
  if (
    !isString(v.id) ||
    !isString(v.what_happened) ||
    !isString(v.why_it_matters) ||
    !isNumber(v.novelty) ||
    !isNumber(v.signal_strength) ||
    !isString(v.coverage_gap) ||
    !isString(v.suggested_angle) ||
    !isString(v.format) ||
    !isNumber(v.evergreen_score) ||
    !isNumber(v.confidence) ||
    !Array.isArray(v.risk_flags) ||
    !v.risk_flags.every(isString) ||
    !isNumber(v.score) ||
    typeof v.wildcard !== "boolean" ||
    (v.status !== "proposed" && v.status !== "snoozed") ||
    !isString(v.created_at)
  ) {
    throw bad();
  }
  return {
    id: v.id,
    what_happened: v.what_happened,
    why_it_matters: v.why_it_matters,
    novelty: v.novelty,
    signal_strength: v.signal_strength,
    coverage_gap: v.coverage_gap,
    suggested_angle: v.suggested_angle,
    format: v.format,
    evergreen_score: v.evergreen_score,
    confidence: v.confidence,
    risk_flags: v.risk_flags,
    signal: parseCardSignal(v.signal),
    score: v.score,
    wildcard: v.wildcard,
    status: v.status,
    created_at: v.created_at,
  };
}

export function parseQueue(json: unknown): Card[] {
  if (!Array.isArray(json))
    throw new ApiError(502, "bad_shape", "queue is not a list");
  return json.map(parseCard);
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `API returned ${response.status}`;
  try {
    const body: unknown = await response.json();
    if (isRecord(body) && isRecord(body.error)) {
      if (isString(body.error.code)) code = body.error.code;
      if (isString(body.error.message)) message = body.error.message;
    }
  } catch {
    // Body was not JSON; keep the safe defaults.
  }
  return new ApiError(response.status, code, message);
}

export async function fetchQueue(limit = 15): Promise<Card[]> {
  const base = process.env.API_BASE_URL;
  if (!base)
    throw new ApiError(500, "not_configured", "API_BASE_URL is not set");
  const response = await fetch(`${base}/cards/queue?limit=${limit}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw await errorFromResponse(response);
  return parseQueue(await response.json());
}

// Runs in the browser; calls the same-origin proxy route (the API has no CORS).
export async function postDecision(
  cardId: string,
  body: Decision,
  editorKey: string,
): Promise<void> {
  const response = await fetch(
    `/api/cards/${encodeURIComponent(cardId)}/decision`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Editor-Key": editorKey,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15_000),
    },
  );
  if (!response.ok) throw await errorFromResponse(response);
}

// Mirrors ArticleDraft in src/signalforge/core/artifacts/article.py (editor-only).
export const ARTICLE_TEMPLATES = [
  "news_brief",
  "explainer",
  "paper_breakdown",
  "comparison",
] as const;
export type ArticleTemplate = (typeof ARTICLE_TEMPLATES)[number];

export const CLAIM_STATUSES = [
  "verified",
  "supported",
  "uncertain",
  "conflicting",
  "unverified",
] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

export type DraftStatus = "drafting" | "drafted" | "needs_more_info" | "failed";

export type DraftSection = { heading: string; paragraphs: string[] };
export type DraftClaim = {
  text: string;
  evidence_span: string;
  document_indices: number[];
  status: ClaimStatus;
};
export type DraftSource = { label: string; url: string };
export type DraftCover = {
  src: string | null;
  alt: string;
  credit: string | null;
};
export type ArticleBody = {
  title: string;
  dek: string;
  sections: DraftSection[];
  claims: DraftClaim[];
  sources: DraftSource[];
  cover: DraftCover;
};
export type EditorDraft = {
  card_id: string;
  status: DraftStatus;
  template: ArticleTemplate;
  draft: ArticleBody | null;
  review_summary: string;
};

const DRAFT_STATUSES: readonly string[] = [
  "drafting",
  "drafted",
  "needs_more_info",
  "failed",
];

function badDraft(): ApiError {
  return new ApiError(502, "bad_shape", "draft has an unexpected shape");
}

function isStringList(v: unknown): v is string[] {
  return Array.isArray(v) && v.every(isString);
}

function isOneOf<T extends string>(options: readonly T[], v: unknown): v is T {
  return isString(v) && (options as readonly string[]).includes(v);
}

function parseBody(value: unknown): ArticleBody {
  if (!isRecord(value)) throw badDraft();
  const { title, dek, sections, claims, sources, cover } = value;
  if (
    !isString(title) ||
    !isString(dek) ||
    !Array.isArray(sections) ||
    !Array.isArray(claims) ||
    !Array.isArray(sources) ||
    !isRecord(cover) ||
    !isString(cover.alt)
  ) {
    throw badDraft();
  }
  return {
    title,
    dek,
    sections: sections.map((s: unknown) => {
      if (!isRecord(s) || !isString(s.heading) || !isStringList(s.paragraphs))
        throw badDraft();
      return { heading: s.heading, paragraphs: s.paragraphs };
    }),
    claims: claims.map((c: unknown) => {
      if (
        !isRecord(c) ||
        !isString(c.text) ||
        !isString(c.evidence_span) ||
        !Array.isArray(c.document_indices) ||
        !c.document_indices.every(isNumber) ||
        !isOneOf(CLAIM_STATUSES, c.status)
      )
        throw badDraft();
      return {
        text: c.text,
        evidence_span: c.evidence_span,
        document_indices: c.document_indices,
        status: c.status,
      };
    }),
    sources: sources.map((s: unknown) => {
      if (!isRecord(s) || !isString(s.label) || !isString(s.url))
        throw badDraft();
      return { label: s.label, url: s.url };
    }),
    cover: {
      src: isString(cover.src) ? cover.src : null,
      alt: cover.alt,
      credit: isString(cover.credit) ? cover.credit : null,
    },
  };
}

export function parseEditorDraft(json: unknown): EditorDraft {
  if (!isRecord(json)) throw badDraft();
  const { card_id, status, template, draft, review_summary } = json;
  if (
    !isString(card_id) ||
    !isOneOf(DRAFT_STATUSES, status) ||
    !isOneOf(ARTICLE_TEMPLATES, template) ||
    !isString(review_summary)
  ) {
    throw badDraft();
  }
  return {
    card_id,
    status: status as DraftStatus,
    template,
    draft: draft == null ? null : parseBody(draft),
    review_summary,
  };
}

// Runs in the browser through the same-origin proxy. Returns null when no draft exists.
export async function fetchEditorDraft(
  cardId: string,
  editorKey: string,
): Promise<EditorDraft | null> {
  const response = await fetch(
    `/api/editor/drafts/${encodeURIComponent(cardId)}`,
    {
      headers: { "X-Editor-Key": editorKey },
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    },
  );
  if (response.status === 404) return null;
  if (!response.ok) throw await errorFromResponse(response);
  return parseEditorDraft(await response.json());
}

export type DraftSummary = {
  card_id: string;
  status: DraftStatus;
  template: ArticleTemplate;
  title: string;
  signal_title: string;
  claim_counts: Partial<Record<ClaimStatus, number>>;
  created_at: string;
};

function parseDraftSummary(value: unknown): DraftSummary {
  if (!isRecord(value)) throw badDraft();
  const { card_id, status, template, title, signal_title, claim_counts } =
    value;
  if (
    !isString(card_id) ||
    !isOneOf(DRAFT_STATUSES, status) ||
    !isOneOf(ARTICLE_TEMPLATES, template) ||
    !isString(title) ||
    !isString(signal_title) ||
    !isRecord(claim_counts) ||
    !isString(value.created_at)
  ) {
    throw badDraft();
  }
  const counts: Partial<Record<ClaimStatus, number>> = {};
  for (const s of CLAIM_STATUSES) {
    const n = claim_counts[s];
    if (isNumber(n)) counts[s] = n;
  }
  return {
    card_id,
    status: status as DraftStatus,
    template,
    title,
    signal_title,
    claim_counts: counts,
    created_at: value.created_at,
  };
}

export function parseDraftList(json: unknown): DraftSummary[] {
  if (!Array.isArray(json)) throw badDraft();
  return json.map(parseDraftSummary);
}

// Runs in the browser through the same-origin proxy.
export async function fetchDraftList(
  editorKey: string,
): Promise<DraftSummary[]> {
  const response = await fetch("/api/editor/drafts", {
    headers: { "X-Editor-Key": editorKey },
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw await errorFromResponse(response);
  return parseDraftList(await response.json());
}
