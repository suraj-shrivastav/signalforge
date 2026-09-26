import { Container } from "@/components/layout/Container";
import { Card } from "@/components/ui/Card";

export default function Home() {
  return (
    <Container className="py-16">
      <section aria-labelledby="hero" className="mb-12">
        <h1 id="hero" className="text-display text-ink">
          What changed in AI this week
        </h1>
        <p className="mt-4 max-w-article text-lead text-muted">
          Short, sourced write-ups on new releases, research and tools. Read in
          five minutes, skip the noise.
        </p>
      </section>
      <Card className="p-12 text-center">
        <h2 className="text-h3 text-ink">No articles yet</h2>
        <p className="mt-2 text-muted">Check back soon.</p>
      </Card>
    </Container>
  );
}
