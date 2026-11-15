# SignalForge on a new device: Hermes + scheduler setup

## What runs where

| Part | Where | Job |
|---|---|---|
| Backend API and database | Render and Supabase | The pipeline's state and all endpoints. |
| Website | Vercel | Serves the published articles. |
| Cron autopilot (`apps/worker/autopilot.py`) | Render cron job, every 15 minutes | Runs the pipeline: four slots a day, publish pacing, images, closing dead cards. See [deploy-cron.md](deploy-cron.md). |
| launchd `ai.signalforge.cron` | The owner's laptop | Fallback only. It runs the same pipeline slots until the cloud cron is set up. Never run it beside the cron. |
| Hermes | The owner's laptop | The owner's Telegram control and the 6 pm evening report. |

Hermes never schedules the pipeline. The owner uses it from Telegram to find out why an article is not published (`why`), to ask for research on a topic (`topic`), to see the publish queue (`queue`), and to ask anything about the pipeline. The pipeline does not depend on Hermes, so a Hermes failure never blocks drafting or publishing.

State on the owner's machine (checked 2026-11-15 with `hermes cron list` and launchd):

- launchd `ai.signalforge.cron` is loaded and runs the pipeline slots today.
- Hermes job `signalforge-evening-tick` (6 pm evening report) is the only SignalForge Hermes job that should be active.
- `signalforge-morning-tick`, `signalforge-midday-tick` and `signalforge-night-autopilot` are paused legacy jobs that used to drive the pipeline. They would double-run with the autopilot: remove them (next section).
- `job-pipeline` is unrelated to SignalForge. Leave it.

1. **Pipeline scheduler, a fallback only** (launchd + shell): section 2 below. Four slots a day (00, 06, 12, 18 local). Each slot ticks the backend, accepts the two top-scored cards, researches them, drafts them, auto-reviews it and publishes it (or queues it behind the pacing limit). Every 15 minutes it also tries to publish the next queued draft and refreshes the website cache after a publish.
2. **Hermes** (agent + Telegram gateway): the owner's Telegram control (section 5) and one evening job (6 pm) that reports the day to Telegram.

## Clean up legacy Hermes jobs

The old morning, midday and night tick jobs ran the pipeline from Hermes. The autopilot and launchd replaced them. List the jobs, then remove each legacy one:

```bash
hermes cron list
hermes cron remove <id>        # alias: rm, delete. Do this for each of the three legacy jobs
hermes cron pause <id>         # or at least pause it; never resume it
```

Use the ids that `hermes cron list` prints for `signalforge-morning-tick`, `signalforge-midday-tick` and `signalforge-night-autopilot`. Keep the evening job and `job-pipeline`. Then `hermes cron list` should show one active SignalForge job.

## Publishing limits

- At least 4 hours between articles, at most 3 per rolling 24 hours. The API enforces this; the scripts cannot go over it.
- About two cards are in the pipeline at a time (the autopilot's `AUTOPILOT_ACCEPT_PER_RUN`, default 2: it accepts only enough to top that up; the launchd script's `ACCEPT_PER_RUN` accepts two per slot), so one failure still leaves a draft. A card that fails research or its draft is retried; after 2 failed attempts its `next_action` becomes `close` and the autopilot rejects it (it logs each close as `auto-closed <card_id> (<stage>): <title>`). A card whose revise has used all `AUTO_REVIEW_MAX_REDRAFTS` (2) redrafts is closed the same way.
- A late slot (laptop off) runs as soon as the Mac is awake, so the number of articles per day can drop below 3 on days the Mac was off.

## Backend setup (one time, any new Render or database)

1. Run database migrations against the database: `alembic upgrade head` (uses `DATABASE_URL`; head is `0014`: `0013` adds `pipeline_controls` (kill switch and slot lease), `0014` adds `article_drafts.attempts`). Run it before the backend deploys new code.
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

## 2. Install the pipeline scheduler (fallback / until the soak passes)

Skip this section while the cron autopilot ([deploy-cron.md](deploy-cron.md)) is running, and decommission launchd as described there. Install it only if the cron is down. Never run launchd next to the cron autopilot: the scripts keep their slot in `~/.signalforge-state` and never take the API's slot lease, so both would run every slot. Unload launchd before you enable the cron.

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
4. Add the backend key to `~/.hermes/.env` as `AGENT_API_KEY=<agent key>` (the editor key also works).
5. Start the gateway as a service and confirm Telegram is connected:

```bash
hermes gateway install      # launchd service, starts at login
hermes gateway status       # expect: telegram connected
```

Send the bot a message to confirm it answers.

## 4. Create the evening report job

