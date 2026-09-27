# Editor Console: Auth Gate, Mock Article, Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate `/editor/*` behind a shared password, add a realistic mock article fixture for the triage draft-review pane, and restyle the signals list and triage queue with the sub-project 1 design system.

**Architecture:** A signed cookie (HMAC over a timestamp, verified in `middleware.ts` with Web Crypto, no session store) gates every `/editor/*` route except the login page itself. The existing per-request `EDITOR_API_KEY` header flow (typed into `TriageBoard`, sent to the same-origin decision proxy) is untouched — the new password only gates the UI shell, not the API write. A new `mockArticle` fixture stands in for the not-yet-built drafting stage, rendered by a new `ArticlePreview` component. The signals list and triage board are rebuilt with the sub-project 1 primitives (`Button`, `Tag`, `Card`, `Input`, `Skeleton`, `CoverImage`, `Prose`); no new primitives.

**Tech Stack:** Next.js 16 (App Router, Edge middleware, Web Crypto `crypto.subtle`), TypeScript strict, Vitest + Testing Library, npm.

**Spec:** `docs/superpowers/specs/2026-09-27-editor-console-design.md`. Also honor `docs/superpowers/specs/2026-09-27-article-drafting-design.md` (mock article style rules) and `docs/superpowers/specs/2026-09-27-web-design-system-design.md` / `docs/ui/design-system.md` (tokens, primitives).

## Global Constraints

