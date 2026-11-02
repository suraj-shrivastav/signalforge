#!/bin/bash
# SignalForge cron pipeline: tick -> accept topmost -> research -> draft -> auto-review -> publish-next
# Runs on the deployed backend only (no localhost).
# Owner policy (2026-11-01): no approval needed; one topmost-scored card per run.
set -euo pipefail

cd "${SIGNALFORGE_REPO:-$HOME/personal/signalforge}"

API="${API_BASE_URL:-https://signalforge-wmtl.onrender.com}"
KEY="${SIGNALFORGE_KEY:-}"
EDITOR_KEY="${EDITOR_API_KEY:-${KEY}}"

if [ -z "$KEY" ]; then
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') ERROR: SIGNALFORGE_KEY not set" >> "$HOME/signalforge-cron.log"
  exit 1
fi

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" >> "$HOME/signalforge-cron.log"; }

# Wait for a stage to finish. Returns 0 when idle, 1 after 30 min.
wait_stage() {
  local name="$1"
  for i in $(seq 1 30); do
    local run running
    run=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 "$API/agent/runs" -H "X-Editor-Key: $EDITOR_KEY")
    running=$(echo "$run" | jq -r '.running.stage // empty')
    if [ -z "$running" ]; then
      log "$name finished"
      return 0
    fi
    if [ "$i" -eq 30 ]; then
      log "$name still running after 30 minutes, giving up"
      return 1
    fi
    sleep 60
  done
  return 1
}

# Auto-accept the single topmost proposed card (highest score) per run
accept_best_cards() {
  log "GET /cards/queue (auto-accept topmost)"
  local queue
  queue=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 "$API/cards/queue?limit=50" -H "X-Editor-Key: $EDITOR_KEY")

  local ids
  ids=$(echo "$queue" | jq -r '[.[] | select(.status=="proposed")] | sort_by(.score) | reverse | .[0:1] | .[] | .id')

  if [ -z "$ids" ]; then
    log "no proposed cards to accept"
    return 0
  fi

  local accepted=0
  while IFS= read -r id; do
    [ -z "$id" ] && continue
    local title score
    title=$(echo "$queue" | jq -r --arg id "$id" '.[] | select(.id==$id) | .signal.title // .title // "unknown"')
    score=$(echo "$queue" | jq -r --arg id "$id" '.[] | select(.id==$id) | .score')
    log "accepting card $id (score $score): $title"
    local resp http_code
    resp=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -w "\n%{http_code}" -X POST "$API/cards/$id/decision" \
      -H "X-Editor-Key: $KEY" -H "Content-Type: application/json" \
      -d "{\"decision\":\"accepted\",\"note\":\"auto-accepted: topmost by score\"}")
    http_code=$(echo "$resp" | tail -n1)
    log "accept $id: HTTP $http_code"
    # The API answers 201 Created for a decision; accept 200 as well.
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
      accepted=$((accepted + 1))
    fi
  done <<< "$ids"

  log "auto-accepted $accepted card(s)"
}

# 1. Tick: ingest, assess, build cards, research, draft
log "POST /agent/run/tick"
resp=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -X POST "$API/agent/run/tick" -H "X-Editor-Key: $KEY")
log "tick: $resp"
echo "$resp" | jq -e '.started == true' >/dev/null || { log "tick failed to start: $resp"; exit 1; }
wait_stage "tick" || exit 1

# 2. Accept the topmost proposed card from the queue
accept_best_cards

# 3-5. Research -> draft -> auto-review, repeated once if the accepted card did not reach review.
review_and_publish() {
  local work ids card_id resp action n
  work=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 "$API/agent/work" -H "X-Editor-Key: $EDITOR_KEY")
  # No mapfile/readarray: macOS /bin/bash is 3.2 and lacks them.
  ids=$(echo "$work" | jq -r '[.cards[] | select(.next_action=="auto_review") | .card_id] | .[0:3] | .[]')
  while IFS= read -r card_id; do
    [ -z "$card_id" ] && continue
    for n in 1 2 3; do
      log "auto-review $card_id (try $n)"
      resp=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -X POST "$API/agent/drafts/$card_id/auto-review?publish=true" -H "X-Editor-Key: $KEY")
      log "auto-review $card_id: $resp"
      action=$(echo "$resp" | jq -r '.action // empty')
      [ "$action" = "revise" ] || break
      [ "$n" -lt 3 ] || break
      log "revise requested, POST /agent/run/revise"
      curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -X POST "$API/agent/run/revise" -H "X-Editor-Key: $KEY" >/dev/null || break
      wait_stage "revise" || break
    done
  done <<< "$ids"
}

for attempt in 1 2; do
  work=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 "$API/agent/work" -H "X-Editor-Key: $EDITOR_KEY")
  waiting=$(echo "$work" | jq '[.cards[] | select(.next_action=="run_research" or .next_action=="retry_research")] | length' 2>/dev/null || echo 1)
  case "$waiting" in ''|*[!0-9]*) waiting=1 ;; esac
  if [ "$waiting" -lt 1 ]; then waiting=1; fi
  if [ "$waiting" -gt 3 ]; then waiting=3; fi
  log "POST /agent/run/research (limit=$waiting, attempt $attempt)"
  resp=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -X POST "$API/agent/run/research?retry_failed=true&limit=$waiting" -H "X-Editor-Key: $KEY")
  log "research: $resp"
  echo "$resp" | jq -e '.started == true' >/dev/null || { log "research failed to start: $resp"; exit 1; }
  wait_stage "research" || exit 1

  log "POST /agent/run/draft (attempt $attempt)"
  resp=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -X POST "$API/agent/run/draft?retry_failed=true" -H "X-Editor-Key: $KEY")
  log "draft: $resp"
  echo "$resp" | jq -e '.started == true' >/dev/null || { log "draft failed to start: $resp"; exit 1; }
  wait_stage "draft" || exit 1

  work=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 "$API/agent/work" -H "X-Editor-Key: $EDITOR_KEY")
  ready=$(echo "$work" | jq '[.cards[] | select(.next_action=="auto_review")] | length' 2>/dev/null || echo 0)
  [ "${ready:-0}" -gt 0 ] && break
  log "no draft ready for review after attempt $attempt"
done
review_and_publish

# 6. Publish the longest-waiting approved draft if a pacing slot is open
log "POST /agent/publish-next"
resp=$(curl -sS --retry 4 --retry-delay 20 --retry-all-errors --max-time 180 -X POST "$API/agent/publish-next" -H "X-Editor-Key: $KEY")
log "publish-next: $resp"

log "cron pipeline complete"
