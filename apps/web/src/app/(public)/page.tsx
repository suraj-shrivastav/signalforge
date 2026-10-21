import Link from "next/link";
import { Container } from "@/components/layout/Container";
import { Card } from "@/components/ui/Card";
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
    <Container className="py-16">
      <section aria-labelledby="hero" className="mb-12">
        <h1 id="hero" className="text-display text-ink">
          What changed this week
        </h1>
        <p className="mt-4 max-w-article text-lead text-muted">
          Short, sourced write-ups on new releases, research and tools. Read in
          five minutes, skip the noise.
        </p>
      </section>
      {articles.length === 0 ? (
        <Card className="p-12 text-center">
          <h2 className="text-h3 text-ink">No articles yet</h2>
          <p className="mt-2 text-muted">Check back soon.</p>
        </Card>
      ) : (
        <ul className="space-y-6">
          {articles.map((article) => (
            <li key={article.slug}>
              <Card className="p-6">
                <h2 className="text-h3 text-ink">
                  <Link href={`/articles/${article.slug}`}>
                    {article.title}
                  </Link>
                </h2>
                <p className="mt-2 text-muted">{article.dek}</p>
                <p className="mt-2 text-caption text-muted">
                  <time dateTime={article.published_at}>
                    {DATE.format(new Date(article.published_at))}
                  </time>
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </Container>
  );
}
