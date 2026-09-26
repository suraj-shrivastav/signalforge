type Tokens = Record<string, string>;

function channel(v: number): number {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`Not a six digit hex color: ${hex}`);
  const n = parseInt(m[1], 16);
  return (
    0.2126 * channel((n >> 16) & 255) +
    0.7152 * channel((n >> 8) & 255) +
    0.0722 * channel(n & 255)
  );
}

export function contrastRatio(hexA: string, hexB: string): number {
  const a = luminance(hexA);
  const b = luminance(hexB);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function declarations(block: string): Tokens {
  const out: Tokens = {};
  const re = /--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g;
  for (const m of block.matchAll(re)) out[m[1]] = m[2];
  return out;
}

function blockAfter(css: string, selector: string): string {
  const start = css.indexOf(selector);
  if (start < 0) return "";
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/** Hex tokens from the light `:root` block and the dark `[data-theme]` block. */
export function readTokens(css: string): { light: Tokens; dark: Tokens } {
  const light = declarations(blockAfter(css, ":root {"));
  const dark = {
    ...light,
    ...declarations(blockAfter(css, '[data-theme="dark"] {')),
  };
  return { light, dark };
}
