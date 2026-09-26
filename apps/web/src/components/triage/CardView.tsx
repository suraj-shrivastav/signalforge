// TODO(design): design references and global.css are pending; unstyled on purpose.
import type { Card } from "@/lib/api";
import { hostOf, safeHref } from "@/lib/format";
import { DecisionBar } from "./DecisionBar";

export function CardView({ card }: { card: Card }) {
  const href = safeHref(card.signal.canonical_url);
  return (
    <article>
      <h2 id={`card-${card.id}`}>{card.signal.title}</h2>
      {card.wildcard && <p>Wildcard</p>}
      {card.status === "snoozed" && <p>Snoozed</p>}
      <p>
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {hostOf(card.signal.canonical_url)}
          </a>
        ) : (
          hostOf(card.signal.canonical_url)
        )}
        {href && " (opens in new tab)"} · {card.signal.source}
      </p>
      <p>{card.what_happened}</p>
      <p>Why it matters: {card.why_it_matters}</p>
      <dl>
        <dt>Suggested angle</dt>
        <dd>{card.suggested_angle}</dd>
        <dt>Coverage gap</dt>
        <dd>{card.coverage_gap}</dd>
        <dt>Format</dt>
        <dd>{card.format}</dd>
        <dt>Score</dt>
        <dd>{card.score.toFixed(2)}</dd>
        <dt>Novelty</dt>
        <dd>{card.novelty.toFixed(2)}</dd>
        <dt>Signal strength</dt>
        <dd>{card.signal_strength.toFixed(2)}</dd>
        <dt>Confidence</dt>
        <dd>{card.confidence.toFixed(2)}</dd>
        <dt>Risk flags</dt>
        <dd>{card.risk_flags.length ? card.risk_flags.join(", ") : "none"}</dd>
      </dl>
      <DecisionBar cardId={card.id} labelledBy={`card-${card.id}`} />
    </article>
  );
}
