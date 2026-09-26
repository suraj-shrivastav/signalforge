import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

type Props = { children: ReactNode; href?: string; className?: string };

export function Tag({ children, href, className }: Props) {
  const classes = cx(
    "inline-flex items-center rounded-pill bg-sunken px-3 py-1 text-caption text-muted",
    href && "transition-colors hover:text-ink",
    className,
  );
  if (href) {
    return (
      <a href={href} className={classes}>
        {children}
      </a>
    );
  }
  return <span className={classes}>{children}</span>;
}
