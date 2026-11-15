# Hermes evening job prompt (images + Telegram report)

Use with `hermes cron create --name signalforge-evening-report --schedule "0 18 * * *" --deliver telegram --grace-minutes 720 --prompt "$(sed 1,3d evening-report-prompt.md)"`.
Replace the paths below with this machine's repo path.

The SignalForge pipeline (tick, accept best card, research, draft, auto-review, publish) already ran from a launchd script; its log is /Users/suraj/signalforge-cron.log. Standing owner policy: no approval is needed, never ask questions. Send the header X-Editor-Key with the AGENT_API_KEY environment variable on every request and never print the key.

1. Read the last 40 lines of /Users/suraj/signalforge-cron.log. Note the card accepted, published or queued slugs and any FAILED or error lines.
2. Images are made by the scheduler (it runs `articleimg.py auto` every 15 minutes: no model, always valid). GET /agent/work. If any article still has next_action attach_images, run once: API_BASE_URL=https://signalforge-wmtl.onrender.com EDITOR_API_KEY="$AGENT_API_KEY" /Users/suraj/personal/signalforge/.venv/bin/python /Users/suraj/personal/signalforge/skills/article-images/scripts/articleimg.py auto . On a 502, retry once after 30 s. Do not draw or write SVG yourself. Report any SKIP line verbatim.
List every card the agent closed today (decision `rejected`, note starting `auto-closed:`) by title.


Final response (delivered to the owner): card title and score, published or queued (slug, URL, next_publish_at), images attached, and any errors verbatim. Do not unpublish or delete anything.
