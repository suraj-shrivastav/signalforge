import type { Metadata } from "next";
import {
  Bricolage_Grotesque,
  Fraunces,
  Instrument_Sans,
} from "next/font/google";
import "./globals.css";
import { siteUrl } from "@/lib/site";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

const body = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

const display = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: { default: "SignalForge", template: "%s | SignalForge" },
  description:
    "Short, sourced write-ups on new AI releases, research and tools.",
  alternates: { types: { "application/atom+xml": "/feed.xml" } },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${body.variable} ${fraunces.variable} ${display.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Constant string, no user input: safe for dangerouslySetInnerHTML */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
