# Web Design System and Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `apps/web` one token-driven design system (Tailwind v4 plus `globals.css`), light and dark themes, a small UI kit, a layout shell with placeholder reader and editor routes, and CI guards so styling stays in one file.

**Architecture:** `apps/web/src/app/globals.css` is the only place design values live. Tailwind v4 `@theme` maps those variables to utilities (`bg-surface`, `rounded-card`, `text-muted`). Components use utility names only. A `check:tokens` script fails CI on hex colors or arbitrary Tailwind values outside `globals.css`. Dark mode overrides the same variables. The `/design` page renders every component in both themes as the visual check.

**Tech Stack:** Next.js 16 (App Router, `src/` layout), TypeScript strict, Tailwind v4 (`tailwindcss`, `@tailwindcss/postcss`), `next/font` (Inter, Source Serif 4), Vitest with Testing Library and jsdom, npm.

**Spec:** `docs/superpowers/specs/2026-09-27-web-design-system-design.md`. Provided stylesheet: `global.css` at the repo root (to be moved to `apps/web/src/app/globals.css`).

## Global Constraints

- Read `apps/web/AGENTS.md` and `apps/web/CLAUDE.md` first; Next.js 16 differs from older versions, so check `node_modules/next/dist/docs` before using route-group, font, metadata or client/server APIs.
- All design values (colors, radii, fonts, type scale, spacing, shadows) live only in `globals.css`. Components use token utilities only: no hex colors, no `w-[13px]` style arbitrary values, no inline `style`.
- Visual rules from the spec: radius 16px cards, 12px inputs and buttons, full pill tags; no sharp corners; no heavy shadows (1px hairlines, `shadow-hover` on hover only); near-black accent; hierarchy from size, weight and spacing; Inter for UI, Source Serif 4 for article headlines and body.
- Accessibility: visible focus rings, contrast at least 4.5:1 for text pairs in both themes (verified by a test), semantic landmarks, reduced motion respected.
- TypeScript strict, no `any`. ESLint, Prettier, `check:tokens`, typecheck, tests and build all pass. PRs at most 400 changed lines (CSS and generated lockfile lines excluded), squash-merged, Conventional Commits, no AI trailers.
- **No AI signalling on public pages.** Public routes (`(public)` group, `feed.xml`, metadata) never show or embed model names, AI-authorship wording, `model_trail`, prompt versions or verification notes. Such data appears only under `/editor`. A test scans the public route sources for these terms.
- **No em dashes.** No em dash or en dash used as a dash in any UI copy, placeholder text or docs added by this plan.
- **Icons come from `lucide-react`** (add as a dependency in Task 2). Use them for the theme toggle (`Sun`, `Moon`), header (`Search`, `Menu`, `X`), read time (`Clock`) and button arrows (`ArrowRight`). Icons are decorative (`aria-hidden`) unless they are the only content of a control, which then needs an `aria-label`. Size through a token-based class, no arbitrary values.
- **Article page layout is centered:** the article column sits centered on the page, and the header block (tags, title, dek, byline, cover) is center aligned. Body text stays left aligned for readability.
- No real data and no new API endpoints in `lib/api.ts` in this plan. Existing editor pages keep working.

## Rulings made while planning

- **Layout stays `apps/web/src/...` and the package manager stays npm.** The spec says `apps/web/app` and pnpm; the repo already uses `src/` and npm (CI runs `npm ci`). Costs nothing; paths in the spec map one to one under `src/`.
- **Existing pages move under `/editor`.** The spec's public home takes `/`. The current unstyled signals list moves to `/editor/signals` and the triage page to `/editor/triage`. API route handlers (`/api/cards/...`) do not move. Costs a one-time URL change for the editor; sub-project 3 restyles these pages.
- **Raw variable names change to avoid self-reference.** `globals.css` declares `--radius-card: 16px` in `:root` and then `--radius-card: var(--radius-card)` in `@theme`. A variable referencing itself is invalid, and it only works by accident of cascade layer order. The raw tokens are renamed with a `--raw-` prefix for every name that `@theme` re-exports (radii, fonts, shadows, container widths, transitions, z-index), and `@theme` points at the raw names. Colors already use distinct names and stay.
- **Dark `sunken` is `#1A180F`** as supplied (darker than the surface, slightly warm). Kept; revisit on the `/design` page if it looks muddy.
- **Contrast is tested, not asserted in a comment.** The CSS header quotes approximate ratios; a unit test computes them from the actual token hex values.

