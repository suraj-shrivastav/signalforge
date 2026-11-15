# Agent API

How an automation agent runs SignalForge through HTTP. The cron autopilot (`apps/worker/autopilot.py`, see [docs/deploy-cron.md](../deploy-cron.md)) is the main client; Hermes uses the same API for owner commands over Telegram. Send the key in the
`X-Editor-Key` header. Set `AGENT_API_KEY` on the API for a separate, revocable key; the
editor key keeps working. The OpenAPI spec is at `GET /openapi.json` (tag `agent` for the
endpoints below).

## The loop

1. **Collect:** `POST /agent/run/tick` (ingest, assess, cards, research, draft). It runs in the
   background; `GET /agent/runs` shows progress. One run at a time (409 while busy).
2. **Pick topics:** `GET /cards/queue`, then `POST /cards/{id}/decision` with `accepted` or
   `rejected`. Keep `AUTO_PIPELINE_ON_ACCEPT` **false** (the default) when the autopilot runs the
   pipeline: its accepts would start a competing pass inside the API, and the autopilot's next
   stage start would get 409. The autopilot accepts cards itself and then calls the run endpoints.
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
| `close` | the card cannot finish: research failed or came back thin twice (`MAX_RESEARCH_ATTEMPTS`, stage `research_parked`), the draft failed twice (`MAX_DRAFT_ATTEMPTS`, stage `draft_failed`), the draft ended `needs_more_info` (no usable claims, stage `draft_needs_more_info`), or a revise has used all `AUTO_REVIEW_MAX_REDRAFTS` redrafts, failed ones included (stage `revise_exhausted`). Reject it: `POST /cards/{id}/decision` with `{"decision":"rejected","reason_tags":["needs_more_evidence"],"note":"auto-closed: <stage>"}`. Never retry. |
| `wait` | nothing to do: research or the draft is running (stages `researching`, `draft_drafting`). |
| `none` | nothing to do: `rejected`, `unpublished` (the owner took it down; the agent does not publish it again, and an editor publish brings it back) or `complete`. |

Every `next_action` the API can return: `run_research`, `retry_research`, `run_draft`, `retry_draft`, `auto_review`, `run_revise`, `publish`, `attach_images`, `close`, `wait`, `none` (`classify` in `src/signalforge/pipeline_state.py`). `GET /agent/work` leaves out `wait` and `none`.

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

## Ask for a topic

`POST /agent/topics` takes `{"url": "..."}` or `{"query": "plain text"}` (exactly one), an
optional `note` (the angle, passed on to drafting when the card is accepted) and `hot`. It
runs in the background; the outcome is in `GET /agent/runs` under `last.topic`.

- A **URL** is fetched, and its readable text must be at least 400 characters.
- A **query** is searched (Tavily). The first readable page whose URL is not already a signal
  is used; the other hits come back as `alternatives`, so the owner can pick another.
- The page becomes a signal (source `manual`), is assessed (always treated as relevant, the
  owner asked for it) and carded. The result has the card: scores, format, risk flags,
  suggested angle. Without `hot` it stops there. The owner then accepts or rejects it like any
  other card, and whether it can be published shows in research: `needs_more_info` means no.
- With `hot: true` the card is accepted at once, scored above every other card so research
  takes it next, then researched and drafted, outside the daily research cap. Finish with
  `POST /agent/drafts/{card_id}/auto-review?publish=true&force=true` to publish past the pace.

Errors come back as `{"ok": false, "error": "..."}` in the run result, for example the page
could not be fetched, search is not configured, or nothing readable was found.

## One at a time, best first

Research costs money, so it never fans out:

- Research takes the best waiting accepted card first (highest `score`, oldest on a tie). The
  default for `POST /agent/run/research` is 1 card; pass `?limit=N` to take more. `tick` takes
  1 as well (`--research-limit`).
- Only one pipeline run happens at a time. The pass that starts after an accept and any run an
  agent starts share one slot, so a manual run returns 409 while an accept pass is going and
  the other way round. `GET /agent/runs` shows it as stage `auto`.
- With `AUTO_PIPELINE_ON_ACCEPT=true` (off by default, and kept off under the autopilot), each
  accept starts a pass that takes one card. Accepting three cards gives three passes in a row,
  best first, never in parallel.

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

