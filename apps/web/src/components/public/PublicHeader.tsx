import Link from "next/link";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

const LINKS = [
  { href: "/#latest", label: "Latest" },
  { href: "/topics/all", label: "Topics" },
  { href: "/search", label: "Search" },
  { href: "/feed.xml", label: "RSS" },
] as const;

export function PublicHeader() {
  return (
    <header className="px-4 pt-6 md:px-6">
      <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <Link
          href="/"
          className="inline-flex items-center gap-2 font-display text-lead font-extrabold tracking-tight text-ink"
        >
          <span aria-hidden="true" className="size-4 rounded-pill bg-ink" />
          SignalForge
        </Link>
        <div className="flex items-center gap-2">
          <nav aria-label="Main" className="flex gap-1 text-small">
            {LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="rounded-pill px-3 py-1.5 text-ink transition-colors hover:bg-sunken"
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