---

## File Structure

- Move `global.css` → `apps/web/src/app/globals.css` (fix raw token names).
- Modify `apps/web/package.json`, `apps/web/postcss.config.mjs` (create), `apps/web/src/app/layout.tsx`, `apps/web/eslint.config.mjs` (if needed), `.github/workflows/ci.yml`.
- Create `apps/web/scripts/check-tokens.mjs`, `apps/web/src/lib/contrast.ts`.
- Create `apps/web/src/components/ui/{Button,Tag,Card,Input,Skeleton,ThemeToggle}.tsx`.
- Create `apps/web/src/components/layout/{Container,Prose,Header,Footer}.tsx`.
- Create routes: `src/app/(public)/{layout,page}.tsx`, `(public)/articles/[slug]/page.tsx`, `(public)/topics/[topic]/page.tsx`, `(public)/search/page.tsx`, `(public)/feed.xml/route.ts`; `src/app/editor/layout.tsx`, `src/app/editor/signals/page.tsx` (moved from `src/app/page.tsx`), `src/app/editor/triage/...` (moved from `src/app/triage`); `src/app/design/page.tsx`.
- Tests beside each unit (`*.test.ts(x)`).

---

### Task 1: Tailwind v4, tokens and the token guard

**Files:**
- Create: `apps/web/postcss.config.mjs`, `apps/web/scripts/check-tokens.mjs`, `apps/web/scripts/check-tokens.test.ts`
- Move and modify: `global.css` → `apps/web/src/app/globals.css`
- Modify: `apps/web/package.json`, `apps/web/src/app/layout.tsx`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: utilities `bg-page`, `bg-surface`, `bg-sunken`, `border-line`, `text-ink`, `text-muted`, `bg-accent`, `text-on-accent`, `rounded-card`, `rounded-control`, `rounded-pill`, `shadow-hover`, `text-caption|small|body|lead|h3|h2|h1|display`, `font-sans`, `font-serif`, `max-w-article`, `max-w-page`; fonts wired as CSS variables `--font-inter` and `--font-source-serif` on `<html>` via `next/font`; `npm run check:tokens` script.

- [ ] **Step 1: Install** `npm i tailwindcss @tailwindcss/postcss postcss` in `apps/web` and add `postcss.config.mjs` with the `@tailwindcss/postcss` plugin (verify the current Tailwind v4 + Next 16 setup in the Tailwind docs and `node_modules/next/dist/docs`).
- [ ] **Step 2: Move and fix `globals.css`.** `mv global.css apps/web/src/app/globals.css`. Rename every raw token that `@theme` re-exports to `--raw-…` (`--raw-radius-card`, `--raw-font-sans`, `--raw-shadow-hover`, `--raw-container-article`, `--raw-transition-fast`, `--raw-z-dropdown`, and so on) and update the `@theme` block and all `var(...)` uses to match. Leave color raw names (`--page-bg`, `--ink`, …) as they are. Keep the file's structure and comments; update the contrast comment to say ratios are verified by test (Task 5).
- [ ] **Step 3: Fonts and layout.** In `layout.tsx` load `Inter` and `Source_Serif_4` with `next/font/google` (`variable: "--font-inter"` and `"--font-source-serif"`, `display: "swap"`), put both variable class names on `<html lang="en">`, import `./globals.css`. Keep metadata.
- [ ] **Step 4: Write the failing token-guard test** (`check-tokens.test.ts`, vitest, node): given a temp directory with a component containing `className="bg-[#fff]"`, `className="w-[13px]"`, `style={{ color: "#123456" }}` and a plain `#141414` string, `checkTokens(dir)` reports each with file and line; a clean component passes; `globals.css` in the scanned tree is exempt. Export `checkTokens(rootDir): { file: string; line: number; rule: string }[]` from `check-tokens.mjs`, and make the CLI exit 1 with a readable list when violations exist.
- [ ] **Step 5: Run it to fail, implement the script** (scan `src/**/*.{ts,tsx,css}` except `globals.css`; rules: hex color literals `#[0-9a-fA-F]{3,8}\b`, Tailwind arbitrary values `\b[a-z-]+-\[[^\]]+\]`, inline `style=`), then run: `npm run check:tokens` (must currently report violations only if the existing unstyled pages contain any; fix them) and add the script to `package.json` as `"check:tokens": "node scripts/check-tokens.mjs"`.
- [ ] **Step 6: CI.** In `.github/workflows/ci.yml` web job add `npm run check:tokens` after lint.
- [ ] **Step 7: Verify:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`. Also open a built page and confirm `document.documentElement` has the two font variables and that `getComputedStyle(document.body).backgroundColor` matches `#F5F1EA` (a one-off manual check is fine; note the result in the report).
- [ ] **Step 8: Commit:** `git commit -m "feat: add Tailwind v4 design tokens and token guard"`

