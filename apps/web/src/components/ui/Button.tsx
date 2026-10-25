import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

type Variant = "primary" | "secondary" | "ghost";
type Size = "lg" | "md" | "sm";

type Common = { variant?: Variant; size?: Size; pill?: boolean };
type ButtonProps = Common &
  ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };
type LinkProps = Common &
  AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:opacity-85",
  secondary: "bg-surface border border-line text-ink hover:bg-sunken",
  ghost: "bg-transparent text-ink hover:bg-sunken",
};

const SIZE: Record<Size, string> = {
  lg: "px-6 py-3 text-small font-semibold",
  md: "px-5 py-2 text-small",
  sm: "px-3 py-1 text-caption",
};

export function Button(props: ButtonProps | LinkProps) {
  const {
    variant = "primary",
    size = "md",
    pill = false,
    className,
    ...rest
  } = props;
  const classes = cx(
    "inline-flex items-center justify-center gap-2 font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
    pill ? "rounded-pill" : "rounded-control",
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
