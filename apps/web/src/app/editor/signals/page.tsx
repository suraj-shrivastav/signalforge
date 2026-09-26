import Link from "next/link";
import { fetchSignals } from "@/lib/api";
import { formatRelative, formatScore, hostOf, safeHref } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string; all?: string }>;
}) {
  const { cursor, all } = await searchParams;
  const showAll = all === "1";
  let list;
  try {
    list = await fetchSignals(cursor, !showAll);
  } catch {
    return (
      <main>
        <h1>Signals</h1>
        <p role="alert">
          Could not load signals. Check that the API is running.
        </p>
      </main>
    );
  }

  const now = new Date();
  return (
    <main>
      <h1>Signals</h1>
      <p>
        {showAll ? (
          <Link href="/editor/signals">Show relevant only</Link>
        ) : (
          <Link href="/editor/signals?all=1">Show all</Link>
        )}
      </p>
      {list.items.length === 0 ? (
        <p>No signals yet. Run the ingest, then reload.</p>
      ) : (
        <ol>
          {list.items.map((signal) => {
            const href = safeHref(signal.canonical_url);
            const points = signal.metadata.points;
            return (
              <li key={signal.id}>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {signal.title}
                  </a>
                ) : (
                  signal.title
                )}
                <div>
                  {hostOf(signal.canonical_url)} · {signal.source} ·{" "}
                  {formatRelative(now, signal.published_at)}
                  {typeof points === "number" ? ` · ${points} points` : ""}
                </div>
                {signal.assessment && (
                  <div>
                    <span>{signal.assessment.category}</span> ·{" "}
                    <span>
                      {formatScore(signal.assessment.relevance_score)}
                    </span>
                    <p>{signal.assessment.summary}</p>
                    <p>Why it matters: {signal.assessment.why_it_matters}</p>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      {list.next_cursor && (
        <a
          href={`/editor/signals?cursor=${encodeURIComponent(list.next_cursor)}${showAll ? "&all=1" : ""}`}
        >
          Older
        </a>
      )}
    </main>
  );
}
