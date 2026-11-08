# SignalForge on a new device: Hermes + scheduler setup

SignalForge's backend runs on Render. The laptop runs two things:

1. **Pipeline scheduler** (launchd + shell): every 6 hours it ticks the backend, accepts the top-scored card, researches it, drafts it, auto-reviews it and publishes it (or queues it behind the pacing limit).
2. **Hermes** (agent + Telegram gateway): one evening job attaches images to published articles and sends a report to Telegram.

The pipeline does not depend on an LLM agent, so a Hermes failure never blocks drafting or publishing.

## Prerequisites

- macOS, `git`, `jq`, `curl` (system versions are fine; scripts work on bash 3.2, no `mapfile`)
- Hermes CLI installed (`hermes --version`)
- A Telegram bot token and your chat id (bot created with @BotFather)
- Backend keys: the agent key (`SIGNALFORGE_KEY`) and the editor key (`EDITOR_API_KEY`). Ask the owner; never commit them.
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

How scheduling works: launchd runs the wrapper at login and every 15 minutes. The wrapper runs the pipeline once per slot (00, 06, 12, 18 local time). If the laptop was off or asleep, the missed slot runs as soon as the Mac is back. A failed slot retries up to 3 times. A lock prevents overlapping runs.

Every 15 minutes the wrapper also calls `publish-next` and `articleimg.py auto` (deterministic cover and figure for any published article without images; needs `uv sync` so `.venv/bin/python` exists).

Do not also add a crontab entry for the pipeline. It would double-run it.

## 3. Set up Hermes and the Telegram gateway

1. Install Hermes and run `hermes setup`. Choose a model provider.
2. Run `hermes gateway setup` and choose Telegram. Enter the bot token and your chat id when asked.
3. In `~/.hermes/config.yaml` make sure `catch_up_missed: true` is set under the cron section, so missed Hermes jobs run after wake.
4. Add the backend key for the image step to `~/.hermes/.env` as `AGENT_API_KEY=<editor key>`.
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

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `mapfile: command not found` | Old script version. macOS bash 3.2 has no `mapfile`. Re-run `install.sh` to get the current scripts. |
| `publish-next` returns `published: null, waiting: N` | Pacing limit (4 h apart, 3 per 24 h). Expected, drafts drain as slots open. |
| Log shows `slot ... FAILED (attempt 3)` | Read the lines above it. Fix the cause, then delete `~/.signalforge-state` to retry the slot. |
| `backend unreachable, will retry next interval` | Render cold start or no wifi. Retries automatically. |
| Hermes job `agent reported failure` | The agent was cut off (often by sleep) or the model call failed. Check `hermes cron runs`, `~/.hermes/logs/errors.log`. |
| Telegram `nodename nor servname provided` or `Sticky Telegram path ... failed` | Network dropped across sleep. The gateway retries; reports may arrive late. |
| Runs happen at odd times | Check for a leftover crontab (`crontab -l`) or old Hermes tick jobs; remove or `hermes cron pause <id>` them. |

## Uninstall

```bash
launchctl bootout gui/$(id -u)/ai.signalforge.cron
rm ~/Library/LaunchAgents/ai.signalforge.cron.plist ~/bin/signalforge_cron_*.sh ~/.signalforge-state
```