---

### Task 2: Theme toggle

**Files:**
- Create: `apps/web/src/components/ui/ThemeToggle.tsx`, `apps/web/src/lib/theme.ts`, tests `apps/web/src/lib/theme.test.ts`, `apps/web/src/components/ui/ThemeToggle.test.tsx`
- Modify: `apps/web/src/app/layout.tsx`, `apps/web/package.json` (devDependencies `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`), vitest config if needed

**Interfaces:**
- Produces: `type Theme = "light" | "dark" | "system"`; `readStoredTheme(storage: Pick<Storage,"getItem">): Theme`; `resolveTheme(stored: Theme, prefersDark: boolean): "light" | "dark"`; `applyTheme(doc: Document, theme: Theme): void` (sets or removes `data-theme` on `<html>`; `system` removes it so the media query in `globals.css` decides); a tiny inline script constant `THEME_INIT_SCRIPT` that applies the stored theme before first paint; `<ThemeToggle />` client component (button cycling light → dark → system, `aria-label` reflecting the current mode, persisted to `localStorage` under `signalforge-theme`).
- Storage access is wrapped in try/catch (private mode or blocked storage must not throw).

- [ ] **Step 1: Write failing tests:** `readStoredTheme` returns `system` for missing/invalid values and for a storage that throws; `resolveTheme("system", true)` is dark; `applyTheme` sets `data-theme="dark"`, removes the attribute for `system`; the toggle cycles and persists (jsdom, mocked `matchMedia`); it respects `prefers-color-scheme` when nothing is stored; no crash when storage throws.
- [ ] **Step 2:** run to fail; **Step 3:** implement; render `THEME_INIT_SCRIPT` in `layout.tsx` head via `<script dangerouslySetInnerHTML>` (the one permitted use, with a comment: constant string, no user input) and `suppressHydrationWarning` on `<html>`.
- [ ] **Step 4:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run build`. **Step 5: Commit:** `feat: add theme toggle with persisted choice`

---

### Task 3: UI primitives

**Files:**
- Create: `apps/web/src/components/ui/{Button,Tag,Card,Input,Skeleton,CoverImage}.tsx`, tests `Button.test.tsx`, `Tag.test.tsx`, `Input.test.tsx`, `CoverImage.test.tsx`

**Interfaces:**
- Produces (all accept `className` merged via a tiny `cx(...parts)` helper in `src/lib/cx.ts`; no `clsx` dependency):
  - `Button`: props `variant: "primary" | "secondary" | "ghost"` (default primary), `size: "md" | "sm"`, native button props, `type` defaults to `"button"`. Primary: `bg-accent text-on-accent`; secondary: `bg-surface border border-line text-ink`; ghost: transparent. `rounded-control`, `focus-visible` ring comes from the global rule, disabled state reduces opacity and sets `aria-disabled` semantics via the native attribute. Renders an `<a>` when `href` is given (`as` prop or discriminated union; pick one and test both).
  - `Tag`: pill (`rounded-pill`), `bg-sunken text-muted text-caption`; optional `href`.
  - `Card`: `bg-surface border border-line rounded-card`, `hover:shadow-hover` only when `interactive`.
  - `Input`: labelled field (`label` prop required, rendered as a real `<label htmlFor>`), `rounded-control`, error text linked with `aria-describedby`, `aria-invalid`.
  - `CoverImage`: props `slug: string`, `alt: string` (required), optional `src`, optional `ratio: "16/9" | "1/1"`. With `src` it renders `next/image` with the alt text. Without `src` it renders a deterministic token-styled fallback block (`bg-sunken rounded-card`, pattern chosen by a small hash of `slug` from 4 token-based variants, `role="img"` with the alt text). Never renders an empty or broken box. Used by article cards and the article page.
  - `Skeleton`: `bg-sunken rounded-control` block with `aria-hidden` and a reduced-motion-safe pulse (Tailwind `animate-pulse` is fine; the global reduced-motion rule neutralises it).

- [ ] **Step 1: Write failing tests** for Button (default type button, variants apply expected token classes, disabled blocks clicks, renders a link with href), Tag (renders text, link variant), Input (label association, error wiring and `aria-invalid`), CoverImage (fallback when no `src`, same slug gives same variant, alt always present), Card (interactive class only when set). **Step 2:** run to fail; **Step 3:** implement; **Step 4:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`; **Step 5: Commit:** `feat: add UI primitives`

