import Link from "next/link";
import { Container } from "@/components/layout/Container";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-line py-8 text-small text-muted">
      <Container className="flex flex-wrap items-center justify-between gap-4">
        <span>SignalForge</span>
        <nav aria-label="Footer" className="flex gap-6">
          <Link href="/topics/all" className="hover:text-ink">
            Topics
          </Link>
          <Link href="/search" className="hover:text-ink">
            Search
          </Link>
          <a href="/feed.xml" className="hover:text-ink">
            RSS
          </a>
        </nav>
      </Container>
    </footer>
  );
}
