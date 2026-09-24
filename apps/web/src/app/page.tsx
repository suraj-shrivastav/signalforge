import { fetchSignals } from "@/lib/api";
import { formatRelative, hostOf, safeHref } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  const { cursor } = await searchParams;
  let list;
  try {
    list = await fetchSignals(cursor);
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
              </li>
            );
          })}
        </ol>
      )}
      {list.next_cursor && (
        <a href={`/?cursor=${encodeURIComponent(list.next_cursor)}`}>Older</a>
      )}
    </main>
  );
}
