"use client";

import { REASON_TAGS, type ReasonTag } from "@/lib/api";
import { cx } from "@/lib/cx";

export function ReasonTags({
  selected,
  onChange,
  disabled,
}: {
  selected: ReasonTag[];
  onChange: (tags: ReasonTag[]) => void;
  disabled: boolean;
}) {
  return (
    <fieldset disabled={disabled}>
      <legend className="mb-2 text-small font-medium text-ink">
        Reason tags
      </legend>
      <div className="flex flex-wrap gap-2">
        {REASON_TAGS.map((tag) => {
          const checked = selected.includes(tag);
          return (
            <label
              key={tag}
              className={cx(
                "inline-flex cursor-pointer items-center gap-1 rounded-pill px-3 py-1 text-caption transition-colors",
                checked
                  ? "bg-ink text-page"
                  : "bg-sunken text-muted hover:text-ink",
                disabled && "cursor-not-allowed opacity-50",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...selected, tag]
                      : selected.filter((t) => t !== tag),
                  )
                }
                className="sr-only"
              />
              {tag}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
