import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Container } from "@/components/layout/Container";
import { Button } from "@/components/ui/Button";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { logout } from "@/app/editor/login/actions";

export const metadata: Metadata = {
  title: "Editor",
  robots: { index: false, follow: false },
};

const LINKS = [
  { href: "/editor/signals", label: "Signals" },
  { href: "/editor/triage", label: "Triage" },
  { href: "/editor/drafts", label: "Drafts" },
] as const;

export default function EditorLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <nav aria-label="Editor" className="border-b border-line">
        <Container className="flex h-14 items-center justify-between gap-6">
          <div className="flex gap-6 text-small">
            {LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-muted transition-colors hover:text-ink"
              >
                {link.label}
              </Link>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <form action={logout}>
              <Button type="submit" variant="ghost" size="sm">
                Sign out
              </Button>
            </form>
          </div>
        </Container>
      </nav>
      <Container className="py-8">{children}</Container>
    </>
  );
}
