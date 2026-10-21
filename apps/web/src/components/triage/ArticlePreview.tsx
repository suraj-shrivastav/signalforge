import { Prose } from "@/components/layout/Prose";
import { Tag } from "@/components/ui/Tag";
import { CoverImage } from "@/components/ui/CoverImage";
import type { ArticleTemplate, DraftFlag, EditorDraft } from "@/lib/api";
import { safeHref } from "@/lib/format";

const TEMPLATE_NAMES: Record<ArticleTemplate, string> = {
  news_brief: "News brief",
  explainer: "Explainer",
  paper_breakdown: "Paper breakdown",
  comparison: "Comparison",
};

const FLAG_LABELS: Record<DraftFlag["kind"], string> = {
  uncited: "No claim cited",
  number: "Number not in the cited claims",
  unsupported: "The judge does not confirm this",
};

// Marks each flagged sentence inside its paragraph so the editor sees what to check.
function FlaggedText({ text, flags }: { text: string; flags: DraftFlag[] }) {
  const hits = flags
    .map((flag) => ({ flag, at: text.indexOf(flag.text) }))
    .filter((hit) => hit.at >= 0)
    .sort((a, b) => a.at - b.at);
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const { flag, at } of hits) {
    if (at < cursor) continue;
    if (at > cursor) parts.push(text.slice(cursor, at));
    parts.push(
      <mark
        key={at}
        data-flag={flag.kind}
        title={`${FLAG_LABELS[flag.kind]}. ${flag.detail}`}
        className="bg-sunken underline decoration-wavy decoration-accent"
      >
        {flag.text}
      </mark>,
    );
    cursor = at + flag.text.length;
  }
  parts.push(text.slice(cursor));
  return <>{parts}</>;
}

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
      {article.flags.length > 0 && (
        <p role="status" className="text-small">
          {article.flags.length} flagged{" "}
          {article.flags.length === 1 ? "sentence needs" : "sentences need"}{" "}
          your check (highlighted).
        </p>
      )}
      <p>
        <FlaggedText
          text={article.dek}
          flags={article.flags.filter((f) => f.section === -1)}
        />
      </p>
      <CoverImage
        slug={draft.card_id}
        alt={article.cover.alt}
        src={article.cover.src ?? undefined}
      />
      {article.sections.map((section, index) => (
        <Prose key={index}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map((paragraph, p) => (
            <p key={p}>
              <FlaggedText
                text={paragraph}
                flags={article.flags.filter(
                  (f) => f.section === index && f.paragraph === p,
                )}
              />
            </p>
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
