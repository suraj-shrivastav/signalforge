// TODO(design): design references and global.css are pending; unstyled on purpose.
import { fetchQueue, type Card } from "@/lib/api";
import { CardView } from "@/components/triage/CardView";

export const dynamic = "force-dynamic";

export default async function TriagePage() {
  let cards: Card[];
  try {
    cards = await fetchQueue();
  } catch {
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
        cards.map((card) => <CardView key={card.id} card={card} />)
      )}
    </main>
  );
}
