import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

type Variant = "primary" | "secondary" | "ghost";
type Size = "md" | "sm";

type Common = { variant?: Variant; size?: Size };
type ButtonProps = Common &
  ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };
type LinkProps = Common &
  AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-on-accent",
  secondary: "bg-surface border border-line text-ink",
  ghost: "bg-transparent text-ink hover:bg-sunken",
};

const SIZE: Record<Size, string> = {
  md: "px-5 py-2 text-small",
  sm: "px-3 py-1 text-caption",
};

export function Button(props: ButtonProps | LinkProps) {
  const { variant = "primary", size = "md", className, ...rest } = props;
  const classes = cx(
    "inline-flex items-center justify-center gap-2 rounded-control font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
    VARIANT[variant],
    SIZE[size],
    className,
  );
  if (rest.href !== undefined) {
    return (
      <a
        {...(rest as AnchorHTMLAttributes<HTMLAnchorElement>)}
        className={classes}
      />
    );
  }
  const { type = "button", ...btn } =
    rest as ButtonHTMLAttributes<HTMLButtonElement>;
  return <button {...btn} type={type} className={classes} />;
}
