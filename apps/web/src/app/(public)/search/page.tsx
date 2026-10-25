import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { PublicHeader } from "@/components/public/PublicHeader";
import { fetchPublicArticlesSafe } from "@/lib/public";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Search",
  robots: { index: false, follow: true },
};

// Plain GET form: filters the published articles by title and dek, no JavaScript needed.
export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const query = q.trim().toLowerCase().slice(0, 100);
  const all = await fetchPublicArticlesSafe(200);
  const results = query
    ? all.filter((a) => `${a.title} ${a.dek}`.toLowerCase().includes(query))
    : [];
  return (
    <>
      <PublicHeader />
      <div className="mx-auto max-w-article px-4 py-12 md:px-6">
        <h1 className="article-title text-4xl text-ink md:text-5xl">
          Search
        </h1>
        <form action="/search" method="get" className="mt-6 flex gap-2">
          <input
            type="search"
            name="q"
            defaultValue={q}
            aria-label="Search articles"
            placeholder="Search articles"
            className="min-w-0 flex-1 rounded-pill border border-line bg-surface px-5 py-3 text-body text-ink"
          />
          <Button type="submit" size="lg" pill>
            Search
          </Button>
        </form>
        {query && (
          <p role="status" className="mt-6 text-small text-muted">
            {results.length} {results.length === 1 ? "result" : "results"} for
            &ldquo;{q.trim()}&rdquo;
          </p>
        )}
        <ul className="mt-4 divide-y divide-line">
          {results.map((article) => (
            <li key={article.slug} className="py-5">
              <Link
                href={`/articles/${article.slug}`}
                className="font-display text-lead font-bold text-ink hover:underline"
              >
                {article.title}
              </Link>
              <p className="mt-1 text-small text-muted">{article.dek}</p>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