---

### Task 4: Layout components, route groups and placeholders

**Files:**
- Create: `apps/web/src/components/layout/{Container,Prose,Header,Footer}.tsx`, the route files listed in File Structure; tests `Header.test.tsx`
- Move: `src/app/page.tsx` → `src/app/editor/signals/page.tsx`; `src/app/triage/*` → `src/app/editor/triage/*` (update imports; keep `src/app/api/cards/[id]/decision/route.ts` where it is)

**Interfaces:**
- Consumes: primitives and `ThemeToggle`.
- Produces:
  - `Container` (`max-w-page` centered, gutters from tokens; `size="article"` uses `max-w-article`); `Prose` wraps children in the `.prose` class; `Header` (sticky, hairline bottom border `border-line`, wordmark left, nav links Topics and Search plus `ThemeToggle` right; below the `md` breakpoint the links collapse behind a button with `aria-expanded` and `aria-controls`); `Footer` (simple, muted).
  - `(public)/layout.tsx` renders `Header`, `<main id="main">`, `Footer` and a "Skip to content" link as the first focusable element. Placeholders: home shows a short hero and an empty-state `Card` ("No articles yet"); `articles/[slug]`, `topics/[topic]`, `search` render a titled placeholder with `Skeleton`s; `feed.xml/route.ts` returns a valid empty Atom feed with `Content-Type: application/atom+xml`.
  - `editor/layout.tsx`: minimal shell with a "Signals" and "Triage" nav, `noindex` metadata (`robots: { index: false, follow: false }`), no auth yet.
  - Moved pages keep their behavior; only imports and paths change. The unstyled triage components may stay unstyled here (sub-project 3 restyles them), but they must still pass `check:tokens`.

