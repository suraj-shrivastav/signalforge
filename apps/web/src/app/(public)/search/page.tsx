import { Container } from "@/components/layout/Container";
import { Skeleton } from "@/components/ui/Skeleton";

export default function SearchPage() {
  return (
    <Container className="py-12">
      <h1 className="text-h1 text-ink">Search</h1>
      <div className="mt-8 space-y-4">
        <Skeleton className="h-12" />
        <Skeleton className="h-12" />
      </div>
    </Container>
  );
}
