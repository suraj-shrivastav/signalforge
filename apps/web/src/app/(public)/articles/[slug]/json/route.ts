import { fetchPublicArticle } from "@/lib/public";
import { articleUrl, keyFacts } from "@/lib/seo";
import { siteUrl } from "@/lib/site";

export const revalidate = 300;

// JSON twin of an article for agents: every claim keeps its sources.
export async function GET(
  _request: Request,
  ctx: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await ctx.params;
  const article = await fetchPublicArticle(slug);
  if (!article) return Response.json({ error: "Not found" }, { status: 404 });
  const canonical = articleUrl(siteUrl(), slug);
  return Response.json(
    { ...article, canonical, key_facts: keyFacts(article) },
    {
      headers: {
        Link: `<${canonical}>; rel="canonical"`,
        "X-Robots-Tag": "noindex",
      },
    },
  );
}
