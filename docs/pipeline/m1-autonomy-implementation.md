# Milestone 1 implementation record: unattended and stoppable

Written for an engineer or agent with no context. The plan is [docs/superpowers/plans/2026-11-15-autonomous-signalforge-roadmap.md](../superpowers/plans/2026-11-15-autonomous-signalforge-roadmap.md); the decision is [ADR-0008](../adr/0008-cloud-cron-autopilot.md). Where this file and the code disagree, the code wins.

## 1. Goal and status

Goal: SignalForge runs with no human at runtime, off the laptop, and the owner can stop it at any time. Milestone 1 ("unattended and stoppable") was merged on 2026-11-15 (PRs #136 to #148). The production database is at alembic revision 0015 (head). Follow-up PRs after the M1 merge: #149 (docs record), #150 and #151 (residual fixes), #152 (claim holder), #153 (Hermes diagnostics). The 7-day soak is pending (owner steps in section 7).

## 2. What shipped, by PR

| PR | Title | What it does | Key files |
|---|---|---|---|
| #136 | docs: autonomous SignalForge roadmap and implementation plan | The plan and the improvement spec. | `docs/superpowers/plans/2026-11-15-autonomous-signalforge-roadmap.md`, `docs/superpowers/specs/2026-11-15-signalforge-improvement.md` |
| #137 | ci: restore migrations and integration job on a throwaway pgvector container | CI runs migrations up and down and the integration tests against a pgvector container. There is no local Postgres. | `.github/workflows/ci.yml` |
| #138 | feat: close dead-end cards instead of waiting on a person | `close` next_action: a card that cannot finish is rejected with `needs_more_evidence`, not parked for a human. | `src/signalforge/pipeline_state.py` |
| #139 | feat: pipeline_controls row for the kill switch and slot lease | Migration 0013, the singleton row, `is_paused`, `slot_id`, `ControlsRepository`. | `src/signalforge/control_policy.py`, `src/signalforge/db/repositories/controls.py`, `src/signalforge/db/models/ops.py`, `.../versions/0013_add_pipeline_controls.py` |
| #140 | feat: webhook alerts for pauses and failed slots | `send_alert` to a Slack- or Discord-compatible webhook; `ALERT_WEBHOOK_URL`; httpx loggers forced to WARNING. | `src/signalforge/alerts.py`, `src/signalforge/core/config.py`, `src/signalforge/core/logging.py` |
| #141 | feat: kill switch and slot lease endpoints; stage runs and publish honour pause | `/agent/controls*` endpoints; 423 on stage runs, publish-next, topics; auto-review stops publishing; run-after-accept skips. | `apps/api/routes/agent.py`, `apps/api/auto_pipeline.py`, `apps/api/deps.py` |
| #142 | feat: model prices and call caps so per-card budgets can trip | `LLM_PRICES`, `BUDGET_MAX_CALLS_PER_TOPIC`, `BUDGET_MAX_CALLS_PER_ARTICLE`. | `src/signalforge/core/config.py`, `src/signalforge/llm/roles.py`, `src/signalforge/llm/gateway.py` |
| #143 | fix: fail stage rows orphaned by a restart so cards retry | Startup sweep fails `running` rows older than 90 minutes. | `src/signalforge/stale_runs.py`, `apps/api/main.py` |
| #144 | fix: bound draft retries so a failing draft closes after two attempts | Migration 0014 `article_drafts.attempts`; `MAX_DRAFT_ATTEMPTS`. | `src/signalforge/pipeline_state.py`, `src/signalforge/db/repositories/article.py`, `.../versions/0014_add_article_draft_attempts.py` |
| #145 | feat: autopilot runs the slot pipeline from any cron host via the agent API | The cron entry point. | `apps/worker/autopilot.py` |
| #146 | docs: cron autopilot replaces launchd; Hermes keeps Telegram control | Cron deploy guide, Hermes Telegram control prompt, evening report reads the API; `skills/` in the Railway image. | `docs/deploy-cron.md`, `scripts/hermes/telegram-control.md`, `infra/railway/api.Dockerfile` |
| #148 | fix: keep unpublished articles down, bound redrafts, pause covers every publish | Unpublished is `none`; failed redrafts count; agent-key editor publish gets 423 when paused; `tick` exits 0 when paused; `.dockerignore` keeps `skills/`; CI builds the image. | `src/signalforge/pipeline_state.py`, `apps/api/routes/articles.py`, `apps/worker/tick.py`, `.dockerignore` |
| #147 | fix: harden autopilot slot handling and correct soak docs | Isolated pre-claim steps, `last[stage].ok` check, 409 retried once, accept on first attempt only, 360-minute lease, one outcome line, child env stripping. | `apps/worker/autopilot.py`, `docs/deploy-cron.md` |

## 3. How it works now

### Control plane

`pipeline_controls` is a one-row table (`id = 1`, seeded by migration 0013). Columns: `paused`, `paused_reason`, `paused_by` (`editor` or `agent`, by the key used), `paused_at`, `paused_until`, `slot`, `slot_status` (`running`, `done`, `failed`), `slot_failures`, `slot_lease_until`, `slot_holder` (migration 0015). Every repository call locks the row (`SELECT ... FOR UPDATE`).

- `is_paused(row, now)` (`src/signalforge/control_policy.py`): false unless `paused`; a pause with no `paused_until` holds until resumed; a pause with `paused_until` (a breaker pause, `minutes` on the pause call, 1 minute to 7 days) stops counting once that time passes.
- `slot_id(now_local)`: `YYYY-MM-DD-HH` with the hour rounded down to 00, 06, 12 or 18 in the autopilot's clock (`AUTOPILOT_TZ`, default UTC).
- `claim_slot(slot, now, lease, holder=None)` (`ControlsRepository`): a leased, running slot asked again by the same non-null `holder` returns its own claim unchanged (lease and failures untouched); otherwise refused when a lease is still running, when this slot is already `done`, or when it has 3 failures. Otherwise it sets `running`, the lease expiry, and keeps the failure count if it is the same slot (a new slot starts at 0). `finish_slot(slot, ok)` sets `done` or `failed`, adds a failure on `ok=false`, and clears the lease and the holder; it ignores a slot that is not the current one.

### Autopilot flow

`apps/worker/autopilot.py`, run by cron every 15 minutes. It needs `API_BASE_URL` and `SIGNALFORGE_KEY` (exit 1 without them) and sends the key as `X-Editor-Key`.

1. `GET /agent/controls`. Paused: log outcome `paused` and exit 0. An error: outcome `failed`, exit 1.
2. Pre-claim steps, each isolated (an exception is logged and the next step still runs; a 423 stops the run as `paused`): `POST /agent/publish-next` (and a site revalidate if something published), the images tick (`articleimg.py auto` as a child process with `DATABASE_URL`, `SUPABASE_*` and every `*_API_KEY` except the agent key removed; a missing script or a non-zero exit only logs a warning), and `close_dead_ends` (reject every `close` card with `needs_more_evidence` and the note `auto-closed: <stage>`).
3. `POST /agent/controls/slot/claim` with the current slot, a per-run `holder` (uuid4 hex) and `lease_minutes=360`; if the call raises it is retried once with the same holder. (A worst-case slot runs about 330 minutes; the API default lease is 120.) Not claimed: outcome `skipped`, exit 0.
4. `run_slot`, on a claimed slot: `tick`; then, only when `failures == 0` (the slot's first attempt), accept `max(0, AUTOPILOT_ACCEPT_PER_RUN - in_flight)` cards, highest `score` first from `GET /cards/queue?limit=50`, where `in_flight` counts `/agent/work` cards whose next_action is `run_research`, `retry_research`, `run_draft`, `retry_draft`, `auto_review`, `run_revise` or `publish`; then up to two rounds of research (`retry_failed=true`, `limit` = waiting cards capped to 1 to 4) and draft (`retry_failed=true`), stopping early once a card awaits review; `revise` if any card is `run_revise`; auto-review up to 3 cards (`publish=true`; a `revise` answer triggers a revise run and a re-review, at most 3 attempts per card; a 409 means the card is no longer pending and is skipped); `publish-next`.
5. Every stage start goes through `Api.start`: a 409 waits for the running stage and retries once; the run is polled on `GET /agent/runs` (60 seconds, 30 polls) and counts as ok only when `last[stage].ok` is true. A 5xx or a network error is retried up to 4 attempts, 20 seconds apart. A tick that exits non-zero only logs a warning.
6. `POST /agent/controls/slot/finish` with the result. A failure sends the alert `slot failed 3 times` when this was the third failure. A pause mid-slot finishes the slot as failed, never alerts, and exits 0 with outcome `paused`.
7. One JSON log line per run: `message: "slot outcome"`, `slot`, `outcome` (`done`, `failed`, `skipped`, `paused`), `reason` (the failing step; HTTP status and path or an exception type, never a message that could carry a URL). Exit 1 on `failed`.

### State machine

`classify` in `src/signalforge/pipeline_state.py` is a pure function of stored statuses. Caps: `MAX_RESEARCH_ATTEMPTS = 2`, `MAX_DRAFT_ATTEMPTS = 2`, and `AUTO_REVIEW_MAX_REDRAFTS` (default 2; used and failed redrafts both count, via `redrafts_used`). Rows are checked top to bottom.

| Condition | stage | next_action |
|---|---|---|
| no research row | `accepted` | `run_research` |
| research `researching` | `researching` | `wait` |
| research `failed` or `needs_more_info`, attempts at the cap | `research_parked` | `close` |
| research `failed` or `needs_more_info` | `research_failed` or `research_needs_more_info` | `retry_research` |
| research ok, no draft row | `researched` | `run_draft` |
| draft `failed`, attempts at the cap | `draft_failed` | `close` |
| draft `failed` | `draft_failed` | `retry_draft` |
| draft `drafting` | `draft_drafting` | `wait` |
| draft any other status but `drafted` (for example `needs_more_info`) | `draft_<status>` | `close` |
| review `pending` | `awaiting_review` | `auto_review` |
| review `revise`, redrafts at the cap | `revise_exhausted` | `close` |
| review `revise` | `revise_requested` | `run_revise` |
| review `rejected` | `rejected` | `none` (terminal) |
| published row `unpublished` | `unpublished` | `none` (terminal until an editor publishes) |
| approved, not published | `approved` | `publish` |
| published, no cover or no figure | `published` | `attach_images` |
| published with cover and figure | `complete` | `none` (terminal) |

`close` is acted on by the autopilot (rejection with `needs_more_evidence`), so a closed card becomes `rejected`. The attempt counters are `research_packages.attempts` (migration 0012) and `article_drafts.attempts` (0014).

### Pause coverage

| Path | While paused |
|---|---|
| `POST /agent/run/{stage}` (tick, assess, cards, research, draft, revise) | 423 |
| `POST /agent/publish-next` | 423 |
| `POST /agent/topics` | 423 |
| `POST /editor/drafts/{id}/publish` with the agent key | 423 |
| `POST /editor/drafts/{id}/publish` with the editor key | allowed (the owner's manual override; it also brings back an unpublished article) |
| `POST /agent/drafts/{id}/auto-review` | reviews and approves; with `publish=true` it does not publish (`queued: true`) |
| `run_after_accept` (only when `AUTO_PIPELINE_ON_ACCEPT=true`) | skipped; the accept is still recorded |
| `python -m apps.worker.tick` | exits 0, runs nothing |
| Autopilot | exits before any step; paused mid-run, it ends the slot as failed without an alert |
| `GET /agent/controls`, `pause`, `resume`, `slot/claim`, `slot/finish`; `GET /agent/runs`, `/agent/work`, `/agent/pipeline` | allowed |
| Card decisions, image attach and upload, unpublish, `POST /ingest/{source}` | allowed |

A pause does not stop a stage thread that is already running; it ends when it finishes.

### Alerts

`send_alert(url, title, detail)` (`src/signalforge/alerts.py`) posts `{"text": ..., "content": ...}` to `ALERT_WEBHOOK_URL`, never raises, and logs only the error type (the message of an httpx error can carry the secret URL). Two senders: the API on a pause (`POST /agent/controls/pause`, in a background task) and the autopilot after the third failed attempt on a slot. Set the variable on both hosts. Unset: the alert is logged only.

### Budgets and prices

`BUDGET_PER_TOPIC_USD` (0.50) and `BUDGET_PER_ARTICLE_USD` (1.50) are USD caps; they only bite when `LLM_PRICES` (JSON, USD per million tokens by model id) lists the model, because an unpriced model costs 0 and the gateway logs a warning. `BUDGET_MAX_CALLS_PER_TOPIC` and `BUDGET_MAX_CALLS_PER_ARTICLE` cap the number of LLM calls and default to unset (no cap). Measured values are in section 8.

### Stale-run sweep

Stage runs are daemon threads, so a restart leaves `running` rows. At startup `sweep_stale_runs` (`src/signalforge/stale_runs.py`) fails `stage_runs` still `running` and research or draft rows still `researching` or `drafting` that are older than 90 minutes, with the reason `interrupted`, so the state machine retries them. The call is wrapped so a database error can never fail app startup.

## 4. Migrations applied to production

| Revision | Adds | Applied | From |
|---|---|---|---|
| 0013 | `pipeline_controls` (seeded row) | 2026-11-15 | main at 40e7350 |
| 0014 | `article_drafts.attempts` | 2026-11-15 | the PR #144 head, afe2163, just before merge, with owner approval |
| 0015 | `pipeline_controls.slot_holder` | 2026-11-15 | from PR #152 head 39abd3c, just before merge, with owner approval |

`alembic upgrade head` was run again from main at 3c76e70 on 2026-11-15 and the database was at head (0014); 0015 followed with #152, so production is now at 0015 (head). The migrations folder is `src/signalforge/db/migrations/versions`. Note for Milestone 2: the plan names its first migration `0014 sentence_verdicts`; 0014 and 0015 are taken, so it becomes 0016.

## 5. Decisions (rulings) made during implementation

- R1: Restored the CI migrations/integration job first (#137), because there is no local Postgres. Cost if wrong: one extra PR.
- R2: Budget call caps default to None in code; measured values go in env. Cost if wrong: caps stay off until env is set.
- R3: The startup stale-run sweep is always wrapped, so it can never fail app startup. Cost if wrong: none.
- R5: The orchestrator runs prod migrations; main is assumed to auto-deploy. Cost if wrong: none.
- R6: The spec moved into docs/superpowers/specs/. Cost if wrong: a file move.
- R7: The reviewer runs gh outside any checkout with -R. Cost if wrong: none.
- R8: httpx/httpcore loggers are forced to WARNING so secret URLs never reach logs. Cost if wrong: fewer request log lines.
- R9: Hermes stays the owner's Telegram control surface (status, pause, resume, publish now, hot topic, daily report), not the runtime driver. Cost if wrong: Telegram control only works while the Hermes gateway host is on.
- R10: Added Task 6b, a cap on draft retries (migration 0014). Cost if wrong: one extra column.
- R11: 0014 was applied to prod from the PR head before merge, with owner approval. Cost if wrong: none (it was applied before the merge).
- R12: A research crash before the package insert has no per-card cap; it is bounded by the 3-failures-per-slot rule. Cost if wrong: repeated cost on a card that keeps crashing.
- R13: The autopilot uses configure_logging, not basicConfig. Cost if wrong: none.
- R14: Task 8b ran in parallel with Task 7 on disjoint files. Cost if wrong: a rebase.
- R15: skills/ added to the Railway image. Cost if wrong: a slightly larger image.
- R16: The final fix wave was split across two parallel PRs (#147, #148). Cost if wrong: a rebase.
- R17: autopilot.py at about 323 lines is accepted. Cost if wrong: a later split.

There is no R4 in the ruling list.

## 6. Known residuals

- Hermes Telegram control works only while its gateway host (the laptop) is on. Moving the gateway to the cloud is a follow-up.

Fixed after M1 merge:

- A claim call that fails after the server took the lease no longer strands the slot. Migration 0015 adds `pipeline_controls.slot_holder`; the autopilot sends one `holder` id per run and retries the claim once with the same id, and the server hands the same holder its own claim back without changing the lease or the failure count. `finish_slot` and `release_slot` clear the holder (#152).
- A pause mid-slot no longer counts as a failure. The autopilot sends `slot/finish` with `release: true`; the slot shows as `failed` but `slot_failures` is unchanged, so the next run claims it again and accepts cards normally (this PR).
- A tick with a non-zero `exit_code` now fails the slot, with `tick exit_code N` in the outcome line (this PR).
- The accept target counts every non-terminal card, mid-stage (`wait`) included, read from `GET /agent/pipeline` because `/agent/work` hides `wait` (this PR).
- `agent_runs` ordering race, the agent-key republish of an unpublished article, and the untyped redraft error (the companion API fix PR).

## 7. Owner steps before the soak, and soak pass criteria

Steps, in order (details in [docs/deploy-cron.md](../deploy-cron.md), not repeated here): unload launchd; create the cron service with only the autopilot variables; set `AUTO_PIPELINE_ON_ACCEPT=false`, `ALERT_WEBHOOK_URL`, `LLM_PRICES` and the two call caps on the API host; install the Telegram control prompt in Hermes ([docs/hermes-setup.md](../hermes-setup.md)).

Soak pass criteria (7 days, laptop off): every slot has an `outcome: done` line and no `outcome: failed` line; at least 2 publishes a day; no card stuck in one stage for more than 24 hours; one kill-switch drill done; one alert received. Record the results in `docs/pipeline/m1-soak-<date>.md`.

## 8. Measurements

`llm_calls` per `stage_run`, last 30 days, measured 2026-11-15:

| Stage | p95 calls | max calls |
|---|---|---|
| research | 18.8 | 27 |
| draft | 12.1 | 15 |
| assess | 27 | 40 |
| cards | 23 | 30 |

These are the basis for the recommended caps: `BUDGET_MAX_CALLS_PER_TOPIC=40` and `BUDGET_MAX_CALLS_PER_ARTICLE=30`.

Production row counts on 2026-11-15:

| Table | Status | Rows |
|---|---|---|
| `research_packages` | researched | 98 |
| `research_packages` | needs_more_info | 3 |
| `research_packages` | failed | 1 |
| `article_drafts` | drafted | 88 |
| `article_drafts` | needs_more_info | 7 |
| `article_drafts` | failed | 1 |

## 9. What's next

Milestone 2, "Trustworthy judge", per section 4 of the plan: persisted sentence verdicts, a larger judge probe set, a referee role, a calibration report, a judge chosen in an ADR, and the hard writer/judge family check. It starts only after the soak passes.