The report reads the API only (`GET /agent/controls`, `/agent/work`, `/agent/runs`), never a local log, so it works with the laptop scheduler off.

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

The prompt reads `GET /agent/controls`, `/agent/work` and `/agent/runs` (the cron has no local log). Closed cards leave `/agent/work` at once, so the report does not list them: the autopilot log on the cron host records each close. To refresh an existing job after the prompt changes, edit its `prompt` in `~/.hermes/cron/jobs.json` (back the file up first) or recreate the job with the command above.

### Hermes memory

See "Install or update the Hermes skill" below. Do not hand-copy facts into memory: the skill holds them, and memory keeps only a one-line pointer to it.

## 5. Telegram control

The prompt is in [scripts/hermes/telegram-control.md](../scripts/hermes/telegram-control.md). It is installed into the Hermes skill with the reference (see "Install or update the Hermes skill" below). It lets the owner send `status`, `pause <reason>`, `resume`, `publish now`, `hot <url or query>`, `cards`, `why <title or slug>`, `topic <url or query>` and `queue` to the bot, and maps each to an API call with the agent key. Free-form questions are answered from the read-only endpoints only. It never unpublishes or deletes, and acts only on messages from the owner's chat. `topic` is normal research that waits its turn; `hot` jumps the queue.

Make sure `API_BASE_URL` is set in `~/.hermes/.env` next to `AGENT_API_KEY`. Restart the gateway (`hermes gateway status`), then send `status` to the bot to check it answers.

The control works only while the gateway host is on. The pipeline does not depend on it: pause also works with `curl` (see [deploy-cron.md](deploy-cron.md)).

## Install or update the Hermes skill

The SignalForge facts and the owner's commands live in one Hermes skill, `~/.hermes/skills/signalforge-pipeline/SKILL.md`, not in memory: together they are about 10,000 characters, and Hermes memory holds at most 2,200 (`memory_char_limit`). The skill is built from three repo files:

- [scripts/hermes/skill-header.md](../scripts/hermes/skill-header.md): the skill's frontmatter and its role (remote control and explainer; it never runs the pipeline);
- [scripts/hermes/signalforge-reference.md](../scripts/hermes/signalforge-reference.md): what SignalForge is, who runs what, card states, limits, revise reasons, endpoints, rules;
- [scripts/hermes/telegram-control.md](../scripts/hermes/telegram-control.md): the owner's commands.

1. Run `scripts/hermes/install-skill.sh`. It backs up the old skill to `SKILL.md.bak` and writes the new one.
2. Keep exactly one SignalForge entry in `~/.hermes/memories/MEMORY.md` (entries are separated by a line with `§`), a pointer such as: "SignalForge: Hermes is the owner's Telegram remote control and explainer, never the scheduler. The autopilot cron runs the pipeline. For any SignalForge question or command (status, why, queue, topic, hot, pause, resume, publish now, cards) load skill signalforge-pipeline. Never tick, accept, research, draft or publish on your own; never unpublish or delete; never print the key." Delete any older SignalForge entries.
3. Make sure `API_BASE_URL` and `AGENT_API_KEY` are in `~/.hermes/.env`, restart the gateway (`hermes gateway restart`) and send `why <a title>` and `queue` to the bot.

Re-run step 1 after any of the three files changes in the repo. Hermes must never write the skill or the pointer itself.

## Optional: run the Hermes gateway on a cloud host

By default Telegram works only while the laptop is on and awake, because the gateway runs there. To keep Telegram answering with the laptop off, run the gateway on an always-on host (a small VM; any Linux box with Hermes installed). This is optional: the pipeline itself already runs in the cloud.

```bash
hermes setup                  # provider key, on the host
hermes gateway setup          # choose Telegram, same bot token and chat id
hermes gateway run            # foreground, recommended for Docker; or:
hermes gateway install && hermes gateway start   # systemd service
hermes gateway status
```

Copy `~/.hermes/.env` values (`AGENT_API_KEY`, `API_BASE_URL`) and the SignalForge skill (run `scripts/hermes/install-skill.sh` there) plus the memory pointer entry to the host. Run the gateway in one place only: stop the laptop's service first (`hermes gateway stop`), because two gateways polling one Telegram bot fight over messages. The evening job runs where the gateway scheduler runs, so recreate it on the host (section 4) and remove it from the laptop. `hermes gateway --help` lists the other options (`enroll`, `migrate`).

## 6. Keep the machine awake (recommended)

Closing the lid sleeps the Mac and no script can block that. On a machine that must run unattended:

```bash
sudo pmset -b sleep 0 disablesleep 1     # battery
sudo pmset -c sleep 0                    # charger
```

