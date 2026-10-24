// Colour-block tiles stand in for cover images until articles have real ones.

function hash(slug: string): number {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return h;
}

export function tileClass(slug: string): string {
  return `tile-c${hash(slug) % 5}`;
}

// The first figure in the title or dek (e.g. "5.0", "24.3%"), else the first word.
export function tileLabel(title: string, dek: string): string {
  const figure =
    /\d[\d.,]*\s?[%x+]?/.exec(title) ?? /\d[\d.,]*\s?[%x+]?/.exec(dek);
  if (figure) return figure[0].trim();
  return title.split(/\s+/)[0] ?? "";
}