- Before review, the draft stage repairs once: one writer call rewrites or drops each flagged sentence and an overreaching title, then everything is checked again (`stages/draft.py`).
- A flagged dek: revise, with the reason `the dek is flagged: restate the main finding from the claims`.
- More than `AUTO_REVIEW_MAX_FLAGGED_SHARE` (40%) of sentences flagged: revise (`N sentences are flagged (P%), limit 40%`).
- Otherwise every flagged sentence is deleted, a section left empty is removed, then the draft is revised if any of these hold. Each failing check adds its own reason, and all reasons are the note:
  - fewer words than `ceil(band minimum x AUTO_REVIEW_LENGTH_FLOOR_RATIO)`, never below `AUTO_REVIEW_MIN_WORDS` (250): `<words> words after deletions, minimum <floor> for <template>`. The ratio defaults to 0.8 (baseline: below 100% of the template minimum, 38 of 60 published articles; below 80%, 22 of 60). Raise to 1.0 when Milestone 2b deepens research.
  - fewer than `AUTO_REVIEW_MIN_CLAIMS` (3) verified or supported claims: `<n> verified or supported claims, minimum 3`.
  - the dek opens with a word that points back at nothing: `the dek opens with a word that points back at nothing: '<text>'`.
  - a paragraph opens that way, including one a deletion moved to the front: `a paragraph opens with a word that points back at nothing: '<text>'`. The words are This, These, That, Those, Such, It, Its, They, Their.
  - a section under `AUTO_REVIEW_MIN_SECTION_SENTENCES` (2) sentences: `section '<heading>' has <n> sentence(s), minimum 2`.
  - a strong title word no cited claim states: `the title uses '<word>', which no cited claim states`.
  - a dash or banned phrasing: `contains an em dash or an en dash used as a dash`, `contains banned authorship phrasing: '<phrase>'`.
  - a deletion that cannot be made: `cannot fix a flagged sentence: <message>`.
- Pass: approved (and published with `publish=true`). Fail: `revise` with the reasons as the
  note; `POST /agent/run/revise` redrafts with that note. A card gets at most
  `AUTO_REVIEW_MAX_REDRAFTS` (2) redrafts. A redraft that fails (the writer or judge errored)
  keeps the old body and the `revise` status, and its `redraft_failed` event in the review
  log counts as one of them. With the redrafts used up, a failing draft is rejected by
  auto-review, and a card still in `revise` gets `next_action` `close`.

The process note on the public article says an editor reviewed it only when one did. When the draft's `review_note` is `approved by policy` (the auto-review approval), the note is `PUBLISH_PROCESS_NOTE_AUTO` (automated checks, not an editor, approved it); any other approval uses `PUBLISH_PROCESS_NOTE`. `python -m apps.worker.backfill_process_note [--apply]` rewrites the note on articles already published that way (dry run by default). `python -m apps.worker.quality_report --days N` prints a read-only readability and length report on published articles.

Every automatic edit and decision is in the draft's review log with `actor` (`agent` or
`editor`). `POST /editor/articles/{slug}/unpublish` takes an article down.

## Kill switch and slot lease

A pause stops the agent without revoking its key. While paused, `POST /agent/run/{stage}`,
`POST /agent/publish-next`, `POST /agent/topics` and `POST /editor/drafts/{id}/publish` with
the agent key return **423**; `auto-review?publish=true` still reviews and approves
but does not publish (`queued: true`). The auto pipeline after an accept skips while paused (the decision is still recorded). The old cron entry point `python -m apps.worker.tick` exits 0 without running anything. Reads and publishes with the editor key are not affected: the editor key is the owner's manual override. Never blocked by a pause: `GET /agent/runs`, `/agent/work`, `/agent/pipeline`, every `/agent/controls*` call, card decisions, image attach and upload, unpublish, and auto-review without `publish=true`. A breaker pause (`minutes` set) stops counting as paused once `paused_until` passes, with no resume call.

| Call | Does |
|---|---|
| `GET /agent/controls` | `{paused, paused_reason, paused_by, paused_until, slot, slot_status, slot_failures}` |
| `POST /agent/controls/pause` | `{"reason": "...", "minutes": null}`. `minutes` set is a breaker pause that lifts itself; without it the pause holds until resumed. Sends a webhook alert if `ALERT_WEBHOOK_URL` is set. |
| `POST /agent/controls/resume` | clears the pause |
| `POST /agent/controls/slot/claim` | `{"slot": "2026-11-15-06", "lease_minutes": 120, "holder": "<id>"}` returns `{claimed, slot, failures}`; `claimed` is false if the slot is held or done. `holder` is optional (max 64 chars, `[A-Za-z0-9_-]`): the same holder asking again while its own lease runs gets `claimed: true` with the lease and failures unchanged, so a client whose reply was lost can retry safely. Finishing or releasing the slot clears it. |
| `POST /agent/controls/slot/finish` | `{"slot": "...", "ok": true}` ends the lease. `ok: false` counts one failure. `{"slot": "...", "ok": false, "release": true}` is for a pause: a running slot ends as `failed` with the lease cleared and `slot_failures` unchanged, so it can be claimed again and does not count toward the 3-failure limit. |

Pause and resume record `paused_by` as `editor` or `agent`, by the key used.

## Limits

The judge model is small and noisy, so automatic approval can let a wrong sentence through.
Deleting flagged sentences and requiring verified claims lowers the risk but does not remove it.
Pause it with `POST /agent/controls/pause`, or revoke `AGENT_API_KEY`.
