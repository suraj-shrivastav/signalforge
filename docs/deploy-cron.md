# Deploy the cron autopilot

The autopilot runs the pipeline from a cloud cron job instead of the laptop. It is one command,
`uv run python -m apps.worker.autopilot`, started every 15 minutes. It holds only the agent key
and calls the API; it needs no `DATABASE_URL` and no storage keys.

Each run:

1. Reads `GET /agent/controls` and exits 0 if the pipeline is paused.
2. Tries `POST /agent/publish-next`, then the images tick (`skills/article-images/scripts/articleimg.py auto`).
3. Closes every `/agent/work` card whose `next_action` is `close`: `POST /cards/{id}/decision` with `rejected`, `["needs_more_evidence"]` and the note `auto-closed: <stage>`.
4. Claims the 6-hour slot (`POST /agent/controls/slot/claim`). If it gets the lease it runs tick, accepts the top cards, research, draft, auto-review and revise, publish-next, then `slot/finish`. A second runner finds the slot held or done and does nothing.
5. Sends an alert after 3 failed attempts on one slot.

## Render Cron Job

1. Create a Cron Job from this repository, built the same way as the API service.
2. Schedule `*/15 * * * *`. Command `uv run python -m apps.worker.autopilot`.
3. Set the variables below.

| Variable | Value |
|---|---|
| `API_BASE_URL` | the API's public URL, no trailing slash |
| `SIGNALFORGE_KEY` | the agent key (`AGENT_API_KEY` of the API) |
| `AUTOPILOT_TZ` | optional, default `UTC`; sets which clock the 00/06/12/18 slots follow |
| `SITE_URL` | the public web URL |
| `REVALIDATE_SECRET` | same value as on Vercel; expires the article cache after a publish |
| `ALERT_WEBHOOK_URL` | optional, see Alerts |
| `AUTOPILOT_ACCEPT_PER_RUN` | optional, default `2` cards accepted per slot |

## Railway equivalent

Add a service from the same repository and Dockerfile (`infra/railway/api.Dockerfile`). Set a
custom start command `uv run python -m apps.worker.autopilot`, a cron schedule `*/15 * * * *`
and the same variables. See [deploy-railway.md](deploy-railway.md). Use one scheduler per
deployment: do not also run the old `python -m apps.worker.tick` cron service.

## Soak checklist

Do these in order and record the results in `docs/pipeline/m1-soak-<date>.md`.

1. Run the cloud cron and the laptop launchd agent side by side for 1 day. The slot lease turns the second runner into a no-op.
2. Check `GET /agent/controls`: `slot_status` is `done` for each slot.
3. Decommission launchd (below), then run 7 days with the laptop off.

Pass criteria for the 7 days:

- Every slot `done` with `slot_failures=0`.
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
`{"text": ..., "content": ...}` to it (`text` for Slack, `content` for Discord).

Telegram: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>`. Telegram reads
`chat_id` from the query string and `text` from the JSON body. Verify this once with a drill
pause. The URL contains the bot token, so keep it secret and never commit it.

## Budgets

Set these on the **API** host, not on the cron job:

- `LLM_PRICES`: JSON of USD per million tokens per model id, for example `{"vendor/model": {"input": "0.2", "output": "0.6"}}`.
- `BUDGET_MAX_CALLS_PER_TOPIC=40` and `BUDGET_MAX_CALLS_PER_ARTICLE=30`. Measured from 30 days of `llm_calls`, as of 2026-11-15.
