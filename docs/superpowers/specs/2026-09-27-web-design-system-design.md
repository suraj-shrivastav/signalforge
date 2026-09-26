# Web design system and shell (sub-project 1 of 4)

## Context

SignalForge has no frontend. The product needs a public reader site (articles, topics, search) and an editor console (card queue, evidence, draft review). Both share one look: modern, minimal, soft rounded corners, beige/off-white/white/grey, near-black accent only.

The work is split into four sub-projects, each with its own spec, plan and build:

1. **Design system and web shell** (this spec)
2. **Reader site** (home feed, article page, topics, search, RSS; needs new FastAPI read endpoints)
3. **Editor console, queue** (card queue with accept/reject on the existing decision endpoints)
4. **Editor console, evidence and draft review** (needs backend endpoints that do not exist yet; specced after the drafting stage exists)

Order: 1, then 2 and 3 in either order, then 4.

## Decisions

- Stack: Next.js (App Router), TypeScript strict, Tailwind v4, pnpm.
- One app, `apps/web`, with a public route group and an `/editor` route group. One deploy, shared components and tokens.
- Reader v1 features: home feed, article page, topic pages, search. Extras: dark mode, RSS. No newsletter, no evidence panel in v1.
- Reader data comes from new read endpoints on the FastAPI backend (sub-project 2).

## Design rule: single source of styling

All design values live in `apps/web/app/globals.css` as CSS variables: colors, radii, fonts, type scale, spacing, shadows.

- Tailwind v4 `@theme` reads from those variables.
- Components use only token names (`bg-surface`, `rounded-card`, `text-muted`). No hex colors and no arbitrary values (`w-[13px]`) outside `globals.css`.
- Dark mode is a second block in `globals.css` that overrides the same variables. Components do not change.
- A `check:tokens` script fails on hex colors and arbitrary Tailwind values outside `globals.css`. CI runs it.

Changing the palette, radius or font means editing one file.

## Tokens

Light:

| Token | Value |
|---|---|
| page background | `#F5F1EA` |
| surface (cards) | `#FFFFFF` |
| surface sunken | `#EBE6DD` |
| border | `#E0DAD0` |
| text | `#141414` |
| text muted | `#6B675F` |
| accent | near-black (`#141414`); primary buttons solid with off-white text |

Dark: background `#121110`, surface `#1B1A18`, border `#2A2825`, text `#F2EEE6`, muted `#9A958B`.

Shape: radius 16px cards, 12px inputs and buttons, full pill for tags. No sharp corners. No heavy shadows: 1px hairlines, plus `0 1px 2px rgba(0,0,0,.04)` on hover only.

Type: Inter for UI, Source Serif 4 for article headlines and body, loaded through `next/font` and wired to font variables. Scale 13, 15, 17, 20, 28, 40, 56px, tight tracking on large headlines. With no accent color, hierarchy comes from size, weight and spacing.

Spacing: 4px base grid. Article column max 680px. Home grid max 1120px, 3 columns on desktop, 1 on mobile.

The hex values above are the initial values for `globals.css`, the only place they may appear.

## Structure (`apps/web`)

- `app/(public)/`: home, `articles/[slug]`, `topics/[topic]`, `search`, `feed.xml`. Placeholders in this sub-project.
- `app/editor/`: placeholder layout only. Filled in by sub-project 3.
- `app/design/`: showcase page rendering every component in light and dark.
- `components/ui/`: Button, Tag (pill), Card, Input, Skeleton, ThemeToggle.
- `components/layout/`: Header, Footer, Container, Prose.
- `lib/api.ts`: typed fetch client for the FastAPI backend. Base URL only in this sub-project, no endpoints.

Header: wordmark left; topics, search and theme toggle right. Collapses to a menu on mobile. Sticky with a hairline border.

## Tooling and testing

- ESLint, Prettier, `check:tokens`.
- Vitest and Testing Library for component behavior (Tag, Button, ThemeToggle). ThemeToggle persists its choice and respects `prefers-color-scheme`; both are tested.
- The `/design` page is the visual check. No screenshot tests in v1.
- CI gains a web job: lint, typecheck, tokens check, tests.
- Accessibility: visible focus rings, contrast at least 4.5:1 in both themes (checked against the tokens), semantic landmarks, reduced motion respected.

## Deliverables

1. `apps/web` scaffold that builds and runs.
2. `globals.css` token system with light and dark themes.
3. UI and layout components and the `/design` page.
4. Placeholder reader and editor routes.
5. `check:tokens` script and the CI web job.

## Out of scope

Real data, API endpoints in `lib/api.ts`, editor auth, search logic, RSS content, newsletter, evidence panel. These belong to sub-projects 2 to 4.
