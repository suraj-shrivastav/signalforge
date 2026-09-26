"use client";

import { Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Container } from "@/components/layout/Container";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { cx } from "@/lib/cx";

const NAV_ID = "site-nav";

export function Header() {
  const [open, setOpen] = useState(false);
  const Icon = open ? X : Menu;
  const link =
    "inline-flex items-center gap-2 text-small text-muted transition-colors hover:text-ink";

  return (
    <header className="sticky top-0 z-sticky border-b border-line bg-page">
      <Container className="relative flex h-16 items-center justify-between">
        <Link href="/" className="text-h3 font-semibold text-ink">
          SignalForge
        </Link>
        <div className="flex items-center gap-2">
          <nav
            id={NAV_ID}
            aria-label="Main"
            className={cx(
              open
                ? "absolute inset-x-0 top-full flex flex-col gap-4 border-b border-line bg-page px-4 py-4"
                : "hidden",
              "md:static md:flex md:flex-row md:items-center md:gap-6 md:border-0 md:p-0",
            )}
          >
            <Link href="/topics/all" className={link}>
              Topics
            </Link>
            <Link href="/search" className={link}>
              <Search aria-hidden="true" className="size-4" />
              Search
            </Link>
          </nav>
          <ThemeToggle />
          <button
            type="button"
            aria-expanded={open}
            aria-controls={NAV_ID}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center justify-center rounded-control p-2 text-ink transition-colors hover:bg-sunken md:hidden"
          >
            <Icon aria-hidden="true" className="size-5" />
          </button>
        </div>
      </Container>
    </header>
  );
}
