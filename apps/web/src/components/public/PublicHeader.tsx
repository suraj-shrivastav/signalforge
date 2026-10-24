import Link from "next/link";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

const LINKS = [
  { href: "/#latest", label: "Latest" },
  { href: "/topics/all", label: "Topics" },
  { href: "/search", label: "Search" },
  { href: "/feed.xml", label: "RSS" },
] as const;

// Centered, quiet navigation. The wordmark only shows on inner pages (the landing page has its own).
export function PublicHeader({ wordmark = true }: { wordmark?: boolean }) {
  return (
    <header className="px-4 pt-6 md:px-6">
      <div className="mx-auto flex max-w-page flex-col items-center gap-3">
        {wordmark && (
          <Link href="/" className="font-serif text-h3 text-ink">
            SignalForge
          </Link>
        )}
        <div className="flex items-center gap-6">
          <nav aria-label="Main" className="flex gap-8 font-serif text-lead">
            {LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-ink transition-opacity hover:opacity-60"
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
