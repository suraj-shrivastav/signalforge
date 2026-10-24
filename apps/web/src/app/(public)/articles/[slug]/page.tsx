import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Link2 } from "lucide-react";
import { PostTile } from "@/components/public/PostTile";
import { PublicHeader } from "@/components/public/PublicHeader";
import { safeHref } from "@/lib/format";
import { fetchPublicArticle, fetchPublicArticlesSafe } from "@/lib/public";
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

const MAX_FACTS = 5;
const FIGURE_AFTER = 1; // inline image sits after the second section

const SHARE_BUTTON =
  "inline-flex size-10 items-center justify-center rounded-pill border border-line bg-surface text-small font-semibold text-ink transition-colors hover:bg-sunken";

// The writer can return a whole section as one paragraph. Break long ones into short
// chunks of whole sentences so the page stays readable.
function chunkParagraph(text: string, per = 3): string[] {
  const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z"(])/);
  if (sentences.length <= per + 1) return [text];
  const chunks: string[] = [];
  for (let i = 0; i < sentences.length; i += per) {
    chunks.push(sentences.slice(i, i + per).join(" "));
  }
  return chunks;
}

function dedupe<T extends { label: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((i) => !seen.has(i.label) && !!seen.add(i.label));
}

function readMinutes(article: {
  dek: string;
  sections: { paragraphs: string[] }[];
}): number {
  const text = [article.dek, ...article.sections.flatMap((s) => s.paragraphs)];
  const words = text.join(" ").split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 220));
}

