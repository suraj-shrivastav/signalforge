import { ApiError, fetchQueue, type Card as CardData } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { TriageBoard } from "@/components/triage/TriageBoard";

export const dynamic = "force-dynamic";

export default async function TriagePage() {
  let cards: CardData[];
  try {
    cards = await fetchQueue();
  } catch (err) {
    console.error(
      JSON.stringify({
        event: "triage_queue_failed",
        error: err instanceof Error ? err.name : "unknown",
        status: err instanceof ApiError ? err.status : undefined,
        code: err instanceof ApiError ? err.code : undefined,
      }),
    );
    return (
      <main>
        <h1 className="mb-6 text-h2 text-ink">Triage</h1>
        <Card className="p-6">
          <p role="alert" className="text-ink">
            Could not load the queue. Check that the API is running.
          </p>
        </Card>
      </main>
    );
  }
  return (
    <main>
      <h1 className="mb-6 text-h2 text-ink">Triage</h1>
      {cards.length === 0 ? (
        <Card className="p-6">
          <p className="text-ink">
            The queue is empty. Run the cards stage, then reload.
          </p>
        </Card>
      ) : (
        <TriageBoard cards={cards} />
      )}
    </main>
  );
}
