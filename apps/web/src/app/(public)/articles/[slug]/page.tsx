import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Container } from "@/components/layout/Container";
import { Prose } from "@/components/layout/Prose";
import { CoverImage } from "@/components/ui/CoverImage";
import { safeHref } from "@/lib/format";
import { fetchPublicArticle } from "@/lib/public";
import {
  articleJsonLd,
  articleMetadata,
  jsonLdString,
  keyFacts,
} from "@/lib/seo";
import { siteUrl } from "@/lib/site";

type Params = { params: Promise<{ slug: string }> };

const DATE = new Intl.DateTimeFormat("en-US", {
  dateStyle: "long",
  timeZone: "UTC",
});

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const article = await fetchPublicArticle(slug);
  if (!article) return { title: "Article not found", robots: { index: false } };
  return articleMetadata(article, siteUrl());
}

export default async function ArticlePage({ params }: Params) {
  const { slug } = await params;
  const article = await fetchPublicArticle(slug);
  if (!article) notFound();
  const site = siteUrl();
  const facts = keyFacts(article);
  const updated =
    DATE.format(new Date(article.modified_at)) !==
    DATE.format(new Date(article.published_at));

  return (
    <Container size="article" className="py-12">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdString(articleJsonLd(article, site)),
        }}
      />
      <article>
        <header>
          <h1 className="text-h1 text-ink">{article.title}</h1>
          <p className="mt-4 text-lead text-muted">{article.dek}</p>
          <p className="mt-4 text-small text-muted">
            By {article.byline} ·{" "}
            <time dateTime={article.published_at}>
              {DATE.format(new Date(article.published_at))}
            </time>
            {updated && (
              <>
                {" "}
                · Updated{" "}
                <time dateTime={article.modified_at}>
                  {DATE.format(new Date(article.modified_at))}
                </time>
              </>
            )}
          </p>
          {article.cover.src && (
            <div className="mt-6">
              <CoverImage
                slug={article.slug}
                alt={article.cover.alt}
                src={article.cover.src}
              />
              {article.cover.credit && (
                <p className="mt-1 text-caption text-muted">
                  {article.cover.credit}
                </p>
              )}
            </div>
          )}
        </header>

        {facts.length > 0 && (
          <section aria-labelledby="key-facts" className="mt-8">
            <h2 id="key-facts" className="text-h3 text-ink">
              Key facts
            </h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              {facts.map((fact, index) => (
                <li key={index}>
                  {fact.text}{" "}
                  {fact.sources.map((source) => (
                    <a
                      key={source.url}
                      href={safeHref(source.url) ?? undefined}
                      rel="noopener noreferrer"
                      className="text-small underline"
                    >
                      [{source.label}]
                    </a>
                  ))}
                </li>
              ))}
            </ul>
          </section>
        )}

        <Prose className="mt-8">
          {article.sections.map((section, index) => (
            <section key={index}>
              <h2>{section.heading}</h2>
              {section.paragraphs.map((paragraph, p) => (
                <p key={p}>{paragraph}</p>
              ))}
            </section>
          ))}
        </Prose>

        {article.editor_analysis && (
          <section aria-labelledby="analysis" className="mt-8">
            <h2 id="analysis" className="text-h3 text-ink">
              Editor&apos;s analysis
            </h2>
            <p className="mt-2">{article.editor_analysis}</p>
          </section>
        )}

        <section aria-labelledby="sources" className="mt-8">
          <h2 id="sources" className="text-h3 text-ink">
            Sources
          </h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            {article.sources.map((source) => {
              const href = safeHref(source.url);
              return (
                <li key={source.url}>
                  {href ? (
                    <a
                      href={href}
                      rel="noopener noreferrer"
                      className="underline"
                    >
                      {source.label}
                    </a>
                  ) : (
                    source.label
                  )}
                </li>
              );
            })}
          </ol>
        </section>
        <p className="mt-8 text-small text-muted">{article.process_note}</p>
      </article>
    </Container>
  );
}
