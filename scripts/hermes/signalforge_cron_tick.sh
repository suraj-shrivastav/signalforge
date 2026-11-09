#!/bin/bash
# SignalForge scheduler wrapper. launchd calls this every 15 min and at load/wake.
# Runs the pipeline once per 6 h slot (00, 06, 12, 18 local). A missed slot (laptop off or asleep)
# runs as soon as the Mac is back. Max 3 attempts per slot.
set -uo pipefail
LOG="$HOME/signalforge-cron.log"
STATE="$HOME/.signalforge-state"
LOCK="$HOME/.signalforge-cron.lock"
log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" >> "$LOG"; }

[ -f "$HOME/.signalforge.env" ] && { set -a; . "$HOME/.signalforge.env"; set +a; }
[ -n "${SIGNALFORGE_KEY:-}" ] || { log "ERROR: SIGNALFORGE_KEY not set"; exit 1; }

# Expire the website's cached article list after a publish. No-op unless SITE_URL and
# REVALIDATE_SECRET are set. Never fails the run.
revalidate_site() {
  [ -n "${SITE_URL:-}" ] && [ -n "${REVALIDATE_SECRET:-}" ] || return 0
  curl -sS --max-time 30 -o /dev/null -X POST "${SITE_URL%/}/api/revalidate" \
    -H "x-revalidate-secret: $REVALIDATE_SECRET" 2>/dev/null || log "site revalidate failed"
  return 0
}

# Publish tick: the API enforces the pace (4 h gap, 3 per 24 h), so this is safe every 15 min.
# It runs even when the slot is done, so an approved draft goes live as soon as a pacing slot
# opens instead of waiting for the next 6 h pipeline run.
publish_tick() {
  local resp
  resp=$(curl -sS --max-time 60 -X POST "$API_BASE_URL/agent/publish-next" \
    -H "X-Editor-Key: $SIGNALFORGE_KEY" 2>/dev/null) || return 0
  if [ "$(echo "$resp" | jq -r '.published // empty | type' 2>/dev/null)" = "object" ]; then
    log "publish tick: $(echo "$resp" | jq -c '{slug: .published.slug, waiting}' 2>/dev/null)"
    revalidate_site
  fi
}
# Image tick: give every published article without images a cover and a figure. Deterministic
# (no model), so it never skips an article and never waits for the evening Hermes job.
images_tick() {
  local repo py out
  repo="${SIGNALFORGE_REPO:-$HOME/personal/signalforge}"
  py="$repo/.venv/bin/python"
  [ -x "$py" ] || { log "images tick: $py missing, run uv sync"; return 0; }
  out=$(API_BASE_URL="$API_BASE_URL" EDITOR_API_KEY="${EDITOR_API_KEY:-$SIGNALFORGE_KEY}" \
    SIGNALFORGE_KEY="$SIGNALFORGE_KEY" "$py" "$repo/skills/article-images/scripts/articleimg.py" auto 2>&1) || {
    log "images tick failed: $(echo "$out" | tail -2 | tr '\n' ' ')"; return 0; }
  [ -n "$out" ] || return 0
  echo "$out" | while IFS= read -r line; do log "images tick: $line"; done
  echo "$out" | grep -q '^OK ' && revalidate_site
  return 0
}

if [ ! -d "$LOCK" ]; then publish_tick; images_tick; fi

slot="$(date '+%Y-%m-%d')-$(printf '%02d' $(( 10#$(date +%H) / 6 * 6 )))"
done_slot=$(sed -n 1p "$STATE" 2>/dev/null || true)
fail_slot=$(sed -n 2p "$STATE" 2>/dev/null || true)
fails=$(sed -n 3p "$STATE" 2>/dev/null || echo 0)
[ "$done_slot" = "$slot" ] && exit 0
if [ "$fail_slot" = "$slot" ] && [ "${fails:-0}" -ge 3 ]; then exit 0; fi
[ "$fail_slot" = "$slot" ] || fails=0

# Single instance (mkdir is atomic). Break a stale lock whose pid is gone.
if ! mkdir "$LOCK" 2>/dev/null; then
  pid=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then exit 0; fi
  rm -rf "$LOCK"; mkdir "$LOCK" || exit 0
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

# Need network before starting (wifi is slow after wake).
for i in 1 2 3 4 5 6; do
  curl -sS --max-time 15 -o /dev/null "$API_BASE_URL/agent/runs" -H "X-Editor-Key: $EDITOR_API_KEY" && break
  [ "$i" -eq 6 ] && { log "backend unreachable, will retry next interval"; exit 0; }
  sleep 20
done

log "slot $slot start (attempt $((fails + 1)))"
if caffeinate -i "$HOME/bin/signalforge_cron_pipeline.sh" >> "$LOG" 2>&1; then
  printf '%s\n\n0\n' "$slot" > "$STATE"
  log "slot $slot done"
else
  printf '%s\n%s\n%s\n' "$done_slot" "$slot" "$((fails + 1))" > "$STATE"
  log "slot $slot FAILED (attempt $((fails + 1)))"
fi
