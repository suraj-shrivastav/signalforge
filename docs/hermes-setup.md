# SignalForge on a new device: Hermes + scheduler setup

SignalForge's backend runs on Render (database on Supabase, website on Vercel). The laptop runs two things:

1. **Pipeline scheduler** (launchd + shell): four slots a day (00, 06, 12, 18 local). Each slot ticks the backend, accepts the two top-scored cards, researches them, drafts them, auto-reviews it and publishes it (or queues it behind the pacing limit). Every 15 minutes it also tries to publish the next queued draft and refreshes the website cache after a publish.
2. **Hermes** (agent + Telegram gateway): one evening job (6 pm) reports the day to Telegram and attaches images when needed.

The pipeline does not depend on an LLM agent, so a Hermes failure never blocks drafting or publishing.

## Publishing limits

- At least 4 hours between articles, at most 3 per rolling 24 hours. The API enforces this; the scripts cannot go over it.
- Two cards are accepted per slot (`ACCEPT_PER_RUN` in the pipeline script), so one failure still leaves a draft. A card that fails research is retried once in the same run and once in the next slot. After 2 failed attempts it becomes `parked` and is never retried (the evening report lists parked cards).
- A late slot (laptop off) runs as soon as the Mac is awake, so the number of articles per day can drop below 3 on days the Mac was off.

## Backend setup (one time, any new Render or database)

1. Run database migrations against the database: `alembic upgrade head` (uses `DATABASE_URL`; head is `0012`, which adds `research_packages.attempts`). Run it before the backend deploys new code.
2. Render environment: set `LLM_EMBED_BATCH_SIZE=1` when the embedding provider cannot embed more than one text per request (NVIDIA `nemotron-3.5-embed-1b` returns HTTP 500 for batches). Leave it unset (0) for providers that batch normally. If embeddings still fail, research keeps the claims unmerged instead of failing.
3. Vercel: set `REVALIDATE_SECRET` (same value as in `~/.signalforge.env`) so the scheduler can expire the article cache after a publish.

## Prerequisites

- macOS, `git`, `jq`, `curl` (system versions are fine; scripts work on bash 3.2, no `mapfile`)
- Hermes CLI installed (`hermes --version`)
- A Telegram bot token and your chat id (bot created with @BotFather)
- Backend keys: the agent key (`SIGNALFORGE_KEY`) and the editor key (`EDITOR_API_KEY`). Ask the owner; never commit them.
- Optional for the website cache refresh: `SITE_URL` (the Vercel URL) and `REVALIDATE_SECRET`.
- Repo cloned, project venv created for the image skill (`uv sync` in the repo root)

## 1. Clone the repo

```bash
git clone git@github.com:suraj-shrivastav/signalforge.git ~/personal/signalforge
cd ~/personal/signalforge && uv sync
```

If the repo lives elsewhere, set `SIGNALFORGE_REPO` in `~/.signalforge.env`.

## 2. Install the pipeline scheduler

```bash
scripts/hermes/install.sh      # first run creates ~/.signalforge.env and stops
$EDITOR ~/.signalforge.env     # paste the real keys (file is chmod 600)
scripts/hermes/install.sh      # second run installs the launchd agent
```

What it installs:

| Item | Path |
|---|---|
| Wrapper (slots, lock, retries) | `~/bin/signalforge_cron_tick.sh` |
| Pipeline | `~/bin/signalforge_cron_pipeline.sh` |
| launchd agent | `~/Library/LaunchAgents/ai.signalforge.cron.plist` |
| Log | `~/signalforge-cron.log` |
| Slot state | `~/.signalforge-state` |

How scheduling works: launchd runs the wrapper at login and every 15 minutes. Each run first tries `publish-next` (cheap; the API applies the pacing limit). Then it runs the full pipeline once per slot (00, 06, 12, 18 local time). If the laptop was off or asleep, the missed slot runs as soon as the Mac is back. A failed slot retries up to 3 times. A lock prevents overlapping runs. Re-run `install.sh` after pulling script changes: it copies the scripts to `~/bin`.

Every 15 minutes the wrapper also calls `publish-next` and `articleimg.py auto` (deterministic cover and figure for any published article without images; needs `uv sync` so `.venv/bin/python` exists).

Do not also add a crontab entry for the pipeline. It would double-run it.

## 3. Set up Hermes and the Telegram gateway

1. Install Hermes and run `hermes setup`. Choose a model provider.
2. Run `hermes gateway setup` and choose Telegram. Enter the bot token and your chat id when asked.
3. In `~/.hermes/config.yaml` make sure `catch_up_missed: true` is set under the cron section, so missed Hermes jobs run after wake.
4. Add the backend key to `~/.hermes/.env` as `AGENT_API_KEY=<editor key>`.
5. Start the gateway as a service and confirm Telegram is connected:

```bash
hermes gateway install      # launchd service, starts at login
hermes gateway status       # expect: telegram connected
```

Send the bot a message to confirm it answers.

## 4. Create the evening report job

The prompt is in [scripts/hermes/evening-report-prompt.md](../scripts/hermes/evening-report-prompt.md). Edit the repo paths in it for this machine, then:

```bash
hermes cron create \
  --name signalforge-evening-report \
  --schedule "0 18 * * *" \
  --deliver telegram \
  --grace-minutes 720 \
  --prompt "$(sed 1,5d scripts/hermes/evening-report-prompt.md)"
hermes cron list
```

`--grace-minutes 720` lets the job still fire up to 12 hours late after a sleep or shutdown.

**Only this job should be enabled for SignalForge in Hermes.** Do not create or unpause the old morning, midday or night tick jobs: they run the same pipeline as the launchd scheduler and would double every run. Other Hermes jobs (job search and so on) are independent and need no change.

The prompt tells Hermes to list `parked` cards by title and never retry them. To refresh an existing job after the prompt changes, edit its `prompt` in `~/.hermes/cron/jobs.json` (back the file up first) or recreate the job with the command above.

### Hermes memory

Add these facts to `~/.hermes/memories/MEMORY.md` (one entry per fact, separated by `§`) so Hermes can answer questions about the pipeline:

- API base URL `https://signalforge-wmtl.onrender.com`. Write endpoints accept `X-Editor-Key` with `AGENT_API_KEY` or `EDITOR_API_KEY`. Reads of run state (`/agent/runs`, `/cards/queue`, `/agent/work`) need `EDITOR_API_KEY`. Publish pacing: 4 h gap, max 3 per 24 h, never force. Auto-review: max 2 redrafts.
- Research needs at least 3 claims, otherwise one extra search round. A card is tried at most 2 times, then `next_action` is `parked`. Never retry or accept a parked card; list it by title for the owner. Failure text starts with a class: `blocked`, `empty`, `no_claims`, `thin`, `budget`, `other`. Claim merging is skipped if the embedding API fails.
- The launchd scheduler runs the pipeline. Only the evening Hermes job is enabled; the morning, midday and night tick jobs stay paused on purpose.
- The article-images skill lives in the repo at `skills/article-images/`. Use the project venv (`.venv/bin/python`), because system python 3.9 is too old.

## 5. Keep the machine awake (recommended)

Closing the lid sleeps the Mac and no script can block that. On a machine that must run unattended:

```bash
sudo pmset -b sleep 0 disablesleep 1     # battery
sudo pmset -c sleep 0                    # charger
```

Skipping this is safe: slots run late, never get lost. The wrapper also wraps each run in `caffeinate -i` so idle sleep cannot cut a run short.

## 6. Verify

```bash
launchctl list | grep signalforge          # agent loaded
tail -f ~/signalforge-cron.log             # expect: slot ... start, ... cron pipeline complete, slot ... done
hermes cron status                         # scheduler running
hermes cron run <job-id>                   # fire the evening job now
```

A healthy run logs `tick finished`, `accept ...: HTTP 201`, `research finished`, `draft finished`, `auto-review ...`, `publish-next`, `cron pipeline complete`.

## Models

The pipeline picks its models per role from env (`LLM_MODEL_*`, `LLM_BASE_URL`; see `src/signalforge/llm/roles.py`) and works with any OpenAI-compatible endpoint. Hermes' own model (currently Nemotron) is separate: it only schedules and reports, so changing either never affects the other. The article writer and the claim judge must stay in different model families.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `mapfile: command not found` | Old script version. macOS bash 3.2 has no `mapfile`. Re-run `install.sh` to get the current scripts. |
| `publish-next` returns `published: null, waiting: N` | Pacing limit (4 h apart, 3 per 24 h). Expected, drafts drain as slots open. |
| Log shows `slot ... FAILED (attempt 3)` | Read the lines above it. Fix the cause, then delete `~/.signalforge-state` to retry the slot. |
| `backend unreachable, will retry next interval` | Render cold start or no wifi. Retries automatically. |
| Hermes job `agent reported failure` | The agent was cut off (often by sleep) or the model call failed. Check `hermes cron runs`, `~/.hermes/logs/errors.log`. |
| Telegram `nodename nor servname provided` or `Sticky Telegram path ... failed` | Network dropped across sleep. The gateway retries; reports may arrive late. |
| A slot runs hours late | The Mac was off or asleep at slot time. The slot runs as soon as it wakes; this is by design. To reduce it, schedule a wake before each slot (for example `sudo pmset repeat wakeorpoweron MTWRFSU 05:55:00`, one schedule only) or keep the Mac awake (section 5). |
| Cards stuck with `parked` | Research failed twice. Read the failure reason, fix the source problem if any, or ignore. They do not block other cards. |
| Research fails with `LLM provider unavailable (status=500)` on embeddings | Set `LLM_EMBED_BATCH_SIZE=1` on the backend. Claim merging is skipped if the embedding call still fails. |
| `column research_packages.attempts does not exist` | Migration `0012` was not applied. Run `alembic upgrade head`. |
| Runs happen at odd times | Check for a leftover crontab (`crontab -l`) or old Hermes tick jobs; remove or `hermes cron pause <id>` them. |

## Uninstall

```bash
launchctl bootout gui/$(id -u)/ai.signalforge.cron
rm ~/Library/LaunchAgents/ai.signalforge.cron.plist ~/bin/signalforge_cron_*.sh ~/.signalforge-state
```
