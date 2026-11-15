# Hermes evening job prompt (images + Telegram report)

Use with `hermes cron create --name signalforge-evening-report --schedule "0 18 * * *" --deliver telegram --grace-minutes 720 --prompt "$(sed 1,5d evening-report-prompt.md)"`.
Replace the paths below with this machine's repo path.

The SignalForge pipeline (tick, accept best card, research, draft, auto-review, publish) runs from a cloud cron job (the autopilot); there is no local log. Standing owner policy: no approval is needed, never ask questions. Send the header X-Editor-Key with the AGENT_API_KEY environment variable on every request and never print the key.

1. GET /agent/controls. Note whether the pipeline is paused (paused_reason, paused_by), the slot, slot_status and slot_failures.
2. GET /agent/work and GET /agent/runs. Note today's activity: cards by stage, the slugs published or queued, and the last run results with any errors.
3. Do not list closed cards: the autopilot closes them within 15 minutes and they leave /agent/work at once. The autopilot log on the cron host records each close (`auto-closed <card_id> (<stage>): <title>`).
4. Images are made by the autopilot (it runs `articleimg.py auto` every 15 minutes: no model, always valid). If any article in /agent/work still has next_action attach_images, run once: API_BASE_URL=https://signalforge-wmtl.onrender.com EDITOR_API_KEY="$AGENT_API_KEY" /Users/suraj/personal/signalforge/.venv/bin/python /Users/suraj/personal/signalforge/skills/article-images/scripts/articleimg.py auto . On a 502, retry once after 30 s. Do not draw or write SVG yourself. Report any SKIP line verbatim.

Final response (delivered to the owner): published or queued (slug, URL, next_publish_at), paused state, slot failures, images attached, and any errors verbatim. Do not unpublish or delete anything.
