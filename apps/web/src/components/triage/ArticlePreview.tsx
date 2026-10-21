import { Prose } from "@/components/layout/Prose";
import { Tag } from "@/components/ui/Tag";
import { CoverImage } from "@/components/ui/CoverImage";
import type { ArticleTemplate, EditorDraft } from "@/lib/api";
import { safeHref } from "@/lib/format";

const TEMPLATE_NAMES: Record<ArticleTemplate, string> = {
  news_brief: "News brief",
  explainer: "Explainer",
  paper_breakdown: "Paper breakdown",
  comparison: "Comparison",
};

type Props = {
  draft: EditorDraft;
};

export function ArticlePreview({ draft }: Props) {
  const article = draft.draft;
  if (!article) {
    return (
      <div className="text-small text-muted">
        <p>
          Drafting {draft.status === "failed" ? "failed" : "has no body yet"}.
        </p>
        {draft.failure_reason && (
          <p aria-label="Failure reason">{draft.failure_reason}</p>
        )}
      </div>
    );
  }
  return (
    <article>
      <p className="text-caption text-muted">
        Draft for review ({draft.status.replaceAll("_", " ")})
      </p>
      <Tag>{TEMPLATE_NAMES[draft.template]}</Tag>
      <h1>{article.title}</h1>
      <p>{article.dek}</p>
      <CoverImage
        slug={draft.card_id}
        alt={article.cover.alt}
        src={article.cover.src ?? undefined}
      />
      {article.sections.map((section, index) => (
        <Prose key={index}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map((paragraph, p) => (
            <p key={p}>{paragraph}</p>
          ))}
        </Prose>
      ))}
      <h2>Claims</h2>
      <ul>
        {article.claims.map((claim, index) => (
          <li key={index} data-status={claim.status}>
            <Tag>{claim.status}</Tag> {claim.text}{" "}
            {claim.document_indices.map((i) => {
              const source = article.sources[i];
              if (!source) return null;
              const href = safeHref(source.url);
              return href ? (
                <a key={i} href={href} rel="noopener noreferrer">
                  {source.label}
                </a>
              ) : (
                <span key={i}>{source.label}</span>
              );
            })}
          </li>
        ))}
      </ul>
      {draft.review_summary && (
        <section aria-label="Review summary">
          <h2>Review summary</h2>
          <pre className="whitespace-pre-wrap text-small">
            {draft.review_summary}
          </pre>
        </section>
      )}
    </article>
  );
}
