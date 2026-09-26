# SignalForge design system

The web app (`apps/web`) styles everything from one file, `src/app/globals.css`. Components use token names such as `bg-page`, `text-ink` and `rounded-card`. They never use hex colors, arbitrary values or inline styles. The visual reference is `docs/ui/design-preview.html`, and the live reference is the `/design` route (noindex).

## Token table

| Group | Tokens | Notes |
| --- | --- | --- |
| Surfaces | `page`, `surface`, `sunken`, `line` | Backed by `--page-bg`, `--surface-bg`, `--sunken-bg`, `--border-color` |
| Text | `ink`, `muted` | Body and secondary text |
| Accent | `accent`, `on-accent` | Near-black in light, near-white in dark, no hue |
| Radii | `rounded-card` (16px), `rounded-control` (12px), `rounded-pill` | |
| Shadow | `shadow-hover` | The only shadow; flat by default |
| Fonts | `font-sans` (Inter), `font-serif` (Source Serif 4) | Loaded with `next/font/google` |
| Type scale | `text-caption`, `small`, `body`, `lead`, `h3`, `h2`, `h1`, `display` | Size, line height and tracking are set together |
| Spacing | `1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24` | 4px base grid |
| Containers | `max-w-article` (680px), `max-w-page` (1120px) | Gutters 16px mobile, 24px desktop |
| Motion and layers | `--transition-*`, `--z-*` | Reduced motion is honored globally |

Color values live in `:root` (light) and `[data-theme="dark"]` (dark), and are repeated inside a `prefers-color-scheme: dark` block for the system setting.

## Adding a token

1. Add the raw value to `:root` in `globals.css` (and to both dark blocks if it is a color).
2. Map it in the `@theme` block so Tailwind generates a utility.
3. Use the utility in components. If the token is a text or background color, add the pair to the contrast test.

## No hex, no arbitrary values

`npm run check:tokens` scans every `.ts`, `.tsx` and `.css` file under `src` except `globals.css`. It fails on hex colors, arbitrary Tailwind values such as `w-[13px]`, and `style=` attributes. It is regex based, so it can miss class names built dynamically. It is a guard, not a proof. Test files are scanned too, so contrast fixtures build hex strings by concatenation. CI runs it on every pull request.

## Theme mechanism

`THEME_INIT_SCRIPT` runs in the document head before paint and sets `data-theme` on `<html>` from local storage, which avoids a flash. `ThemeToggle` cycles light, dark and system. System removes the stored choice and the `prefers-color-scheme` block applies. Storage failures are tolerated. The helpers are in `src/lib/theme.ts`.

## Components

UI: `Button` (primary, secondary, ghost; md, sm; renders a link when given `href`), `Tag`, `Card` (plain and interactive), `Input` (label, error), `Skeleton`, `ThemeToggle`, `CoverImage` (image or one of four token based fallback patterns chosen from the slug). Layout: `Container` (page or article width), `Prose`, `Header`, `Footer`. Icons come from `lucide-react` only.

## Accessibility checks

- `src/lib/contrast.test.ts` reads the hex values from `globals.css` and requires at least 4.5:1 for ink and muted on page and surface, and on-accent on accent, in both themes.
- Focus rings are global (`:focus-visible`, 2px, ink colored).
- Reduced motion shortens animations and transitions.
- Inputs have labels; errors are linked with `aria-describedby` and `aria-invalid`.
- Manual check: open `/design`, tab through it, and toggle each theme.

Measured ratios: ink on page 16.4 (light) and 16.3 (dark); muted on page 5.0 and 6.3; muted on sunken 4.5 (light) and 6.0 (dark), which is what Tag text uses.

## Token changes made while adding the contrast test

None. Every required pair passed with the supplied values.

## Dark sunken note

The supplied dark `--sunken-bg` is `#1a180f`. It is slightly yellow and almost the same lightness as surface (contrast 1.02 against surface, 1.06 against page). On `/design` it reads as a faint warm tint, so tags, skeletons and cover fallbacks are visible mainly through their borders and patterns rather than fill. Text on it passes (muted 6.0:1). It is acceptable for now; if sunken areas need more separation in dark mode, lighten it in `globals.css` and rerun the contrast test.

## Deferred

Real data on the public pages, editor auth, search, newsletter, the evidence panel, keyboard shortcuts in triage, and a dark mode audit of every future component.
