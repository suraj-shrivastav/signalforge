"use client";

import { createContext, useContext, useRef, useState } from "react";
import type { Card as CardData } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Tag } from "@/components/ui/Tag";
import { cx } from "@/lib/cx";
import { CardView } from "./CardView";

const EditorKeyContext = createContext("");

type DecisionClock = { since: () => number; markDecided: () => void };

const LastDecisionContext = createContext<DecisionClock>({
  since: () => 0,
  markDecided: () => {},
});

// Time of the last saved decision (or board mount), shared by all cards.
export function useDecisionClock(): DecisionClock {
  return useContext(LastDecisionContext);
}

export function useEditorKey(): string {
  return useContext(EditorKeyContext);
}

function QueueRow({
  card,
  selected,
  onSelect,
}: {
  card: CardData;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className="block w-full text-left"
    >
      <Card interactive className={cx("p-4", selected && "border-ink")}>
        <p className="mb-2 text-small font-medium text-ink">
          {card.signal.title}
        </p>
        <div className="flex flex-wrap gap-2">
          <Tag>Score {card.score.toFixed(2)}</Tag>
          <Tag>Novelty {card.novelty.toFixed(2)}</Tag>
          <Tag>Signal {card.signal_strength.toFixed(2)}</Tag>
          {card.wildcard && <Tag>Wildcard</Tag>}
          {card.status === "snoozed" && <Tag>Snoozed</Tag>}
        </div>
      </Card>
    </button>
  );
}

// One key field for the whole page. Memory only: never stored or put in a URL.
export function TriageBoard({ cards }: { cards: CardData[] }) {
  const [editorKey, setEditorKey] = useState("");
  const [mountedAt] = useState(() => Date.now());
  const lastDecisionAt = useRef(mountedAt);
  const [clock] = useState<DecisionClock>(() => ({
    since: () => lastDecisionAt.current,
    markDecided: () => {
      lastDecisionAt.current = Date.now();
    },
  }));
  const [selectedId, setSelectedId] = useState(cards[0]?.id);
  const selected = cards.find((card) => card.id === selectedId) ?? cards[0];

  return (
    <LastDecisionContext.Provider value={clock}>
      <EditorKeyContext.Provider value={editorKey}>
        <div className="mb-6 max-w-xs">
          <Input
            label="Editor key"
            type="password"
            autoComplete="off"
            value={editorKey}
            onChange={(e) => setEditorKey(e.target.value)}
          />
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="space-y-3 md:col-span-1">
            {cards.map((card) => (
              <QueueRow
                key={card.id}
                card={card}
                selected={card.id === selected?.id}
                onSelect={() => setSelectedId(card.id)}
              />
            ))}
          </div>
          <div className="md:col-span-2">
            {selected && <CardView key={selected.id} card={selected} />}
          </div>
        </div>
      </EditorKeyContext.Provider>
    </LastDecisionContext.Provider>
  );
}
