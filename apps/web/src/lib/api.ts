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
