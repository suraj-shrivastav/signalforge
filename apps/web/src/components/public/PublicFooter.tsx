import Link from "next/link";

export function PublicFooter() {
  return (
    <footer className="mt-24 px-4 pb-10 text-center text-small text-muted md:px-6">
      <p>© {new Date().getFullYear()} SignalForge</p>
      <nav aria-label="Footer" className="mt-3 flex justify-center gap-6">
        <Link href="/topics/all" className="underline-offset-4 hover:text-ink hover:underline">
          Topics
        </Link>
        <Link href="/search" className="underline-offset-4 hover:text-ink hover:underline">
          Search
        </Link>
        <a href="/feed.xml" className="underline-offset-4 hover:text-ink hover:underline">
          RSS
        </a>
      </nav>
    </footer>
  );
}
