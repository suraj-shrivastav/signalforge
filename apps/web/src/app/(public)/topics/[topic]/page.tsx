import type { Metadata } from "next";
import Link from "next/link";
import { PostTile } from "@/components/public/PostTile";
import { PublicHeader } from "@/components/public/PublicHeader";
import { fetchPublicArticlesSafe } from "@/lib/public";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "All articles",
  description: "Every SignalForge write-up, newest first.",
};

const DATE = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeZone: "UTC",
});

// Articles have no topic labels yet, so every topic path lists the full archive.
export default async function TopicPage() {
  const articles = await fetchPublicArticlesSafe(200);
  return (
    <>
      <PublicHeader />
      <div className="mx-auto max-w-page px-4 py-12 md:px-6">
        <h1 className="font-display text-4xl font-bold tracking-tight text-ink md:text-5xl">
          All articles
        </h1>
        {articles.length === 0 ? (
          <p className="mt-6 text-muted">No articles yet.</p>
        ) : (
          <ul className="mt-10 grid gap-x-8 gap-y-12 md:grid-cols-3">
            {articles.map((article) => (
              <li key={article.slug}>
                <Link
                  href={`/articles/${article.slug}`}
                  className="group block"
                >
                  <PostTile article={article} />
                  <p className="mt-4 text-caption text-muted">
                    <time dateTime={article.published_at}>
                      {DATE.format(new Date(article.published_at))}
                    </time>
                  </p>
                  <h2 className="mt-1 font-display text-lead font-bold leading-tight tracking-tight text-ink group-hover:underline">
                    {article.title}
                  </h2>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
