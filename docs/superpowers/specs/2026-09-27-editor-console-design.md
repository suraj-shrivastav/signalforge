# Editor console: auth gate, mock article, restyle (sub-project 3 of 4)

## Context

Sub-project 1 (design system and shell) shipped tokens, theme, UI primitives, and a route shell. `/editor/signals` and `/editor/triage` still render the pre-design-system placeholder markup: plain `<ol><li>` and unstyled divs. There is real data behind them (signals ingested from RSS/HN/arXiv/HF, topic cards from Phase 3), but no article drafting stage exists yet, so the triage view has nothing to show for "the draft" beyond an evidence-free stub.

This spec covers three things together, because the queue restyle is only useful once it's reachable and once the draft view has something real-looking to render:

1. A password gate on `/editor/*`, since there is no other access control today and the route is reachable by anyone with the URL.
2. A mock article fixture, standing in for the drafting stage until Phase 4 (research and writing) exists.
3. A restyle of the signals list and the triage/card queue using the sub-project 1 design system.

## Decisions

- **Auth: a shared password, not per-user accounts.** One editor (the user) uses this console. A login form, a signed cookie, and a middleware check are enough; a user table and password hashing per account would be solving a problem that doesn't exist yet.
- **No new backend auth.** The FastAPI `EDITOR_API_KEY` header (used by the decision-write endpoint) stays as is. The new `EDITOR_UI_PASSWORD` only gates the Next.js UI. The web app's own route handlers still call the API with the existing key from the server side; the browser never sees `EDITOR_API_KEY`.
- **Cookie signing without a session store.** The cookie holds a timestamp and an HMAC-SHA256 signature over it, keyed by a server secret. `middleware.ts` verifies the signature and checks the timestamp is within 30 days, using the Web Crypto API (`crypto.subtle`), which runs in the Edge middleware runtime. No database row, no session table.
- **Mock article lives in one file, clearly marked.** `apps/web/src/lib/mock/article.ts` exports a single `mockArticle` constant. It is imported only by the triage draft-review view, and only until Phase 4 produces real drafts. A code comment says why it exists and what removes it.
- **Signals and topic cards are never mocked.** They come from the real API today (Phase 2a and 3 are live). Only the article body is mocked, since drafting doesn't exist yet.
- **Restyle reuses sub-project 1 primitives.** Button, Tag, Card, Input, Skeleton, CoverImage, Prose. No new primitives; new work is composition (a queue list, a detail panel, a draft-review pane) plus the login form and one new `ArticlePreview` component that wraps `Prose` around the mock article's structured sections.

## Auth flow

1. Visiting any `/editor/*` path with no valid cookie redirects to `/editor/login?next=<path>`.
2. `/editor/login` renders one `Input` (password, type="password") and one `Button` ("Enter"), styled with the design system, on the public layout's shell (no editor nav, since the visitor isn't authenticated yet).
3. Submit posts to `apps/web/src/app/editor/login/actions.ts` (a server action) or a route handler at `apps/web/src/app/api/editor-auth/route.ts` — the plan picks one and documents why. It compares the submitted password to `EDITOR_UI_PASSWORD` (constant-time compare), and on match sets a cookie `sf_editor_session` = `<timestamp>.<base64url hmac>`, httpOnly, `Secure` in production, `SameSite=Lax`, 30-day `Max-Age`. On mismatch it re-renders the form with an inline error ("Wrong password.").
4. `middleware.ts` matches `/editor/:path*`, excluding `/editor/login` itself. It reads the cookie, recomputes the HMAC over the timestamp with the same secret, and checks: signature matches, and `now - timestamp <= 30 days`. Valid → pass through. Invalid or missing → redirect to `/editor/login?next=<original path>`.
5. A "Sign out" control (in the editor nav) clears the cookie and redirects to `/editor/login`.
6. New env vars: `EDITOR_UI_PASSWORD` (the password) and `EDITOR_COOKIE_SECRET` (HMAC key; falls back to `EDITOR_UI_PASSWORD` if unset, but the plan should default it to a separate generated value in `.env.example` — two secrets is safer than one doing double duty). Both documented in `apps/web/.env.local.example` and `.kiro/steering/tech.md`, values never printed by anyone working on this.
7. Public home page (`(public)/page.tsx`) gets a small, unobtrusive link to `/editor` (footer, muted style) — it only leads to the password wall, so it's safe to show.

## Mock article

`apps/web/src/lib/mock/article.ts`:

```ts
// Mock draft for the triage UI. Phase 4 (research + writing) will produce
// real drafts with this same shape; this file goes away once that stage
// writes to the cards table. Do not import this outside the triage
// draft-review view.
export interface MockArticleSection {
  heading: string;
  paragraphs: string[];
}

export interface MockArticleClaim {
  text: string;
  sourceLabel: string;
  sourceUrl: string;
}

export interface MockArticle {
  title: string;
  dek: string;
  template: "news-brief" | "explainer" | "paper-breakdown" | "comparison";
  sections: MockArticleSection[];
  claims: MockArticleClaim[];
  sources: { label: string; url: string }[];
  coverAlt: string;
}

export const mockArticle: MockArticle = { /* ...full "explainer" article, ~800 words, on a plausible AI-news topic, matching the drafting spec's style rules: no em dashes, no first-person claims, no AI-authorship wording... */ };
```

The plan's task writes the full article body (real sentences, not lorem ipsum, following `docs/superpowers/specs/2026-09-27-article-drafting-design.md`'s style rules exactly, since this fixture is also the first place those rules get exercised).

## Restyle

**Signals list** (`/editor/signals`): each signal becomes a `Card` row: title (link, `text-ink`), a `Tag` for `source`, host name, relative time, points if present. Empty and error states use the existing copy but styled with `Card` and `Button` ("Retry" reloads). The "Show all / Show relevant only" toggle becomes a `Button` variant pair.

**Triage / card queue** (`/editor/triage`): three-part layout:
- A queue list (left or top, responsive): each topic card as a compact `Card` with title, relevance/novelty/signal-strength tags, wildcard indicator, and a selected state.
- A detail panel: shows the selected card's summary, reason tags (`Tag` list, from `REASON_TAGS`), decision buttons (`Button` variants: Accept, Reject, Snooze — matching the existing decision endpoint's contract, `apps/web/src/lib/api.ts` unchanged).
- A draft-review pane: renders `mockArticle` through a new `ArticlePreview` component (`Prose`-wrapped sections, a claim list with source links, `CoverImage` with `coverAlt`). This pane is clearly a preview, not tied to the selected card's real content, until Phase 4 exists — a small caption says "Preview draft (sample content)".

Existing decision-timing and reason-tag logic (`decisionTiming.ts`, `ReasonTags.tsx`) is reused, not rewritten; only its presentation changes.

## Testing

- `middleware.test.ts`: valid cookie passes, missing/expired/tampered cookie redirects, `/editor/login` itself is never redirected.
- `route.test.ts` (or server-action test) for the login handler: correct password sets cookie, wrong password shows the error, no user enumeration in the error message.
- Component tests for the restyled signals list and the triage queue/detail/draft-review composition, using existing test patterns from sub-project 1.
- `check:tokens`, typecheck, lint, build all still pass.

## Out of scope

Per-user accounts, password reset, rate limiting on the login attempt (acceptable for a single-editor internal tool; revisit if this ever gets more editors), real drafting output, changes to the FastAPI backend or `EDITOR_API_KEY`.