- Read `apps/web/AGENTS.md` first; Next.js 16 middleware, cookies and route-handler APIs differ from older versions — check `node_modules/next/dist/docs`.
- All design values come from the existing tokens (`globals.css`); components use token utilities only, verified by `npm run check:tokens`.
- New env vars: `EDITOR_UI_PASSWORD`, `EDITOR_COOKIE_SECRET`. Never print their values in chat, logs, or commit messages. Document them in `apps/web/.env.local.example` (create if it doesn't exist) and `.kiro/steering/tech.md`.
- The existing `EDITOR_API_KEY` flow (`TriageBoard`'s in-memory key field, `X-Editor-Key` header, `postDecision`) does not change.
- `apps/web/src/lib/api.ts` types (`Card`, `Signal`, `Decision`, `REASON_TAGS`, etc.) do not change; this plan is UI-only.
- Cookie: name `sf_editor_session`, httpOnly, `SameSite=Lax`, `Secure` when `NODE_ENV=production`, 30-day `Max-Age`.
- No em dashes, no AI-authorship wording, anywhere added by this plan (mirrors the design-system plan's rules).
- TypeScript strict, no `any`. ESLint, Prettier, `check:tokens`, typecheck, tests and build all pass. PRs at most 400 changed lines, squash-merged, Conventional Commits, no AI trailers.

---

### Task 1: Signed cookie auth gate

**Files:**
- Create: `apps/web/src/lib/editorAuth.ts`, test `apps/web/src/lib/editorAuth.test.ts`
- Create: `apps/web/src/middleware.ts`, test `apps/web/src/middleware.test.ts`
- Create: `apps/web/src/app/editor/login/page.tsx`, `apps/web/src/app/editor/login/actions.ts`
- Modify: `apps/web/src/app/editor/layout.tsx` (add "Sign out"), `apps/web/src/app/(public)/page.tsx` (footer "Editor" link)
- Create/modify: `apps/web/.env.local.example` (add both new vars with placeholder values, never real ones)

**Interfaces:**
- Produces: `COOKIE_NAME = "sf_editor_session"`; `async function signSession(secret: string, issuedAtMs: number): Promise<string>` returns `"<issuedAtMs>.<base64url-hmac>"`; `async function verifySession(secret: string, cookieValue: string, nowMs: number, maxAgeMs: number): Promise<boolean>` recomputes the HMAC over the extracted timestamp with `crypto.subtle.importKey`/`crypto.subtle.sign` (`HMAC`, `SHA-256`), compares in constant time (`crypto.subtle.verify` or a fixed-length byte compare), and checks `nowMs - issuedAtMs <= maxAgeMs`; `THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000`.
- Consumes (in `middleware.ts` and the login action): `process.env.EDITOR_UI_PASSWORD`, `process.env.EDITOR_COOKIE_SECRET` (falls back to `EDITOR_UI_PASSWORD` if unset — read once via a small `getCookieSecret()` helper in `editorAuth.ts`, do not duplicate the fallback logic).

- [ ] **Step 1: Write failing tests for `editorAuth.ts`**

```ts
import { describe, expect, it } from "vitest";
import { signSession, verifySession, THIRTY_DAYS_MS } from "./editorAuth";

describe("signSession / verifySession", () => {
  it("accepts a session it just signed", async () => {
    const value = await signSession("secret", 1_000);
    await expect(verifySession("secret", value, 1_000, THIRTY_DAYS_MS)).resolves.toBe(true);
  });

  it("rejects a tampered timestamp", async () => {
    const value = await signSession("secret", 1_000);
    const [, sig] = value.split(".");
    await expect(verifySession("secret", `999.${sig}`, 1_000, THIRTY_DAYS_MS)).resolves.toBe(false);
  });

  it("rejects a session signed with a different secret", async () => {
    const value = await signSession("secret-a", 1_000);
    await expect(verifySession("secret-b", value, 1_000, THIRTY_DAYS_MS)).resolves.toBe(false);
  });

  it("rejects an expired session", async () => {
    const value = await signSession("secret", 1_000);
    await expect(verifySession("secret", value, 1_000 + THIRTY_DAYS_MS + 1, THIRTY_DAYS_MS)).resolves.toBe(false);
  });

  it("rejects a malformed cookie value", async () => {
    await expect(verifySession("secret", "not-a-valid-cookie", 1_000, THIRTY_DAYS_MS)).resolves.toBe(false);
  });
});
```

- [ ] **Step 2: Run to fail:** `npm run test -- editorAuth` — expect "Cannot find module './editorAuth'".
- [ ] **Step 3: Implement `editorAuth.ts`.** Use `crypto.subtle` (available in both Node 20+ and the Edge runtime; do not import Node's `crypto` module, which is unavailable in Edge middleware).
- [ ] **Step 4: Run to pass:** `npm run test -- editorAuth`.
- [ ] **Step 5: Write failing middleware tests.** Next's `NextRequest`/`NextResponse` can be constructed directly in a Vitest test (see `node_modules/next/dist/docs` for the current middleware testing pattern — Next 16 may differ from older `next-test-api-route-handler`-style approaches). Cases: request to `/editor/signals` with no cookie → 307/308 redirect to `/editor/login?next=%2Feditor%2Fsignals`; request to `/editor/signals` with a valid cookie → passes through (no redirect); request to `/editor/login` with no cookie → passes through (never redirected); request to `/` or `/api/cards/x/decision` → passes through untouched (matcher excludes them).
- [ ] **Step 6: Run to fail**, then **implement `middleware.ts`** with `export const config = { matcher: ["/editor/:path*"] }`, reading `EDITOR_UI_PASSWORD`/`EDITOR_COOKIE_SECRET` from `process.env`, calling `verifySession`, redirecting via `NextResponse.redirect(new URL(...))` when invalid, and never redirecting `/editor/login`.
- [ ] **Step 7: Run to pass.**
- [ ] **Step 8: Build the login page and action.** `login/page.tsx` is a server component rendering a form (styled `Input` type password, `Button` "Enter"), reading `?next=` from `searchParams`, posting to the server action in `actions.ts`. `actions.ts`'s `login(formData: FormData)`: reads `password`, compares to `process.env.EDITOR_UI_PASSWORD` (throw a clear error if that env var is unset — the plan explicitly does NOT allow an empty/unset password to mean "no gate"), on match calls `signSession`, sets the cookie via `cookies().set(...)` with the constants from Step 1, and redirects to the validated `next` path (default `/editor/signals`; reject any `next` that doesn't start with `/editor/` to avoid an open redirect). On mismatch, re-renders the form with `role="alert"` text "Wrong password." (no user enumeration — same message always).
- [ ] **Step 9: Add "Sign out"** to `editor/layout.tsx`'s nav: a `Button` (ghost variant) that posts to a small route handler or server action clearing the cookie and redirecting to `/editor/login`.
- [ ] **Step 10: Add the public footer link.** In `(public)/page.tsx`'s `Footer` usage (or `Footer.tsx` itself if that's where footer content lives — check first), add a small muted `Tag`-or-plain-link "Editor" pointing at `/editor/signals`.
- [ ] **Step 11:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`. Manually start `npm run dev`, visit `/editor/signals` with no cookie (confirm redirect to login), log in with the real `EDITOR_UI_PASSWORD` from your own `.env.local` (do not paste its value anywhere), confirm access persists across a reload, sign out, confirm it's gated again. Stop the dev server afterward.
- [ ] **Step 12: Commit:** `feat: add password gate for the editor console`

---

### Task 2: Mock article fixture and ArticlePreview component

**Files:**
- Create: `apps/web/src/lib/mock/article.ts`
- Create: `apps/web/src/components/triage/ArticlePreview.tsx`, test `ArticlePreview.test.tsx`

**Interfaces:**
- Produces: `MockArticleSection`, `MockArticleClaim`, `MockArticle` types and the `mockArticle` constant, exactly as shaped in the spec's Mock Article section. `<ArticlePreview article={mockArticle} />` (props: `article: MockArticle`) renders: a caption "Preview draft (sample content)" (`text-caption text-muted`), the `template` as a `Tag`, `title` in a heading, `dek`, a `CoverImage` (`slug="mock-preview"`, `alt={article.coverAlt}`), each section's heading and paragraphs inside `Prose`, and a claims list where each claim's text links to its `sourceUrl` labelled with `sourceLabel`.
- Consumes: `Prose` (`@/components/layout/Prose`), `Tag`, `CoverImage` from sub-project 1.

- [ ] **Step 1: Write the mock article content.** Write a real, complete "explainer" article (~800 words) about a plausible AI-news topic (for example, a real-sounding advance in efficient inference or open model tooling — invent specifics; it must read as genuine coverage, not a stub). Follow `docs/superpowers/specs/2026-09-27-article-drafting-design.md`'s style rules exactly: no em dashes or en-dashes-as-dashes, no first-person or experiential claims, no AI-authorship wording anywhere in the copy, every claim in the `claims` array paired with a plausible `sourceLabel`/`sourceUrl`. 4 to 6 sections. This is the deliverable of this step — write it directly into `article.ts`, not as a placeholder.
- [ ] **Step 2: Write failing test for `ArticlePreview`:**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ArticlePreview } from "./ArticlePreview";
import { mockArticle } from "@/lib/mock/article";

describe("ArticlePreview", () => {
  it("renders the sample caption, title and every section heading", () => {
    render(<ArticlePreview article={mockArticle} />);
    expect(screen.getByText(/preview draft/i)).toBeInTheDocument();
    expect(screen.getByText(mockArticle.title)).toBeInTheDocument();
    for (const section of mockArticle.sections) {
      expect(screen.getByText(section.heading)).toBeInTheDocument();
    }
  });

  it("links every claim to its source", () => {
    render(<ArticlePreview article={mockArticle} />);
    for (const claim of mockArticle.claims) {
      expect(screen.getByRole("link", { name: claim.sourceLabel })).toHaveAttribute("href", claim.sourceUrl);
    }
  });

  it("contains no em dash or en dash", () => {
    const text = document.body.textContent ?? "";
    render(<ArticlePreview article={mockArticle} />);
    expect(document.body.textContent).not.toMatch(/[—–]/);
  });
});
```

- [ ] **Step 3:** run to fail; **Step 4:** implement `ArticlePreview.tsx`; **Step 5:** run to pass; **Step 6:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`; **Step 7: Commit:** `feat: add mock article fixture and preview component`

---

### Task 3: Restyle the signals list

**Files:**
- Modify: `apps/web/src/app/editor/signals/page.tsx`
- Test: `apps/web/src/app/editor/signals/page.test.tsx` (create if none exists; check first)

**Interfaces:**
- Consumes: `Card`, `Tag`, `Button` from `@/components/ui`; `Signal`, `fetchSignals` from `@/lib/api`; `formatRelative`, `formatScore`, `hostOf`, `safeHref` from `@/lib/format` (unchanged).
- Produces: no new exports; same route, same data contract, restyled markup only.

- [ ] **Step 1: Write/extend a failing test** asserting the page renders a `Card` (by role/test-id or a stable class) per signal, that the empty state ("No signals yet...") renders inside a `Card`, and that the API-error state renders a `Button` labelled to reload (a link back to the same route is acceptable — check what the current implementation does and preserve its behavior, just restyled).
- [ ] **Step 2:** run to fail (or confirm it already fails against the new expectations); **Step 3:** rebuild the JSX: each signal as a `Card` (title as a link when `safeHref` returns one, else plain text; a `Tag` for `signal.source`; muted line for host + relative time + points); the toggle ("Show all" / "Show relevant only") as `Button` (secondary/ghost variant, still an anchor via `href`, matching Task 3 of the design-system plan's `Button` `href` support); **Step 4:** run to pass; **Step 5:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`; **Step 6: Commit:** `feat: restyle the signals list with the design system`

---

### Task 4: Restyle the triage queue and wire in the draft-review pane

**Files:**
- Modify: `apps/web/src/components/triage/{TriageBoard,CardView,DecisionBar}.tsx`
- Modify: `apps/web/src/app/editor/triage/page.tsx` (integrate the queue/detail/draft-review layout)
- Tests: extend or add `TriageBoard.test.tsx`, `CardView.test.tsx`, `DecisionBar.test.tsx` (check what already exists first — sub-project Phase 3 may already have some)

**Interfaces:**
- Consumes: `Button`, `Tag`, `Card`, `Input` from `@/components/ui`; `ArticlePreview` and `mockArticle` from Task 2; existing `Card` (data type, from `@/lib/api` — name collides with the `Card` UI primitive, so alias one import, e.g. `import { Card as CardData } from "@/lib/api"` or `import { Card as UICard } from "@/components/ui/Card"`; pick one convention and use it consistently across all four files touched in this task).
- Produces: no changes to `useEditorKey`/`useDecisionClock`/`postDecision`/the decision contract — presentation only.

- [ ] **Step 1: Write/extend failing tests** for: `TriageBoard` still renders its editor-key `Input` (now styled) and provides context unchanged; `CardView` renders wildcard/snoozed state as `Tag`s, the metric `dl` as a compact stat row, and (new) an `ArticlePreview` for the currently-viewed card; `DecisionBar` renders Accept/Reject/Snooze as `Button` variants (e.g. primary/secondary/ghost) and the reason tags via the existing `ReasonTags` component (unchanged) styled with `Tag`.
- [ ] **Step 2:** run to fail; **Step 3: implement.** Restructure `editor/triage/page.tsx` into a responsive two-pane layout: a queue list of compact `Card`s (title, score, novelty/signal-strength/wildcard as small `Tag`s) on the left/top, and on the right/bottom the selected card's full `CardView` (which now also renders `ArticlePreview` below the decision bar, captioned as sample content per Task 2). On mobile (`<768px`), stack: queue above, detail below. Keep all existing behavior (editor key entry, decision posting, snooze/reject/accept, error states) working exactly as before; **Step 4:** run to pass; **Step 5:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`; start `npm run dev`, log in through the Task 1 gate, exercise the triage board end to end (select a card, view its `ArticlePreview`, submit a decision) against the real API if it's running, confirm no console errors, stop the server; **Step 6: Commit:** `feat: restyle the triage queue with the design system`

---

### Task 5: Docs and final pass

**Files:**
- Modify: `.kiro/steering/tech.md` (document `EDITOR_UI_PASSWORD`, `EDITOR_COOKIE_SECRET`, no values), `docs/ui/design-system.md` or a new `docs/ui/editor-console.md` (describe the auth flow and the mock-article convention so a future contributor removing it knows what to look for), `README.md` if it lists env vars
- Delete the stale `// TODO(design): design references and global.css are pending; unstyled on purpose.` comments left in `TriageBoard.tsx`, `CardView.tsx`, `DecisionBar.tsx`, `ReasonTags.tsx` (grep for this exact comment across `apps/web/src` and remove every instance touched by this plan)

- [ ] **Step 1:** grep the repo for the stale TODO comment and any remaining references to the old unstyled state; update or remove.
- [ ] **Step 2:** write the docs described above.
- [ ] **Step 3:** `npm run typecheck && npm run lint && npm run test && npm run check:tokens && npm run format:check && npm run build`.
- [ ] **Step 4: Commit:** `docs: document the editor auth flow and remove stale placeholder notes`

---

## Rulings made while planning

- **One shared password, no per-user accounts.** Matches the spec; a single editor doesn't need account infrastructure.
- **`EDITOR_COOKIE_SECRET` falls back to `EDITOR_UI_PASSWORD` if unset**, so the feature works with one env var set, but the plan documents both so a real deployment sets two independent secrets.
- **Login attempts are not rate-limited.** Acceptable for a single-editor internal tool per the spec's Out of Scope; revisit if this ever gets more editors or is exposed beyond a trusted network.
- **The mock article is explicit and commented**, not hidden behind a flag, so it's obvious to remove once Phase 4 drafting exists.
