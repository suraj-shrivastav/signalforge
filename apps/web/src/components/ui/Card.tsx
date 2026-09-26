import type { HTMLAttributes } from "react";
import { cx } from "@/lib/cx";

type Props = HTMLAttributes<HTMLDivElement> & { interactive?: boolean };

export function Card({ interactive = false, className, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={cx(
        "bg-surface border border-line rounded-card transition-shadow",
        interactive && "hover:shadow-hover",
        className,
      )}
    />
  );
}
