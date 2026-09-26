import { useId, type InputHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  error?: string;
  id?: string;
};

export function Input({ label, error, id, className, ...rest }: Props) {
  const auto = useId();
  const inputId = id ?? auto;
  const errorId = `${inputId}-error`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-small font-medium text-ink">
        {label}
      </label>
      <input
        {...rest}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cx(
          "rounded-control border border-line bg-surface px-3 py-2 text-small text-ink",
          className,
        )}
      />
      {error ? (
        <p id={errorId} className="text-caption text-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}
