import { renderCard } from "@/lib/opengraph-image-card";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  ctx: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await ctx.params;
  return renderCard(slug);
}
