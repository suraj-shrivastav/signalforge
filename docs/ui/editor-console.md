# Editor console: auth and mock content

The editor console lives under `apps/web/src/app/editor`. This doc covers two
things that do not fit `docs/ui/design-system.md`: how the console is gated
behind a password, and the mock article used to build the draft-review view
before real drafts exist.

## Auth flow

The console is a single-editor internal tool, so it is gated by one shared
password rather than per-user accounts. There is no login rate limiting; that
is acceptable for a tool used by one trusted editor and would need revisiting
if the console ever got more editors or was exposed outside a trusted
network.

At a conceptual level:

1. The editor submits the shared password on `/editor/login`.
2. The server action in `apps/web/src/app/editor/login/actions.ts` compares
   it against `EDITOR_UI_PASSWORD`. On a match, it signs a session value
   (the issue time plus an HMAC signature) using a secret from
   `getCookieSecret()` in `apps/web/src/lib/editorAuth.ts`, and sets it in a
   cookie named `sf_editor_session`.
3. Middleware checks that cookie on requests to `/editor/*` (other than the
   login route itself), verifying the signature and that the session has not
   expired, and redirects to `/editor/login` if it is missing, invalid, or
   too old.
4. The cookie is `httpOnly`, `sameSite=lax`, marked `secure` in production,
   and expires after 30 days.

Two environment variables control this, both set via environment and never
committed:

- `EDITOR_UI_PASSWORD`: the shared password checked on login.
- `EDITOR_COOKIE_SECRET`: the HMAC secret used to sign and verify the
  session cookie. If unset, it falls back to `EDITOR_UI_PASSWORD`, so the
  feature works with only one variable configured. A real deployment should
  set both, as independent secrets, so that rotating the login password does
  not also invalidate the signing key (and vice versa).

No secret values, real or placeholder, are documented here or anywhere else
in the repo; they are supplied through the environment at deploy time.

## Mock article convention

`apps/web/src/lib/mock/article.ts` exports `mockArticle`, a hand-written
sample article used only to build and preview the triage draft-review view
before the Phase 4 drafting pipeline exists. The file's own header comment
states this and says it should not be imported anywhere else.

Today, `mockArticle` is imported only by the triage draft-review view. A
future contributor removing it once Phase 4 drafting is live should:

1. Search the codebase for imports of `apps/web/src/lib/mock/article.ts`
   (as of this writing, only the triage draft-review view imports it) and
   confirm that is still the only caller.
2. Replace that import with real draft data from the Phase 4 pipeline.
3. Delete `apps/web/src/lib/mock/article.ts` and any tests or fixtures that
   exist solely to exercise the mock article.

The fixture is deliberately explicit and commented rather than hidden behind
a feature flag, so it stays easy to find and remove when it is no longer
needed.
