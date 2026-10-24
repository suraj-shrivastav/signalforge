import Image from "next/image";
import { cx } from "@/lib/cx";
import type { PublicSummary } from "@/lib/public";
import { tileClass, tileLabel } from "@/lib/tile";

type Props = {
  article: Pick<PublicSummary, "slug" | "title" | "dek" | "cover">;
  className?: string;
  size?: "lg" | "md";
};

// A rounded image, or a soft colour block carrying the article's headline figure.
export function PostTile({ article, className, size = "md" }: Props) {
  // Generated covers are drawn 4:3, so they never use the tall tile shape (it would crop them).
  const drawn = article.cover.src?.endsWith(".svg") ?? false;
  const box = cx(
    "relative w-full overflow-hidden rounded-tile",
    size === "lg" && !drawn ? "aspect-4/5" : "aspect-4/3",
    className,
  );
  if (article.cover.src) {
    // Generated covers are SVG: next/image does not optimise them, so use a plain img.
    if (article.cover.src.endsWith(".svg")) {
      return (
        <div className={box}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={article.cover.src}
            alt={article.cover.alt}
            className="absolute inset-0 size-full object-contain"
          />
        </div>
      );
    }
    return (
      <div className={box}>
        <Image
          src={article.cover.src}
          alt={article.cover.alt}
          fill
          sizes="(min-width: 768px) 50vw, 100vw"
          className="object-cover"
        />
      </div>
    );
  }
  return (
    <div
      role="img"
      aria-label={article.cover.alt}
      className={cx(box, tileClass(article.slug), "flex items-end p-6 md:p-8")}
    >
      <span
        aria-hidden="true"
        className={cx(
          "font-display font-extrabold leading-none tracking-tight text-ink",
          size === "lg" ? "text-6xl md:text-8xl" : "text-4xl md:text-5xl",
        )}
      >
        {tileLabel(article.title, article.dek)}
      </span>
    </div>
  );
}
