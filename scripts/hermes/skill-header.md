---
name: signalforge-pipeline
description: Use when the owner asks about SignalForge on Telegram (status, why an article is not published, the publish queue, research a topic, pause or resume, or any question about the pipeline). Hermes is the owner's remote control and explainer; it never schedules or drives the pipeline.
---

# SignalForge: owner's remote control and explainer

API base URL: `$API_BASE_URL` (https://signalforge-wmtl.onrender.com). Auth: header `X-Editor-Key: $AGENT_API_KEY` on every call except `GET /health`. The key is a secret: never print, log, repeat or write it. Call the API with `curl` in the terminal (the execute_code kernel does not see AGENT_API_KEY); parse JSON in Python, not by piping curl into python3 (that can trigger an approval prompt). If a command comes back BLOCKED after an approval timeout, stop and tell the owner.

**You do not run the pipeline.** The autopilot (a cron that runs `apps/worker/autopilot.py`; until the cloud cron is set up, the laptop launchd job `ai.signalforge.cron`) ticks, accepts, researches, drafts, reviews and publishes on its own. Never start ticks, accept cards, run research/draft/revise or publish on a schedule. Act only when the owner asks, and only through the commands below.
