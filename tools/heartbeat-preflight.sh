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
HEALTH_FILE="$HEALTH_CURRENT_FILE"

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

# 0a. State anchors — deterministic diff + dispatch enqueue
STATE_MONITOR_BIN="$TOOLS_DIR/edge-state-dispatch"
if [ -x "$STATE_MONITOR_BIN" ]; then
  state_monitor_output=$("$STATE_MONITOR_BIN" 2>/dev/null || true)
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    case "$line" in
      STATE_CHANGE*|STATE_QUEUE*|STATE_DIFF*)
        SIGNALS+=("$line")
        ;;
    esac
  done <<< "$state_monitor_output"
fi

# 0b. Stub primitives — implement ALL before any beat runs (#191)
PRIMITIVES_LIBEXEC_DIR="$LIBEXEC_DIR"
if [ -d "$PRIMITIVES_LIBEXEC_DIR" ]; then
  STUBS=()
  for prim in "$PRIMITIVES_LIBEXEC_DIR"/*; do
    [ -f "$prim" ] || continue
    [[ "$prim" == *.meta.yaml ]] && continue
    if grep -q 'exit 127' "$prim" 2>/dev/null; then
      STUBS+=("$(basename "$prim")")
    fi
  done

  if [ ${#STUBS[@]} -gt 0 ]; then
    echo "=== PREFLIGHT $(date +%H:%M) ==="
    echo "PREFLIGHT_STUBS (${#STUBS[@]} unimplemented primitives)"
    echo "Implementing before heartbeat can start..."
    for stub_name in "${STUBS[@]}"; do
      stub_path="$PRIMITIVES_LIBEXEC_DIR/$stub_name"
      meta_path="$PRIMITIVES_LIBEXEC_DIR/${stub_name}.meta.yaml"
      desc=""
      if [ -f "$meta_path" ]; then
        desc=$(cat "$meta_path")
      fi
      echo "  → Implementing: $stub_name"
      # Generate implementation via claude -p
      claude -p "You are implementing a source primitive for an autonomous agent.

Primitive name: $stub_name
Location: $stub_path
Contract (meta.yaml):
$desc

Write a bash script that implements this primitive. The script must:
1. Be a valid bash script with #!/usr/bin/env bash
2. Accept arguments from the command line
3. Output JSON to stdout on success
4. Exit 0 on success, non-zero on error
5. Use only standard tools (curl, python3, jq) — no pip installs
6. Source secrets from \$EDGE_DIR/secrets/keys.env if API keys are needed
7. Be concise — under 80 lines

Output ONLY the script content, no explanation." > "${stub_path}.new" 2>/dev/null

      if [ -s "${stub_path}.new" ]; then
        mv "${stub_path}.new" "$stub_path"
        chmod +x "$stub_path"
        # Test: call with no args, must not exit 127
        "$stub_path" --help >/dev/null 2>&1 || "$stub_path" >/dev/null 2>&1
        rc=$?
        if [ $rc -eq 127 ]; then
          echo "    FAIL: still returns 127 after implementation"
        else
          echo "    OK: implemented (exit $rc)"
        fi
      else
        rm -f "${stub_path}.new"
        echo "    FAIL: claude -p returned empty"
      fi
    done
    echo ""
  fi
fi

# 0c. Primitive self-healing — deterministic reprobe before LLM dispatch
SELF_HEALING_BIN="$TOOLS_DIR/edge-self-healing"
if [ -x "$SELF_HEALING_BIN" ]; then
  self_healing_json=$("$SELF_HEALING_BIN" --json 2>/dev/null || true)
  self_healing_signal=$(python3 -c "
import json, sys
try:
    payload = json.loads(sys.stdin.read() or '{}')
    summary = payload.get('summary') or {}
    recovered = int(summary.get('recovered_total') or 0)
    needs = payload.get('needs_llm') or []
    if needs:
        names = ','.join(str(item.get('primitive') or '') for item in needs if item.get('primitive'))
        print(f'SELF_HEALING:NEEDS_LLM {len(needs)} primitives ({names})')
    elif recovered:
        print(f'SELF_HEALING:RECOVERED {recovered} primitives')
except Exception:
    pass
" <<< "$self_healing_json" 2>/dev/null)
  if [ -n "$self_healing_signal" ]; then
    SIGNALS+=("$self_healing_signal")
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

# 3. Open-gap continuity pressure — lightweight projection check
OPEN_GAPS_FILE="$PROJECTIONS_DIR/open-gaps-digest.json"
if [ -f "$OPEN_GAPS_FILE" ]; then
  open_gaps_count=$(python3 -c "
import json
from pathlib import Path
data = json.loads(Path('$OPEN_GAPS_FILE').read_text())
print(int(data.get('open_total') or 0))
" 2>/dev/null || echo 0)
  if [ "$open_gaps_count" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("GAPS:${open_gaps_count} open gaps")
  fi
fi

# 5. Source primitive usage — check last beat
USAGE_LOG="$SOURCE_USAGE_FILE"
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

# 5b. Holding queue — artifacts BLOCKED awaiting drain (#206)
HOLDING_INDEX="$STATE_DIR/holding/index.json"
if [ -f "$HOLDING_INDEX" ]; then
  hold_summary=$(python3 -c "
import json
try:
    d = json.load(open('$HOLDING_INDEX'))
    count = d.get('count', 0)
    if count:
        by_class = d.get('by_class', {})
        oldest = d.get('oldest', '')
        parts = [f'{k}={v}' for k, v in sorted(by_class.items())]
        print(f'{count} ({\" \".join(parts)}) oldest={oldest}')
except: pass
" 2>/dev/null)
  if [ -n "$hold_summary" ]; then
    SIGNALS+=("HOLD:$hold_summary — drain queue: check state/api keys, re-run consolidate-state")
  fi
fi

# 5c. Missing primitives — exit 127 was recorded (#206 + #191)
MISSING_FLAG="$STATE_DIR/missing-primitives.json"
if [ -f "$MISSING_FLAG" ]; then
  missing_names=$(python3 -c "
import json
try:
    d = json.load(open('$MISSING_FLAG'))
    prims = list(d.get('primitives', {}).keys())
    if prims:
        print(','.join(prims[:5]) + (f' (+{len(prims)-5} more)' if len(prims) > 5 else ''))
except: pass
" 2>/dev/null)
  if [ -n "$missing_names" ]; then
    SIGNALS+=("MISSING_PRIMITIVES:$missing_names — implement before next source-class beat")
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
  echo "No signals detected. Use action-skill rotation with heartbeat curation context."
else
  echo "PREFLIGHT_WORK (${#SIGNALS[@]} signals)"
  for s in "${SIGNALS[@]}"; do
    echo "  → $s"
  done
fi
