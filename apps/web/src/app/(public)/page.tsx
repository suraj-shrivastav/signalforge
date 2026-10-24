import Link from "next/link";
import { Bookshelf } from "@/components/public/Bookshelf";
import { PublicHeader } from "@/components/public/PublicHeader";
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
  return (
    <>
      <PublicHeader wordmark={false} />
      <section
        aria-labelledby="hero"
        className="px-4 pb-16 pt-16 text-center md:px-6 md:pt-24"
      >
        <h1
          id="hero"
          className="font-serif text-6xl font-semibold tracking-tight text-ink md:text-8xl"
        >
          SignalForge
        </h1>
        <p className="mt-4 font-serif text-lead text-muted md:text-h3">
          Sourced write-ups on new releases, research and tools
        </p>
      </section>
      <div className="mx-auto max-w-page px-4 md:px-6">
        <Bookshelf articles={articles} />
        <section id="latest" aria-labelledby="latest-h" className="mt-24">
          <h2
            id="latest-h"
            className="text-center font-serif text-h3 font-semibold text-ink"
          >
            Latest
          </h2>
          {articles.length === 0 ? (
            <p className="mt-6 text-center font-serif text-muted">
              No articles yet. The shelves fill as stories are published.
            </p>
          ) : (
            <ul className="mx-auto mt-8 max-w-article divide-y divide-line">
              {articles.map((article) => (
                <li key={article.slug} className="py-6">
                  <p className="text-caption text-muted">
                    <time dateTime={article.published_at}>
                      {DATE.format(new Date(article.published_at))}
                    </time>
                  </p>
                  <h3 className="mt-1 font-serif text-h3 font-semibold text-ink">
                    <Link
                      href={`/articles/${article.slug}`}
                      className="hover:underline"
                    >
                      {article.title}
                    </Link>
                  </h3>
                  <p className="mt-2 font-serif text-body text-muted">
                    {article.dek}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
