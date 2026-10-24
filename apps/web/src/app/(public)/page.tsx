import Link from "next/link";
import { PostTile } from "@/components/public/PostTile";
import { PublicHeader } from "@/components/public/PublicHeader";
import { cx } from "@/lib/cx";
import { fetchPublicArticlesSafe } from "@/lib/public";

// Read at request time: SITE_URL and the article list are not known at build. The fetch
// data cache (5 minutes) keeps API load low.
export const dynamic = "force-dynamic";

const DATE = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeZone: "UTC",
});

export default async function Home() {
  const articles = await fetchPublicArticlesSafe(30);
  const [lead, ...rest] = articles;
  return (
    <>
      <PublicHeader />
      <div className="mx-auto max-w-page px-4 md:px-6">
        {lead ? (
          <section
            aria-labelledby="hero"
            className="grid items-center gap-8 py-10 md:grid-cols-2 md:gap-12 md:py-16"
          >
            <div>
              <p className="text-caption text-muted">
                <time dateTime={lead.published_at}>
                  {DATE.format(new Date(lead.published_at))}
                </time>
              </p>
              <h1
                id="hero"
                className="mt-4 font-display text-4xl font-bold uppercase leading-none tracking-tight text-ink md:text-6xl"
              >
                {lead.title}
              </h1>
              <p className="mt-6 max-w-article text-body text-muted">
                {lead.dek}
              </p>
              <Link
                href={`/articles/${lead.slug}`}
                className="mt-8 inline-flex items-center rounded-pill bg-ink px-6 py-3 text-small font-semibold text-page transition-opacity hover:opacity-80"
              >
                Read the article
              </Link>
            </div>
            <Link
              href={`/articles/${lead.slug}`}
              aria-label={lead.title}
              tabIndex={-1}
            >
              <PostTile article={lead} size="lg" />
            </Link>
          </section>
        ) : (
          <section className="py-24 text-center">
            <h1 className="font-display text-4xl font-bold text-ink md:text-6xl">
              SignalForge
            </h1>
            <p className="mt-4 text-muted">
              No articles yet. New write-ups appear here as they are published.
            </p>
          </section>
        )}

        {rest.length > 0 && (
          <section
            id="latest"
            aria-labelledby="latest-h"
            className="border-t border-line pt-10"
          >
            <h2
              id="latest-h"
              className="flex items-center gap-2 text-small font-semibold uppercase tracking-wider text-ink"
            >
              <span aria-hidden="true" className="size-3 rounded-pill bg-ink" />
              Latest
            </h2>
            <ul className="mt-8 grid gap-x-8 gap-y-12 md:grid-cols-3">
              {rest.map((article, index) => (
                <li
                  key={article.slug}
                  className={cx(index === 0 && "md:col-span-2 md:row-span-2")}
                >
                  <Link
                    href={`/articles/${article.slug}`}
                    className="group block"
                  >
                    <PostTile
                      article={article}
                      size={index === 0 ? "lg" : "md"}
                      className={cx(index === 0 && "md:aspect-4/3")}
                    />
                    <p className="mt-4 text-caption text-muted">
                      <time dateTime={article.published_at}>
                        {DATE.format(new Date(article.published_at))}
                      </time>
                    </p>
                    <h3
                      className={cx(
                        "mt-1 font-display font-bold leading-tight tracking-tight text-ink group-hover:underline",
                        index === 0 ? "text-h3 md:text-h2" : "text-lead",
                      )}
                    >
                      {article.title}
                    </h3>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  );
}
