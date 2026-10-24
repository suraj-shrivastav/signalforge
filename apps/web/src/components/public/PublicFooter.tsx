import Link from "next/link";

export function PublicFooter() {
  return (
    <footer className="mt-24 px-4 pb-10 text-center font-serif text-small text-muted md:px-6">
      <p>© {new Date().getFullYear()} SignalForge</p>
      <nav aria-label="Footer" className="mt-3 flex justify-center gap-6">
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
    </footer>
  );
}
