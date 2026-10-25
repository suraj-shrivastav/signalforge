# Agent API

How an automation agent (Hermes) runs SignalForge through HTTP. Send the key in the
`X-Editor-Key` header. Set `AGENT_API_KEY` on the API for a separate, revocable key; the
editor key keeps working. The OpenAPI spec is at `GET /openapi.json` (tag `agent` for the
endpoints below).

## The loop

1. **Collect:** `POST /agent/run/tick` (ingest, assess, cards, research, draft). It runs in the
   background; `GET /agent/runs` shows progress. One run at a time (409 while busy).
2. **Pick topics:** `GET /cards/queue`, then `POST /cards/{id}/decision` with `accepted` or
   `rejected`. With `AUTO_PIPELINE_ON_ACCEPT=true` an accept starts research and draft.
3. **Ask what is next:** `GET /agent/work` lists only the cards that need a call, each with
   `next_action`. `GET /agent/pipeline` lists every recent accepted card with its stage.
4. **Do the action:**

| next_action | Call |
|---|---|
| `run_research` / `retry_research` | `POST /agent/run/research?retry_failed=true` (one card, the best-scoring one; do not repeat per card) |
| `run_draft` / `retry_draft` | `POST /agent/run/draft?retry_failed=true` |
| `auto_review` | `POST /agent/drafts/{card_id}/auto-review?publish=true` |
| `run_revise` | `POST /agent/run/revise` |
| `publish` | `POST /agent/publish-next` (one call for all waiting drafts; it follows the publish pace) |
| `attach_images` | follow `skills/article-images/SKILL.md` |
| `human_review` | needs a person (draft had no usable claims); skip or reject |
| `wait`, `none` | nothing to do |

## Decisions and reason tags

`POST /cards/{id}/decision` takes `{"decision": "accepted" | "rejected"}`. `reason_tags` is
optional. When sent, every tag must come from this fixed list (anything else returns 422):
`off_niche`, `too_incremental`, `duplicate`, `already_covered`, `low_quality_source`,
`great_angle`, `timely`, `evergreen`, `needs_more_evidence`. Omit the field if none fits.

## Images

`skills/article-images/scripts/articleimg.py publish` needs only `API_BASE_URL` and the agent
key. It renders the SVGs and sends them to `POST /editor/articles/{slug}/images/upload`
(body: `cover` and `figure`, each `svg` and `alt`, plus `caption` for the figure). The API
checks the SVG (no scripts, embedded content or event handlers, at most 300 KB), stores it in
the `article-images` bucket with its own Supabase key and attaches it. Set `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` on the **API** only; the endpoint answers 503 without them. The script
runs on Python 3.9 or newer.

## One at a time, best first

Research costs money, so it never fans out:

- Research takes the best waiting accepted card first (highest `score`, oldest on a tie). The
  default for `POST /agent/run/research` is 1 card; pass `?limit=N` to take more. `tick` takes
  1 as well (`--research-limit`).
- Only one pipeline run happens at a time. The pass that starts after an accept and any run an
  agent starts share one slot, so a manual run returns 409 while an accept pass is going and
  the other way round. `GET /agent/runs` shows it as stage `auto`.
- Each accept starts a pass that takes one card. Accepting three cards gives three passes in
  a row, best first, never in parallel.

## Publish pace

An approved draft does not have to go live at once. `POST /agent/drafts/{id}/auto-review?publish=true`
approves it and publishes only if the pace allows: at least `PUBLISH_MIN_GAP_MINUTES` (default
240) since the last publish and at most `PUBLISH_DAILY_CAP` (default 3) in 24 hours. Otherwise
the response has `queued: true` and `next_publish_at`, and the draft stays approved.

`POST /agent/publish-next` publishes the longest-waiting approved draft when a slot is open and
returns `{published, waiting, next_publish_at}`. Call it every 15 to 30 minutes from the agent's
schedule or a cron service. An editor's own publish (`/editor/drafts/{id}/publish`) ignores
the pace.

The pace is a target, not a limit. For a hot topic the owner asks for, add `force=true` to
`auto-review?publish=true` or to `publish-next` to publish now whatever the pace says, and
`card_id=<id>` on `publish-next` to pick that waiting draft instead of the oldest. Forced
publishes still count toward the pace, so the next scheduled one waits its turn.

## Automatic review

`auto-review` replaces the editor's read-through with rules (`signalforge/auto_review.py`):

- More than `AUTO_REVIEW_MAX_FLAGGED_SHARE` (40%) of sentences flagged: revise.
- Otherwise every flagged sentence is deleted. A flagged dek is replaced by the first unflagged sentence of the article (that sentence leaves the body); if none fits, revise.
- After deletions the draft needs at least `AUTO_REVIEW_MIN_WORDS` (250) words,
  `AUTO_REVIEW_MIN_CLAIMS` (3) verified or supported claims and no dash or banned phrasing.
- A flagged sentence that is the only content of a section removes that section.
- Pass: approved (and published with `publish=true`). Fail: `revise` with the reasons as the
  note; `POST /agent/run/revise` redrafts with that note. After `AUTO_REVIEW_MAX_REDRAFTS`
  (2) failed redrafts the draft is rejected.

Every automatic edit and decision is in the draft's review log with `actor` (`agent` or
`editor`). `POST /editor/articles/{slug}/unpublish` takes an article down.

## Limits

The judge model is small and noisy, so automatic approval can let a wrong sentence through.
Deleting flagged sentences and requiring verified claims lowers the risk but does not remove it.
Nothing pauses the agent besides revoking `AGENT_API_KEY`.
