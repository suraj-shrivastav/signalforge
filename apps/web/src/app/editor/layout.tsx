import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Editor",
  robots: { index: false, follow: false },
};

export default function EditorLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <nav aria-label="Editor" className="flex gap-6 border-b border-line p-4">
        <Link href="/editor/signals">Signals</Link>
        <Link href="/editor/triage">Triage</Link>
      </nav>
      {children}
    </>
  );
}
