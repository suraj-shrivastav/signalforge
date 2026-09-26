import { Container } from "@/components/layout/Container";
import { CoverImage } from "@/components/ui/CoverImage";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tag } from "@/components/ui/Tag";

export default async function ArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <Container size="article" className="py-12">
      <article>
        <header className="text-center">
          <CoverImage slug={slug} alt="Article cover" />
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Tag>Topic</Tag>
            <Tag>Research</Tag>
          </div>
          <h1 className="mt-4 text-h1 text-ink">Article title</h1>
        </header>
        <div className="mt-8 space-y-4 text-left">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </article>
    </Container>
  );
}