- [ ] **Step 1: Write failing tests:** a test that greps `src/app/(public)`, `src/components/layout` and `feed.xml` sources for `model`, `AI-generated`, `written by AI`, `model_trail`, `prompt_version` and fails on any hit; Header toggles the mobile menu (`aria-expanded` flips, links reachable), skip link is the first tabbable element in the public layout, the feed route returns 200 with the Atom content type and parses as XML, `robots` metadata is noindex for `/editor`.
- [ ] **Step 2:** run to fail; **Step 3:** implement and move pages; grep the repo (`docs/`, `README.md`, `.kiro/steering/tech.md`, `apps/web/src/lib/api.test.ts`, route handler tests) for old URLs `/triage` and update them; **Step 4:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`; start `npm run dev` and confirm `/`, `/editor/signals`, `/editor/triage`, `/feed.xml` respond 200 (stop the server afterwards); **Step 5: Commit:** `feat: add layout shell and reader and editor route groups`

---

### Task 5: Design showcase, contrast test, CI and docs

**Files:**
- Create: `apps/web/src/app/design/page.tsx`, `apps/web/src/lib/contrast.ts`, `apps/web/src/lib/contrast.test.ts`, `docs/ui/design-system.md`
- Modify: `.github/workflows/ci.yml` (only if the web job is missing any of lint, typecheck, `check:tokens`, test, build), `docs/ui/triage-placeholder.md` (point at the new design system and `/editor/triage`)

**Interfaces:**
- Produces: `contrastRatio(hexA: string, hexB: string): number` (WCAG relative-luminance formula); `readTokens(css: string): { light: Record<string,string>; dark: Record<string,string> }` parsing hex values from `:root` and the dark blocks of `globals.css`.
- `/design` renders: color swatches with token names, the type scale (both fonts), every Button variant and size (default, hover state notes, disabled), Tag, Card (plain and interactive), Input (normal and error), Skeleton, ThemeToggle, and a `.prose` sample; it works in both themes and is `noindex`.

- [ ] **Step 1: Write the failing contrast test:** `contrastRatio("#000000", "#ffffff")` is 21; for the real `globals.css` assert at least 4.5 for `ink/page`, `ink/surface`, `muted/page`, `muted/surface`, `on-accent/accent` in light, and `ink/page`, `ink/surface`, `muted/page`, `muted/surface`, `on-accent/accent` in dark. If any pair fails, do NOT weaken the test: change the token in `globals.css` minimally (e.g. darken `--muted`) and record the change and reason in the report and in `docs/ui/design-system.md`.
- [ ] **Step 2:** run to fail, implement, run; **Step 3:** build the `/design` page; **Step 4:** write `docs/ui/design-system.md` (token table, how to add a token, the no-hex/no-arbitrary rule and `check:tokens`, theme mechanism, component list, accessibility checks, what is deferred); **Step 5:** run everything: `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`, and confirm the CI web job runs the same set (`gh` is not needed; read the workflow).
- [ ] **Step 6: Commit:** `feat: add design showcase, contrast test and design system docs`

---

## Acceptance (after all merges)

- [ ] `npm run build` and CI web job pass; `check:tokens` fails when a hex color or `w-[13px]` is added to a component (try it once locally, then revert).
- [ ] Open `/design` in light and dark (toggle and OS setting): tokens look as specified, focus rings are visible on Tab, reduced motion respected.
- [ ] `/` shows the shell; `/editor/signals` and `/editor/triage` still work with the running API; a decision can still be recorded (needs `EDITOR_API_KEY`).
- [ ] Changing `--accent` in `globals.css` alone recolors primary buttons everywhere.

## Self-Review

- **Spec coverage:** stack (Task 1); single source of styling and `check:tokens` (Task 1); tokens light and dark and contrast (Tasks 1, 5); fonts (Task 1); components Button, Tag, Card, Input, Skeleton, ThemeToggle (Tasks 2, 3); Container, Prose, Header, Footer (Task 4); route groups, placeholders and RSS route (Task 4); `/design` (Task 5); Vitest and Testing Library, ThemeToggle persistence and system preference tested (Task 2); CI web job (Tasks 1, 5); `lib/api.ts` base URL only (no change needed, it already reads `API_BASE_URL`); deliverables 1 to 5 map to Tasks 1 to 5. Not covered by design: real data, editor auth, search logic, newsletter, evidence panel (spec's out-of-scope).
- **Placeholders:** Tasks 3 to 5 leave exact class strings to the implementer but pin the token names, variants, props and test cases. The dark `sunken` color and any failing contrast pair are decided during implementation and recorded.
- **Type consistency:** `Theme`, `applyTheme`, `readStoredTheme`, `resolveTheme`, `THEME_INIT_SCRIPT`, `cx`, `contrastRatio` and `readTokens` are named the same wherever used.
- **Known ceilings:** the Google font download happens at build time and needs network access in CI (`next/font/google`); if the build environment blocks it, switch to `next/font/local` with vendored font files. The `check:tokens` scan is regex-based, so it can miss dynamically built class names; it is a guard, not a proof.
