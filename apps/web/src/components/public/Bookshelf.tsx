import Link from "next/link";
import type { PublicSummary } from "@/lib/public";

const PER_SHELF = 10;
const MAX_SHELVES = 3;

function hash(slug: string): number {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return h;
}

function bookClasses(slug: string): string {
  const h = hash(slug);
  return `book book-c${h % 5} book-w${(h >> 3) % 5} book-h${(h >> 6) % 5}`;
}

// Each article is a book on a shelf. The title shows on hover or focus; the list below the
// shelves carries the same links as plain text for readers and crawlers.
export function Bookshelf({ articles }: { articles: PublicSummary[] }) {
  const shelves: PublicSummary[][] = [];
  for (let i = 0; i < MAX_SHELVES; i++) {
    shelves.push(articles.slice(i * PER_SHELF, (i + 1) * PER_SHELF));
  }
  return (
    <div aria-label="Articles on the shelf" className="space-y-14">
      {shelves.map((shelf, index) => (
        <div key={index} className="shelf">
          {shelf.map((article) => (
            <Link
              key={article.slug}
              href={`/articles/${article.slug}`}
              aria-label={article.title}
              className={bookClasses(article.slug)}
            >
              <span className="book-label">{article.title}</span>
            </Link>
          ))}
        </div>
      ))}
    </div>
  );
}
