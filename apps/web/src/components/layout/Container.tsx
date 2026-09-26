import type { HTMLAttributes } from "react";
import { cx } from "@/lib/cx";

type Props = HTMLAttributes<HTMLDivElement> & { size?: "page" | "article" };

export function Container({ size = "page", className, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={cx(
        "mx-auto w-full px-4 md:px-6",
        size === "article" ? "max-w-article" : "max-w-page",
        className,
      )}
    />
  );
}
