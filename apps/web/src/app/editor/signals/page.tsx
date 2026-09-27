import { fetchSignals } from "@/lib/api";
import { formatRelative, formatScore, hostOf, safeHref } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Tag } from "@/components/ui/Tag";

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
        <Card className="p-6">
          <p role="alert" className="text-ink mb-4">
            Could not load signals. Check that the API is running.
          </p>
          <Button href="/editor/signals" variant="secondary">
            Retry
          </Button>
        </Card>
      </main>
    );
  }

  const now = new Date();
  return (
    <main>
      <h1>Signals</h1>
      <div className="mb-6 flex gap-2">
        {showAll ? (
          <Button href="/editor/signals" variant="secondary" size="sm">
            Show relevant only
          </Button>
        ) : (
          <Button href="/editor/signals?all=1" variant="secondary" size="sm">
            Show all
          </Button>
        )}
      </div>
      {list.items.length === 0 ? (
        <Card className="p-6">
          <p className="text-ink">
            No signals yet. Run the ingest, then reload.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {list.items.map((signal) => {
            const href = safeHref(signal.canonical_url);
            const points = signal.metadata.points;
            return (
              <Card key={signal.id} className="p-6">
                <div className="mb-4">
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-ink font-medium hover:underline"
                    >
                      {signal.title}
                    </a>
                  ) : (
                    <div className="text-ink font-medium">{signal.title}</div>
                  )}
                </div>
                <div className="mb-4 flex flex-wrap gap-2">
                  <Tag>{signal.source}</Tag>
                </div>
                <div className="mb-4 text-muted text-small">
                  {hostOf(signal.canonical_url)} ·{" "}
                  {formatRelative(now, signal.published_at)}
                  {typeof points === "number" ? ` · ${points} points` : ""}
                </div>
                {signal.assessment && (
                  <div className="border-t border-line pt-4">
                    <div className="mb-3 text-small">
                      <span className="font-medium text-ink">
                        {signal.assessment.category}
                      </span>{" "}
                      ·{" "}
                      <span className="text-ink">
                        {formatScore(signal.assessment.relevance_score)}
                      </span>
                    </div>
                    <p className="mb-2 text-small text-ink">
                      {signal.assessment.summary}
                    </p>
                    <p className="text-small text-muted">
                      Why it matters: {signal.assessment.why_it_matters}
                    </p>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
      {list.next_cursor && (
        <div className="mt-6">
          <Button
            href={`/editor/signals?cursor=${encodeURIComponent(list.next_cursor)}${showAll ? "&all=1" : ""}`}
            variant="secondary"
          >
            Older
          </Button>
        </div>
      )}
    </main>
  );
}
