# Deploy the cron autopilot

The autopilot runs the pipeline from a cloud cron job instead of the laptop. It is one command,
`python -m apps.worker.autopilot` (`uv run python -m apps.worker.autopilot` in a dev checkout),
started every 15 minutes. It holds only the agent key and calls the API; it needs no
`DATABASE_URL` and no storage keys, and it strips those from the images script's environment.

Each run:

1. Reads `GET /agent/controls` and exits 0 if the pipeline is paused.
2. Tries `POST /agent/publish-next`, then the images tick (`skills/article-images/scripts/articleimg.py auto`).
3. Closes every `/agent/work` card whose `next_action` is `close`: `POST /cards/{id}/decision` with `rejected`, `["needs_more_evidence"]` and the note `auto-closed: <stage>`.
4. Claims the 6-hour slot (`POST /agent/controls/slot/claim`, 360-minute lease). If it gets the lease it runs tick, accepts cards (first attempt of a slot only), research, draft, revise for cards waiting on it, auto-review and revise, publish-next, then `slot/finish`. A stage counts as done only when `GET /agent/runs` reports it ended ok. A second runner finds the slot held or done and skips the slot; it still runs steps 2 and 3, which are safe to repeat.
5. Sends an alert after 3 failed attempts on one slot.
6. Logs one JSON line per run with `"message": "slot outcome"` and the fields `slot`, `outcome` (`done`, `failed`, `skipped` or `paused`) and `reason`. These lines are the per-slot history; `GET /agent/controls` shows only the latest slot.

Steps 2 and 3 are best effort: a failure there is logged and the run goes on to the claim.

Accepting: on a slot's first attempt the autopilot accepts `max(0, AUTOPILOT_ACCEPT_PER_RUN - in_flight)` cards, where `in_flight` counts the `/agent/work` cards whose `next_action` is `run_research`, `retry_research`, `run_draft`, `retry_draft`, `auto_review`, `run_revise` or `publish`. So about `AUTOPILOT_ACCEPT_PER_RUN` cards are in the pipeline at any time, and a retried slot accepts none.

## API host settings

- `AUTO_PIPELINE_ON_ACCEPT` must be `false` (the default) on the API. The autopilot accepts cards itself; with it on, every accept starts a pass inside the API that holds the run lock, and the autopilot's next stage start gets 409 and has to wait.
- Set `ALERT_WEBHOOK_URL` on the API host too: the pause alert is sent by the API, not by the cron job.

## Render Cron Job

1. Create a Cron Job from this repository, built the same way as the API service.
2. Schedule `*/15 * * * *`. Command `uv run python -m apps.worker.autopilot`.
3. Make sure the build uses the repository root and includes `skills/`: the images tick runs `skills/article-images/scripts/articleimg.py` (standard library only). If the script is missing it logs a warning and skips the images. No Render config is in this repo, so check this in the Render service settings.
4. Set the variables below.

| Variable | Value |
|---|---|
| `API_BASE_URL` | the API's public URL, no trailing slash |
| `SIGNALFORGE_KEY` | the agent key (`AGENT_API_KEY` of the API) |
| `AUTOPILOT_TZ` | optional, default `UTC`; sets which clock the 00/06/12/18 slots follow |
| `SITE_URL` | the public web URL |
| `REVALIDATE_SECRET` | same value as on Vercel; expires the article cache after a publish |
| `ALERT_WEBHOOK_URL` | optional, see Alerts; set it on the API host as well |
| `AUTOPILOT_ACCEPT_PER_RUN` | optional, default `2`: how many cards to keep in the pipeline (see Accepting) |

Set only these variables. Do not add `DATABASE_URL`, Supabase keys or LLM keys.

## Railway equivalent

Add a new service from the same repository and Dockerfile (`infra/railway/api.Dockerfile`, which copies `skills/` into the image). Set a
custom start command `python -m apps.worker.autopilot` (not `uv run ...`: in that image `uv run`
re-syncs the dev dependencies), a cron schedule `*/15 * * * *` and only the variables above.
Do not duplicate the `api` service to make it: a copy keeps `DATABASE_URL`, the Supabase keys
and the LLM keys, and the cron must hold only the agent key. See
[deploy-railway.md](deploy-railway.md). Use one scheduler per deployment: do not also run the
old `python -m apps.worker.tick` cron service.

## Soak checklist

Do these in order and record the results in `docs/pipeline/m1-soak-<date>.md`.

1. Decommission launchd (below) before you enable the cron. Never run them side by side: the launchd scripts keep their slot in `~/.signalforge-state` and never take the API's slot lease, so both would run every slot.
2. Enable the cron and run 7 days with the laptop off.
3. Each day, read the cron host's logs: every run writes one `slot outcome` line (see Each run, step 6). `GET /agent/controls` shows only the latest slot.

Pass criteria for the 7 days:

- Every slot has an `outcome: done` line and no `outcome: failed` line (so `slot_failures=0`).
- At least 2 publishes a day.
- No card stuck in one stage for more than 24 h.
- One kill-switch drill done.
- One alert received.

## Decommission launchd

```bash
launchctl unload ~/Library/LaunchAgents/ai.signalforge.cron.plist
```

The label is `ai.signalforge.cron` (see `scripts/hermes/ai.signalforge.cron.plist.template`). The
scripts stay in the repo for one release as a fallback. Hermes keeps running: it is the owner's
Telegram control and the evening report, not the pipeline driver.

## Kill switch drill

```bash
curl -X POST $API/agent/controls/pause -H "X-Editor-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"reason":"drill"}'
```

Confirm the next autopilot run does nothing and `GET /agent/controls` shows `paused: true`.
Resume with `POST /agent/controls/resume`. The pause also sends an alert, so the drill covers
the "one alert received" criterion.

## Alerts

`ALERT_WEBHOOK_URL` takes a Slack or Discord incoming webhook. The API and the autopilot post
`{"text": ..., "content": ...}` to it (`text` for Slack, `content` for Discord). Set it on both
hosts: the API sends the pause alert, the autopilot sends the slot-failure alert.

Telegram: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>`. Telegram reads
`chat_id` from the query string and `text` from the JSON body. Verify this once with a drill
pause. The URL contains the bot token, so keep it secret and never commit it.

## Budgets

Set these on the **API** host, not on the cron job:

- `LLM_PRICES`: JSON of USD per million tokens per model id, for example `{"vendor/model": {"input": "0.2", "output": "0.6"}}`.
- `BUDGET_MAX_CALLS_PER_TOPIC=40` and `BUDGET_MAX_CALLS_PER_ARTICLE=30`. Measured from 30 days of `llm_calls`, as of 2026-11-15.
