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

# 4. Corpus curation — run every beat, lightweight
CURATION_FILE="$EDGE_DIR/state/procedure-curation.json"
if command -v edge-crystallize &>/dev/null; then
  # Regenerate curation if stale (>2h) or missing
  curation_stale=false
  if [ ! -f "$CURATION_FILE" ]; then
    curation_stale=true
  else
    curation_age=$(( $(date +%s) - $(stat -c %Y "$CURATION_FILE" 2>/dev/null || echo 0) ))
    if [ "$curation_age" -gt 7200 ] 2>/dev/null; then
      curation_stale=true
    fi
  fi

  if [ "$curation_stale" = true ]; then
    # Run corpus-curation in procedures mode (silent, no LLM)
    edge-crystallize --dry-run 2>/dev/null | grep -q "candidate" && \
      SIGNALS+=("CURATION:crystallization candidates detected")
  fi
fi

# 5. Source primitive usage — check last beat
USAGE_LOG="$EDGE_DIR/state/source-usage.jsonl"
if [ -f "$USAGE_LOG" ]; then
  recent_usage=$(python3 -c "
import json
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(minutes=120)
count = 0
with open('$USAGE_LOG') as f:
    for line in f:
        try:
            e = json.loads(line.strip())
            ts = datetime.fromisoformat(e['ts'].replace('Z', '+00:00'))
            if ts >= cutoff and e.get('phase') == 'end': count += 1
        except: pass
print(count)" 2>/dev/null || echo 0)
  if [ "${recent_usage:-0}" -eq 0 ]; then
    SIGNALS+=("SOURCE:no primitive usage last beat — use edge-source <primitive> for all source operations")
  fi
else
  SIGNALS+=("SOURCE:source-usage.jsonl missing — no primitives have ever been called")
fi

# 5b. Missing primitives (from #206 edge-source halt-flag)
# Surface primitives that have been requested but don't exist or aren't
# implemented. Without this, exit 127 is a hint the agent can ignore;
# primitives stay broken for days. If anything recent, route next beat to build.
MISSING_LOG="$EDGE_DIR/state/missing-primitives.jsonl"
if [ -f "$MISSING_LOG" ]; then
  missing_summary=$(python3 -c "
import json
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
counts = {}
try:
    with open('$MISSING_LOG') as f:
        for line in f:
            try:
                e = json.loads(line.strip())
                ts = datetime.fromisoformat(e['ts'].replace('Z', '+00:00'))
                if ts >= cutoff:
                    key = f\"{e.get('primitive','?')}({e.get('reason','?')})\"
                    counts[key] = counts.get(key, 0) + 1
            except: pass
    if counts:
        top = sorted(counts.items(), key=lambda x: -x[1])[:3]
        print(','.join(f'{k}x{v}' for k,v in top))
except: pass" 2>/dev/null || echo "")
  if [ -n "$missing_summary" ]; then
    SIGNALS+=("PRIMITIVE:missing in last 24h — $missing_summary (next beat should materialize per TOOL_CONTRACT.md)")
  fi
fi

# 6. Hold queue (from #206 adversarial review BLOCKED state)
# Surface artifacts blocked in review so preflight routes to drain before
# new work. Without this, blocked artifacts age silently in holding/.
HOLD_INDEX="$EDGE_DIR/holding/index.json"
if [ -f "$HOLD_INDEX" ]; then
  hold_summary=$(python3 -c "
import json, time
try:
    idx = json.load(open('$HOLD_INDEX'))
    count = idx.get('count', 0)
    if count > 0:
        now = int(time.time())
        oldest = min((i.get('first_seen', now) for i in idx.get('items', [])), default=now)
        age_h = (now - oldest) // 3600
        by_class = idx.get('by_class', {})
        cls = ','.join(f'{k}:{v}' for k,v in by_class.items())
        print(f'{count} artifacts blocked ({cls}) — oldest {age_h}h')
except: pass" 2>/dev/null || echo "")
  if [ -n "$hold_summary" ]; then
    SIGNALS+=("HOLD:$hold_summary — resolve blocking condition, then re-run consolidate-state to drain")
  fi
fi

# 6. Recent operator session (last 2h)?
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
