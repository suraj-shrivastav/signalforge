import Image from "next/image";
import { cx } from "@/lib/cx";

type Props = {
  slug: string;
  alt: string;
  src?: string;
  ratio?: "16/9" | "1/1";
  className?: string;
};

const VARIANTS = ["cover-v0", "cover-v1", "cover-v2", "cover-v3"] as const;

export function coverVariant(slug: string): string {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return VARIANTS[h % VARIANTS.length];
}

export function CoverImage({
  slug,
  alt,
  src,
  ratio = "16/9",
  className,
}: Props) {
  const box = cx(
    "relative w-full overflow-hidden rounded-card bg-sunken",
    ratio === "16/9" ? "aspect-video" : "aspect-square",
    className,
  );
  if (src) {
    return (
      <div className={box}>
        <Image
          src={src}
          alt={alt}
          fill
          sizes="100vw"
          className="object-cover"
        />
      </div>
    );
  }
  return (
    <div role="img" aria-label={alt} className={cx(box, coverVariant(slug))} />
  );
}
