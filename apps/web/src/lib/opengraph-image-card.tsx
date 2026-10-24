import { ImageResponse } from "next/og";
import { fetchPublicArticle } from "@/lib/public";
import { tileLabel } from "@/lib/tile";

// 1200x630 PNG share card for every article: social platforms and search engines do not show
// the SVG cover. The tile colour follows the same slug hash as the on-site tiles. Served at
// /articles/<slug>/og.png (a stable URL, unlike the hashed opengraph-image convention).
const size = { width: 1200, height: 630 };

const TILES = ["#f4c9cc", "#f6e0a4", "#bfe0d2", "#c3d5ef", "#dccdef"];
const INK = "#14201a";

function hash(slug: string): number {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return h;
}

export async function renderCard(slug: string): Promise<ImageResponse> {
  const article = await fetchPublicArticle(slug);
  const title = article?.title ?? "SignalForge";
  const figure = article ? tileLabel(article.title, article.dek) : "";
  const fontSize = title.length > 90 ? 44 : title.length > 60 ? 52 : 60;
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 72,
        background: TILES[hash(slug) % TILES.length],
        color: INK,
      }}
    >
      <div
        style={{
          display: "flex",
          fontSize: 30,
          fontWeight: 700,
          letterSpacing: 2,
        }}
      >
        SIGNALFORGE
      </div>
      <div
        style={{
          display: "flex",
          fontSize: figure.length > 6 ? 140 : 200,
          fontWeight: 700,
          lineHeight: 1,
        }}
      >
        {figure}
      </div>
      <div
        style={{
          display: "flex",
          fontSize,
          fontWeight: 700,
          lineHeight: 1.15,
        }}
      >
        {title}
      </div>
    </div>,
    size,
  );
}
