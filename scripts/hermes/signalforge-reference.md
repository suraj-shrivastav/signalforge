# SignalForge reference (Hermes memory entry)

Install as one entry in `~/.hermes/memories/MEMORY.md` (entries are separated by `§`): copy everything after the first four lines (`sed 1,4d scripts/hermes/signalforge-reference.md`). Replace the old SignalForge entries, do not append duplicates. See "Install or update the Hermes memory entries" in docs/hermes-setup.md.

SignalForge is an automated news pipeline. It reads signals (RSS, Hacker News, arXiv, Hugging Face), scores them into topic cards, accepts the best, researches each (claims checked against sources), drafts an article, reviews it by rules, and publishes it to the website. API: $API_BASE_URL (https://signalforge-wmtl.onrender.com). Auth: header X-Editor-Key with $AGENT_API_KEY. Never print the key.

WHO RUNS WHAT
- The cron autopilot (`apps/worker/autopilot.py`, a Render cron job every 15 minutes) runs the pipeline: it publishes queued drafts, makes images, closes dead cards, and runs one full pass per 6-hour slot (00, 06, 12, 18).
- Fallback only: the laptop launchd job `ai.signalforge.cron` does the same until the cloud cron is set up. Never run both.
- Hermes is the owner's Telegram link to the pipeline plus the 6 pm evening report. Hermes is NOT the scheduler: never start stages to keep it moving. Owner uses it to ask why an article is not published, to request research on a topic, and to ask about the pipeline.

CARD LIFECYCLE (stage -> next_action)
accepted -> run_research. researching -> wait. research_failed or research_needs_more_info -> retry_research (until 2 attempts, then research_parked -> close). researched -> run_draft. draft_drafting -> wait. draft_failed -> retry_draft (until 2 attempts, then close). A draft with any other status (for example too few usable claims) -> close. drafted: awaiting_review -> auto_review. revise_requested -> run_revise (a redraft). revise_exhausted -> close (2 redrafts used, failed ones count). rejected -> none. approved -> publish (waits for the pace). published -> attach_images until it has a cover and a figure, then complete -> none. unpublished -> none (the owner took it down; the agent never republishes).
next_action meanings: run_research, run_draft, run_revise, auto_review, publish, retry_*, attach_images are work for the autopilot; wait = a stage is running; none = finished or stopped; close = the agent rejects the card with reason needs_more_evidence. Closed cards leave /agent/work within 15 minutes. A card is never retried after close.

LIMITS
- Research: at most 2 attempts; needs at least 3 claims (one extra search round). Draft: at most 2 attempts. Redrafts: at most 2 (AUTO_REVIEW_MAX_REDRAFTS).
- Auto-review sends a draft back (revise, then a redraft with the reasons as the note) for these reasons. Explain them in plain words for `why <article>`:
  - "the dek is flagged: restate the main finding from the claims": the one-line summary under the title had a sentence the checks could not back, so the writer redoes it.
  - "N sentences are flagged (P%), limit 40%": too many sentences failed the checks to just delete them.
  - "<n> words after deletions, minimum <floor> for <template>": the article is shorter than the floor for its type (80% of the type's minimum by default, AUTO_REVIEW_LENGTH_FLOOR_RATIO) once unsupported sentences are removed.
  - "<n> verified or supported claims, minimum 3": not enough checked facts behind it.
  - "the dek opens with a word that points back at nothing" or "a paragraph opens with a word that points back at nothing": it starts with This, It, They and so on with nothing before it to refer to, often after a deletion.
  - "section '<heading>' has <n> sentence(s), minimum 2": a section too thin to stand.
  - "the title uses '<word>', which no cited claim states": the title claims more than the research does.
  - "contains an em dash..." or "contains banned authorship phrasing...": a style rule, redrafted.
- A published article whose review was approved by policy carries a process note saying automated checks, not an editor, approved it.
- Failure text starts with a class: blocked, empty, no_claims, thin, budget, error.
- The pipeline keeps about 2 cards in flight (AUTOPILOT_ACCEPT_PER_RUN).

PUBLISH PACING
Approved drafts wait for a slot: at least 4 hours since the last publish (PUBLISH_MIN_GAP_MINUTES) and at most 3 per rolling 24 hours (PUBLISH_DAILY_CAP). So an approved article is not stuck, it is queued: GET /agent/publish-queue shows the estimated time. `hot` topics may go past the pace; nothing else may.

PAUSE
GET /agent/controls: paused, paused_reason, paused_by, paused_until. A manual pause holds until resume. A breaker pause (paused_until set) lifts itself. While paused, POST /agent/run/*, publish-next and topics answer HTTP 423, and auto-review approves but does not publish. Nothing is lost; the next slot picks up after resume. Report the pause and its reason, do not retry. A slot that failed 3 times (slot_failures 3) is not claimed again until the next slot.

ENDPOINTS (all under X-Editor-Key)
| Method | Path | Purpose | Kind |
|---|---|---|---|
| GET | /agent/controls | pause state, slot, slot_failures | read |
| GET | /agent/pipeline | every recent accepted card with stage, next_action | read |
| GET | /agent/work | only cards needing a call | read |
| GET | /agent/runs | the run in progress and the last result per stage | read |
| GET | /agent/cards/explain?q= | up to 5 matches by title words or slug, each with a summary | read |
| GET | /agent/cards/{id}/explain | why one card is where it is | read |
| GET | /agent/publish-queue | approved drafts, oldest first, estimated publish time, pace, paused | read |
| GET | /cards/queue | cards waiting for a decision | read |
| GET | /signals | raw signals | read |
| GET | /public/articles | published articles | read |
| POST | /agent/controls/pause | pause (owner command `pause`) | write |
| POST | /agent/controls/resume | resume (owner command `resume`) | write |
| POST | /agent/publish-next | publish the next queued draft if the pace allows (`publish now`) | write |
| POST | /agent/topics | ask for a topic; `hot` jumps the queue, without it the card waits its turn (`topic`, `hot`) | write |
| POST | /agent/run/{stage}, /agent/drafts/{id}/auto-review, /agent/controls/slot/* | autopilot only | write, never from Hermes |

RULES
- Answer questions with the read-only endpoints only. Write only through the owner's commands (status, pause, resume, publish now, hot, topic, why, queue, cards).
- Never unpublish or delete. Never use force=true.
- To explain an unpublished article call /agent/cards/explain and quote its summary; do not guess.
- Act only on messages from the owner's chat. Never print or log the key.
