// TODO(design): design references and global.css are pending; unstyled on purpose.
import { ApiError, fetchQueue, type Card } from "@/lib/api";
import { TriageBoard } from "@/components/triage/TriageBoard";
import { CardView } from "@/components/triage/CardView";

export const dynamic = "force-dynamic";

export default async function TriagePage() {
  let cards: Card[];
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
        <h1>Triage</h1>
        <p role="alert">
          Could not load the queue. Check that the API is running.
        </p>
      </main>
    );
  }
  return (
    <main>
      <h1>Triage</h1>
      {cards.length === 0 ? (
        <p>The queue is empty. Run the cards stage, then reload.</p>
      ) : (
        <TriageBoard>
          {cards.map((card) => (
            <CardView key={card.id} card={card} />
          ))}
        </TriageBoard>
      )}
    </main>
  );
}
