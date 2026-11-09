import { ImageResponse } from "next/og";
import { fetchPublicArticle } from "@/lib/public";
import { heroText, kindPalette } from "@/lib/kindPalette";

// 1200x630 PNG share card for every article: social platforms and search engines do not show
// the SVG cover. Colours, chip and hero follow the article kind, as on the on-site tiles. Served at
// /articles/<slug>/og.png (a stable URL, unlike the hashed opengraph-image convention).
const size = { width: 1200, height: 630 };

export async function renderCard(slug: string): Promise<ImageResponse> {
  const article = await fetchPublicArticle(slug);
  const title = article?.title ?? "SignalForge";
  const figure = article ? heroText(article.title, article.headline) : "";
  const { bg, fg } = kindPalette(article?.kind ?? null);
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
        background: bg,
        color: fg,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          fontSize: 30,
          fontWeight: 700,
          letterSpacing: 2,
        }}
      >
        SIGNALFORGE
        {article?.kind ? (
          <div
            style={{
              display: "flex",
              marginLeft: 24,
              padding: "0 20px",
              borderRadius: 999,
              background: fg,
              color: bg,
            }}
          >
            {article.kind.toUpperCase()}
          </div>
        ) : null}
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
