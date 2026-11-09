// Two colours per article kind: `bg` is a soft tile colour from the site theme, `fg` the site ink.
// Kept in step with the signal-card palette in skills/article-images; contrast is tested.
export type KindColors = { bg: string; fg: string };

export const KIND_PALETTE: Record<string, KindColors> = {
  paper: { bg: "#dccdef", fg: "#14201a" },
  benchmark: { bg: "#f6e0a4", fg: "#14201a" },
  model: { bg: "#f4c9cc", fg: "#14201a" },
  release: { bg: "#c3d5ef", fg: "#14201a" },
  tool: { bg: "#bfe0d2", fg: "#14201a" },
  discussion: { bg: "#f1e4d3", fg: "#14201a" },
  news: { bg: "#e8eee4", fg: "#14201a" },
  none: { bg: "#e8eee4", fg: "#14201a" },
};

export function kindPalette(kind: string | null): KindColors {
  if (kind && Object.hasOwn(KIND_PALETTE, kind) && kind !== "none") {
    return KIND_PALETTE[kind];
  }
  return KIND_PALETTE.none;
}

// Subject variant: text before a colon (2 to 24 chars), else the first 3 meaningful words.
function subject(title: string): string {
  const head = title.split(":")[0].trim();
  if (title.includes(":") && head.length >= 2 && head.length <= 24) return head;
  const words = title.split(/\s+/).filter(Boolean);
  while (words.length > 3 && /^(how|why|what|a|the)$/i.test(words[0]))
    words.shift();
  return words.slice(0, 3).join(" ");
}

export function heroText(
  title: string,
  headline: { value: string } | null,
): string {
  return headline ? headline.value : subject(title);
}
