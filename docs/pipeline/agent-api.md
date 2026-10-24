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
| `run_research` / `retry_research` | `POST /agent/run/research?retry_failed=true` |
| `run_draft` / `retry_draft` | `POST /agent/run/draft?retry_failed=true` |
| `auto_review` | `POST /agent/drafts/{card_id}/auto-review?publish=true` |
| `run_revise` | `POST /agent/run/revise` |
| `publish` | `POST /editor/drafts/{card_id}/publish` |
| `attach_images` | follow `skills/article-images/SKILL.md` |
| `human_review` | needs a person (draft had no usable claims); skip or reject |
| `wait`, `none` | nothing to do |

## Automatic review

`auto-review` replaces the editor's read-through with rules (`signalforge/auto_review.py`):

- More than `AUTO_REVIEW_MAX_FLAGGED_SHARE` (40%) of sentences flagged: revise.
- Otherwise every flagged sentence is deleted. A flagged dek is replaced by the first unflagged sentence of the article (that sentence leaves the body); if none fits, revise.
- After deletions the draft needs at least `AUTO_REVIEW_MIN_WORDS` (250) words,
  `AUTO_REVIEW_MIN_CLAIMS` (3) verified or supported claims and no dash or banned phrasing.
- Pass: approved (and published with `publish=true`). Fail: `revise` with the reasons as the
  note; `POST /agent/run/revise` redrafts with that note. After `AUTO_REVIEW_MAX_REDRAFTS`
  (2) failed redrafts the draft is rejected.

Every automatic edit and decision is in the draft's review log with `actor` (`agent` or
`editor`). `POST /editor/articles/{slug}/unpublish` takes an article down.

## Limits

The judge model is small and noisy, so automatic approval can let a wrong sentence through.
Deleting flagged sentences and requiring verified claims lowers the risk but does not remove it.
Nothing pauses the agent besides revoking `AGENT_API_KEY`.
