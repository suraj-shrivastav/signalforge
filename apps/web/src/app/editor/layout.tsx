import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { logout } from "@/app/editor/login/actions";

export const metadata: Metadata = {
  title: "Editor",
  robots: { index: false, follow: false },
};

export default function EditorLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <nav
        aria-label="Editor"
        className="flex items-center justify-between gap-6 border-b border-line p-4"
      >
        <div className="flex gap-6">
          <Link href="/editor/signals">Signals</Link>
          <Link href="/editor/triage">Triage</Link>
        </div>
        <form action={logout}>
          <Button type="submit" variant="ghost" size="sm">
            Sign out
          </Button>
        </form>
      </nav>
      {children}
    </>
  );
}