export default async function ArticlePage({ params }: Params) {
  const { slug } = await params;
  const article = await fetchPublicArticle(slug);
  if (!article) notFound();
  const site = siteUrl();
  const facts = keyFacts(article).slice(0, MAX_FACTS);
  const updated =
    DATE.format(new Date(article.modified_at)) !==
    DATE.format(new Date(article.published_at));
  const url = encodeURIComponent(`${site}/articles/${article.slug}`);
  const title = encodeURIComponent(article.title);
  const more = (await fetchPublicArticlesSafe(8))
    .filter((item) => item.slug !== article.slug)
    .slice(0, 3);
  const next = more[0];

  return (
    <>
      <PublicHeader />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdString(articleJsonLd(article, site)),
        }}
      />
      <article className="mx-auto mt-8 max-w-page px-4 md:px-6">
        <header className="mx-auto max-w-4xl">
          <nav aria-label="Breadcrumb" className="text-caption text-muted">
            <ol className="flex flex-wrap gap-2">
              <li>
                <Link href="/" className="hover:text-ink">
                  Home
                </Link>
              </li>
              <li aria-hidden="true">/</li>
              <li>
                <Link href="/#latest" className="hover:text-ink">
                  Latest
                </Link>
              </li>
              <li aria-hidden="true">/</li>
              <li aria-current="page" className="text-ink">
                Article
              </li>
            </ol>
          </nav>
          <div className="mt-6 flex items-center justify-between gap-4">
            <Link
              href="/"
              aria-label="Back to all articles"
              className={SHARE_BUTTON}
            >
              <ArrowLeft aria-hidden="true" className="size-4" />
            </Link>
            <span className="rounded-pill bg-ink px-3 py-1 text-caption font-semibold uppercase tracking-wider text-page">
              {readMinutes(article)} min read
            </span>
            {next ? (
              <Link
                href={`/articles/${next.slug}`}
                className="inline-flex items-center gap-3 text-caption font-semibold uppercase tracking-wider text-ink"
              >
                Read next
                <span className={SHARE_BUTTON}>
                  <ArrowRight aria-hidden="true" className="size-4" />
                </span>
              </Link>
            ) : (
              <span className="size-10" aria-hidden="true" />
            )}
          </div>
          <h1 className="article-title mt-10 text-center text-4xl text-ink md:text-6xl">
            {article.title}
          </h1>
          <p className="mt-6 text-center text-small text-ink">
            <span className="font-semibold underline underline-offset-4">
              {article.byline}
            </span>
          </p>
          <p className="mt-1 text-center text-caption text-muted">
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
        </header>

        {article.cover.src && (
          <figure className="mx-auto mt-10 max-w-3xl">
            <PostTile article={article} />
            {article.cover.credit && (
              <figcaption className="mt-2 text-caption text-muted">
                {article.cover.credit}
              </figcaption>
            )}
          </figure>
        )}

        <div className="mx-auto mt-12 flex max-w-4xl flex-col gap-8 md:flex-row md:gap-12">
          <aside
            aria-label="Share"
            className="md:sticky md:top-8 md:self-start"
          >
            <ul className="flex gap-2 md:flex-col">
              <li>
                <a
                  className={SHARE_BUTTON}
                  rel="noopener noreferrer"
                  aria-label="Share on X"
                  href={`https://twitter.com/intent/tweet?url=${url}&text=${title}`}
                >
                  X
                </a>
              </li>
              <li>
                <a
                  className={SHARE_BUTTON}
                  rel="noopener noreferrer"
                  aria-label="Share on LinkedIn"
                  href={`https://www.linkedin.com/sharing/share-offsite/?url=${url}`}
                >
                  in
                </a>
              </li>
              <li>
                <a
                  className={SHARE_BUTTON}
                  aria-label="Link to this article"
                  href={`/articles/${article.slug}`}
                >
                  <Link2 aria-hidden="true" className="size-4" />
                </a>
              </li>
            </ul>
          </aside>

          <div className="min-w-0 max-w-article">
            <p className="text-lead font-bold leading-snug text-ink">
              {article.dek}
            </p>

            {facts.length > 0 && (
              <section
                aria-labelledby="key-facts"
                className="mt-8 rounded-tile bg-surface px-6 py-6 md:px-8"
              >
                <h2
                  id="key-facts"
                  className="font-serif text-lead font-semibold text-ink"
                >
                  In short
                </h2>
                <ul className="mt-3 list-disc space-y-2 pl-5 font-serif text-body">
                  {facts.map((fact, index) => (
                    <li key={index}>
                      {fact.text}{" "}
                      {dedupe(fact.sources).map((source) => (
                        <a
                          key={source.url}
                          href={safeHref(source.url) ?? undefined}
                          rel="noopener noreferrer"
                          className="text-small text-muted underline"
                        >
                          [{source.label}]
                        </a>
                      ))}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="article-body mt-10">
              {article.sections.map((section, index) => (
                <section key={index}>
                  <h2>{section.heading}</h2>
                  {section.paragraphs
                    .flatMap((paragraph) => chunkParagraph(paragraph))
                    .map((paragraph, p) => (
                      <p key={p}>{paragraph}</p>
                    ))}
                  {article.figure && index === FIGURE_AFTER && (
                    <figure className="mt-10">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={article.figure.src}
                        alt={article.figure.alt}
                        className="w-full rounded-tile"
                      />
                      {article.figure.caption && (
                        <figcaption className="mt-2 text-caption text-muted">
                          {article.figure.caption}
                        </figcaption>
                      )}
                    </figure>
                  )}
                </section>
              ))}
            </div>

            {article.editor_analysis && (
              <section
                aria-labelledby="analysis"
                className="mt-12 rounded-tile bg-surface px-6 py-6 md:px-8"
              >
                <h2
                  id="analysis"
                  className="font-serif text-lead font-semibold"
                >
                  Editor&apos;s analysis
                </h2>
                <p className="mt-2 font-serif">{article.editor_analysis}</p>
              </section>
            )}

            <section aria-labelledby="sources" className="mt-12">
              <h2
                id="sources"
                className="text-caption font-semibold uppercase tracking-wider text-muted"
              >
                Sources
              </h2>
              <ol className="mt-3 list-decimal space-y-1 pl-5 text-small">
                {article.sources.map((source) => {
                  const href = safeHref(source.url);
                  return (
                    <li key={source.url}>
                      {href ? (
                        <a
                          href={href}
                          rel="noopener noreferrer"
                          className="underline underline-offset-2"
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
            <p className="mt-8 border-t border-line pt-4 text-caption text-muted">
              {article.process_note}
            </p>
          </div>
        </div>
      </article>

      {more.length > 0 && (
        <section
          aria-labelledby="more"
          className="mx-auto mt-20 max-w-page px-4 md:px-6"
        >
          <h2
            id="more"
            className="text-center font-display text-h3 font-bold text-ink"
          >
            Read next
          </h2>
          <ul className="mt-8 grid gap-6 md:grid-cols-3">
            {more.map((item) => (
              <li key={item.slug}>
                <Link href={`/articles/${item.slug}`} className="group block">
                  <PostTile article={item} />
                  <p className="mt-4 text-caption text-muted">
                    <time dateTime={item.published_at}>
                      {DATE.format(new Date(item.published_at))}
                    </time>
                  </p>
                  <h3 className="mt-1 font-display text-lead font-bold leading-tight tracking-tight text-ink group-hover:underline">
                    {item.title}
                  </h3>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
