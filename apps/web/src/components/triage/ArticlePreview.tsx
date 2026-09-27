import { Prose } from "@/components/layout/Prose";
import { Tag } from "@/components/ui/Tag";
import { CoverImage } from "@/components/ui/CoverImage";
import type { MockArticle } from "@/lib/mock/article";

type Props = {
  article: MockArticle;
};

export function ArticlePreview({ article }: Props) {
  return (
    <article>
      <p className="text-caption text-muted">Preview draft (sample content)</p>
      <Tag>{article.template}</Tag>
      <h1>{article.title}</h1>
      <p>{article.dek}</p>
      <CoverImage slug="mock-preview" alt={article.coverAlt} />
      {article.sections.map((section) => (
        <Prose key={section.heading}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </Prose>
      ))}
      <ul>
        {article.claims.map((claim, index) => (
          <li key={index}>
            {claim.text} <a href={claim.sourceUrl}>{claim.sourceLabel}</a>
          </li>
        ))}
      </ul>
    </article>
  );
}
