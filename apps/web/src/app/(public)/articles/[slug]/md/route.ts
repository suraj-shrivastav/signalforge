import { fetchPublicArticle } from "@/lib/public";
import { articleMarkdown, articleUrl } from "@/lib/seo";
import { siteUrl } from "@/lib/site";

export const revalidate = 300;

// Plain-Markdown twin of an article for agents. The HTML page stays the canonical URL.
export async function GET(
  _request: Request,
  ctx: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await ctx.params;
  const article = await fetchPublicArticle(slug);
  if (!article) return new Response("Not found", { status: 404 });
  const site = siteUrl();
  return new Response(articleMarkdown(article, site), {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      Link: `<${articleUrl(site, slug)}>; rel="canonical"`,
      "X-Robots-Tag": "noindex",
    },
  });
}
