// TODO(design): design references and global.css are pending; unstyled on purpose.
"use client";

import { REASON_TAGS, type ReasonTag } from "@/lib/api";

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
      <legend>Reason tags</legend>
      {REASON_TAGS.map((tag) => (
        <label key={tag}>
          <input
            type="checkbox"
            checked={selected.includes(tag)}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...selected, tag]
                  : selected.filter((t) => t !== tag),
              )
            }
          />
          {tag}
        </label>
      ))}
    </fieldset>
  );
}
