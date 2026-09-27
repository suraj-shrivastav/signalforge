import type { Card as CardData } from "@/lib/api";
import { hostOf, safeHref } from "@/lib/format";
import { Card } from "@/components/ui/Card";
import { Tag } from "@/components/ui/Tag";
import { mockArticle } from "@/lib/mock/article";
import { ArticlePreview } from "./ArticlePreview";
import { DecisionBar } from "./DecisionBar";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control bg-sunken px-3 py-2">
      <p className="text-caption text-muted">{label}</p>
      <p className="text-small font-medium text-ink">{value}</p>
    </div>
  );
}

export function CardView({ card }: { card: CardData }) {
  const href = safeHref(card.signal.canonical_url);
  return (
    <Card className="p-6">
      <article>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {card.wildcard && <Tag>Wildcard</Tag>}
          {card.status === "snoozed" && <Tag>Snoozed</Tag>}
        </div>
        <h2 id={`card-${card.id}`} className="mb-2 text-h3 text-ink">
          {card.signal.title}
        </h2>
        <p className="mb-4 text-small text-muted">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {hostOf(card.signal.canonical_url)}
            </a>
          ) : (
            hostOf(card.signal.canonical_url)
          )}
          {href && " (opens in new tab)"} · {card.signal.source}
        </p>
        <p className="mb-3 text-small text-ink">{card.what_happened}</p>
        <p className="mb-4 text-small text-ink">
          Why it matters: {card.why_it_matters}
        </p>
        <dl className="mb-4 space-y-2 text-small text-ink">
          <div>
            <dt className="font-medium">Suggested angle</dt>
            <dd className="text-muted">{card.suggested_angle}</dd>
          </div>
          <div>
            <dt className="font-medium">Coverage gap</dt>
            <dd className="text-muted">{card.coverage_gap}</dd>
          </div>
          <div>
            <dt className="font-medium">Format</dt>
            <dd className="text-muted">{card.format}</dd>
          </div>
        </dl>
        <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Score" value={card.score.toFixed(2)} />
          <Stat label="Novelty" value={card.novelty.toFixed(2)} />
          <Stat
            label="Signal strength"
            value={card.signal_strength.toFixed(2)}
          />
          <Stat label="Confidence" value={card.confidence.toFixed(2)} />
        </div>
        <p className="mb-6 text-small text-muted">
          Risk flags:{" "}
          {card.risk_flags.length ? card.risk_flags.join(", ") : "none"}
        </p>
        <DecisionBar cardId={card.id} labelledBy={`card-${card.id}`} />
        <div className="mt-8 border-t border-line pt-6">
          <ArticlePreview article={mockArticle} />
        </div>
      </article>
    </Card>
  );
}