Skipping this is safe: slots run late, never get lost. The wrapper also wraps each run in `caffeinate -i` so idle sleep cannot cut a run short.

## 7. Verify

```bash
launchctl list | grep signalforge          # agent loaded
tail -f ~/signalforge-cron.log             # expect: slot ... start, ... cron pipeline complete, slot ... done
hermes cron status                         # scheduler running
hermes cron run <job-id>                   # fire the evening job now
```

A healthy run logs `tick finished`, `accept ...: HTTP 201`, `research finished`, `draft finished`, `auto-review ...`, `publish-next`, `cron pipeline complete`.

## Models

The pipeline picks its models per role from env (`LLM_MODEL_*`, `LLM_BASE_URL`; see `src/signalforge/llm/roles.py`) and works with any OpenAI-compatible endpoint. Hermes' own model (currently Nemotron) is separate: it only answers the owner and writes the report, so changing either never affects the other. The article writer and the claim judge must stay in different model families.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `mapfile: command not found` | Old script version. macOS bash 3.2 has no `mapfile`. Re-run `install.sh` to get the current scripts. |
| `publish-next` returns `published: null, waiting: N` | Pacing limit (4 h apart, 3 per 24 h). Expected, drafts drain as slots open. |
| Log shows `slot ... FAILED (attempt 3)` | Read the lines above it. Fix the cause, then delete `~/.signalforge-state` to retry the slot. |
| `backend unreachable, will retry next interval` | Render cold start or no wifi. Retries automatically. |
| Evening job fails with `403 Authorization failed` from NVIDIA NIM | Hermes's own model key expired or was revoked. Update the provider key with `hermes setup` (or the provider key in `~/.hermes/.env`). The SignalForge key (`AGENT_API_KEY`) is separate and unaffected: the pipeline keeps running. |
| Hermes job `agent reported failure` | The agent was cut off (often by sleep) or the model call failed. Check `hermes cron runs`, `~/.hermes/logs/errors.log`. |
| Telegram `nodename nor servname provided` or `Sticky Telegram path ... failed` | Network dropped across sleep. The gateway retries; reports may arrive late. |
| A slot runs hours late | The Mac was off or asleep at slot time. The slot runs as soon as it wakes; this is by design. To reduce it, schedule a wake before each slot (for example `sudo pmset repeat wakeorpoweron MTWRFSU 05:55:00`, one schedule only) or keep the Mac awake (section 6). |
| Cards with `close` (a closed card) | Research failed or was thin twice, the draft failed twice or had no usable claims, or a revise used up its redrafts. The autopilot rejects them with `needs_more_evidence` and the note `auto-closed: <stage>` within 15 minutes; they leave `/agent/work` at once, so look for `auto-closed` in the cron host's log. Read the failure reason and fix the source problem if any. They do not block other cards. |
| Calls return HTTP 423, or the autopilot logs `outcome: paused` | The pipeline is paused (kill switch). `GET /agent/controls` shows `paused_reason`, `paused_by` and `paused_until`. Resume with `POST /agent/controls/resume` (or `resume` in Telegram). A breaker pause lifts itself at `paused_until`. Nothing is lost: the next slot picks up. |
| Alert `slot failed 3 times` | The autopilot failed one slot three times and will not claim it again (`GET /agent/controls`: `slot_failures` 3). Read the cron log lines `slot outcome` with `outcome: failed` and their `reason` (the failing step), fix the cause; the next 6-hour slot starts clean. A mid-slot pause counts as a failed attempt too. |
| Redraft cap reached (card stage `revise_exhausted`) | The article used its `AUTO_REVIEW_MAX_REDRAFTS` redrafts, failed ones included. It is closed, not retried. Raise the setting on the API only if the drafts were close to passing. |
| A card is held in a stage for hours | A restart of the API loses an in-flight stage. The API frees such rows (older than 90 minutes) at startup and the next autopilot run retries the card, up to the attempt caps. |
| Research fails with `LLM provider unavailable (status=500)` on embeddings | Set `LLM_EMBED_BATCH_SIZE=1` on the backend. Claim merging is skipped if the embedding call still fails. |
| `column research_packages.attempts` / `article_drafts.attempts` / `pipeline_controls` does not exist | Migration `0012`, `0014` or `0013` was not applied. Run `alembic upgrade head`. |
| Runs happen at odd times | Check for a leftover crontab (`crontab -l`) or old Hermes tick jobs; remove or `hermes cron pause <id>` them. |

## Uninstall

```bash
launchctl bootout gui/$(id -u)/ai.signalforge.cron
rm ~/Library/LaunchAgents/ai.signalforge.cron.plist ~/bin/signalforge_cron_*.sh ~/.signalforge-state
```
