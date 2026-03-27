#!/usr/bin/env bash
# heartbeat-preflight.sh — deterministic check before invoking LLM
# Cost: ~2-3 seconds, zero tokens
# Exit 0 + signals on stdout = there's work → normal heartbeat
# Exit 0 + "PREFLIGHT_CLEAN" = nothing urgent → explore

set -uo pipefail

TODAY=$(date +%Y-%m-%d)
SIGNALS=()

# --- Load shared paths (branding, memory, blog config) ---
# shellcheck source=../config/paths.sh
source "$(dirname "$0")/../config/paths.sh"

# 0. Health check (runs edge-check.sh, updates health/current.json)
HEALTH_SCRIPT="$(dirname "$0")/../bin/edge-check.sh"
HEALTH_FILE="$EDGE_DIR/health/current.json"

if [ -x "$HEALTH_SCRIPT" ]; then
  bash "$HEALTH_SCRIPT" >/dev/null 2>&1
fi

if [ -f "$HEALTH_FILE" ]; then
  health_score=$(python3 -c "import json; print(json.load(open('$HEALTH_FILE')).get('score', 100))" 2>/dev/null || echo 100)
  health_status=$(python3 -c "import json; print(json.load(open('$HEALTH_FILE')).get('status', 'unknown'))" 2>/dev/null || echo "unknown")

  if [ "$health_status" = "critical" ] || [ "$health_score" -lt 40 ] 2>/dev/null; then
    SIGNALS+=("HEALTH:CRITICAL score=${health_score} — maintenance mode, repair before working")
  elif [ "$health_status" = "unhealthy" ] || [ "$health_score" -lt 70 ] 2>/dev/null; then
    SIGNALS+=("HEALTH:UNHEALTHY score=${health_score} — reserve part of beat for repair")
  elif [ "$health_status" = "degraded" ] || [ "$health_score" -lt 85 ] 2>/dev/null; then
    SIGNALS+=("HEALTH:DEGRADED score=${health_score} — 1 remediation action recommended")
  fi
fi

# 1. Pending chat?
chat_pending=$(curl -s --max-time 3 $CURL_AUTH "http://localhost:${BLOG_PORT}/api/chat?unprocessed=true" 2>/dev/null | \
  python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    msgs = [m for m in data.get('messages', []) if m.get('author') == 'user' and not m.get('processed')]
    print(len(msgs))
except: print(0)
" 2>/dev/null || echo 0)

if [ "$chat_pending" -gt 0 ] 2>/dev/null; then
  SIGNALS+=("CHAT:${chat_pending} pending messages")
fi

# 2. Threads with resurface <= today?
for f in "$THREADS_DIR"/*.md; do
  [ -f "$f" ] || continue
  status=$(grep '^status:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  resurface=$(grep '^resurface:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  title=$(grep '^title:' "$f" 2>/dev/null | head -1 | sed 's/^title: *//' | tr -d '"')
  owner=$(grep '^owner:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  if [ "$status" = "active" ] || [ "$status" = "waiting" ]; then
    if [ -n "$resurface" ] && [[ "$resurface" < "$TODAY" || "$resurface" == "$TODAY" ]]; then
      SIGNALS+=("THREAD:[$status] $title (owner:$owner)")
    fi
  fi
done

# 3. Pending errors in debugging.md?
debug_file="${MEMORY_BASE}/debugging.md"
if [ -f "$debug_file" ]; then
  open_errors=$(grep -ci 'status:.*aberto\|status:.*open\|\[ \]' "$debug_file" 2>/dev/null || echo 0)
  if [ "$open_errors" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("ERROR:${open_errors} pending errors")
  fi
fi

# 4. Recent operator session (last 2h)?
# PROJECT_DIR already set by paths.sh
latest_session=$(ls -t "${PROJECT_DIR}"/*.jsonl 2>/dev/null | head -1)
if [ -n "$latest_session" ]; then
  session_age=$(( $(date +%s) - $(stat -c %Y "$latest_session" 2>/dev/null || echo 0) ))
  if [ "$session_age" -lt 7200 ] 2>/dev/null; then
    SIGNALS+=("SESSION:recent interactive session ($(( session_age / 60 ))min ago)")
  fi
fi

# Result
echo "=== PREFLIGHT $(date +%H:%M) ==="
if [ ${#SIGNALS[@]} -eq 0 ]; then
  echo "PREFLIGHT_CLEAN"
  echo "No signals detected. Use round-robin rotation (2 content + 1 meta every 3rd beat)."
else
  echo "PREFLIGHT_WORK (${#SIGNALS[@]} signals)"
  for s in "${SIGNALS[@]}"; do
    echo "  → $s"
  done
fi
