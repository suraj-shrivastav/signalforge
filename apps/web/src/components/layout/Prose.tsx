import type { HTMLAttributes } from "react";
import { cx } from "@/lib/cx";

export function Prose({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("prose", className)} />;
}
