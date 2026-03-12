#!/usr/bin/env bash
# heartbeat-preflight.sh — deterministic checks before invoking LLM
# Cost: ~2-3 seconds, zero tokens
# Exit 0 + signals in stdout = work found -> normal heartbeat
# Exit 0 + "PREFLIGHT_CLEAN" = nothing urgent -> explore (leisure, discovery)
#
# Configure: set EDGE_PROJECT_SLUG env var to match your Claude project slug.
# Remote agent checks (check 6) are optional — remove or customize the SSH target.

set -uo pipefail

TODAY=$(date +%Y-%m-%d)
SIGNALS=()

# Configurable project slug for Claude project paths
PROJECT_SLUG="${EDGE_PROJECT_SLUG:-default}"

# 1. Chat pending?
chat_pending=$(curl -s --max-time 3 'http://localhost:8766/api/chat?unprocessed=true' 2>/dev/null | \
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
for f in ~/edge/threads/*.md; do
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

# 3. New insight (unread)?
insights_file=~/.claude/projects/${PROJECT_SLUG}/memory/insights.md
if [ -f "$insights_file" ]; then
  new_insights=$(grep -c '^\-' "$insights_file" 2>/dev/null || echo 0)
  read_insights=$(grep -c '\[READ' "$insights_file" 2>/dev/null || echo 0)
  unread=$((new_insights - read_insights))
  if [ "$unread" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("INSIGHT:${unread} new insights")
  fi
fi

# 4. Open errors in debugging.md?
debug_file=~/.claude/projects/${PROJECT_SLUG}/memory/debugging.md
if [ -f "$debug_file" ]; then
  open_errors=$(grep -ci 'status:.*open\|\[ \]' "$debug_file" 2>/dev/null || echo 0)
  if [ "$open_errors" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("ERROR:${open_errors} pending errors")
  fi
fi

# 5. Recent interactive session (last 2 hours)?
latest_session=$(ls -t ~/.claude/projects/${PROJECT_SLUG}/*.jsonl 2>/dev/null | head -1)
if [ -n "$latest_session" ]; then
  session_age=$(( $(date +%s) - $(stat -c %Y "$latest_session" 2>/dev/null || echo 0) ))
  if [ "$session_age" -lt 7200 ] 2>/dev/null; then
    SIGNALS+=("SESSION:recent interactive session ($(( session_age / 60 ))min ago)")
  fi
fi

# 6. Remote agent error? (optional — configure SSH target or remove this check)
# Uncomment and set REMOTE_AGENT to enable:
# REMOTE_AGENT="${EDGE_REMOTE_AGENT:-}"
# if [ -n "$REMOTE_AGENT" ]; then
#   remote_last_error=$(ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$REMOTE_AGENT" \
#     "tail -1 ~/edge/logs/heartbeat-${TODAY}.log 2>/dev/null" 2>/dev/null || echo "")
#   if echo "$remote_last_error" | grep -qi "error\|fail" 2>/dev/null; then
#     SIGNALS+=("REMOTE:error detected in last beat on $REMOTE_AGENT")
#   fi
# fi

# 7. Inbox files? (optional — configure INBOX_DIRS or remove this check)
# Uncomment and set INBOX_DIRS to enable:
# INBOX_DIRS="${EDGE_INBOX_DIRS:-}"
# inbox_count=0
# if [ -n "$INBOX_DIRS" ]; then
#   IFS=',' read -ra DIRS <<< "$INBOX_DIRS"
#   for dir in "${DIRS[@]}"; do
#     if [ -d "$dir" ]; then
#       count=$(find "$dir" -type f -name "*.md" -o -name "*.txt" 2>/dev/null | wc -l)
#       inbox_count=$((inbox_count + count))
#     fi
#   done
#   if [ "$inbox_count" -gt 0 ] 2>/dev/null; then
#     SIGNALS+=("INBOX:${inbox_count} files in inbox")
#   fi
# fi

# Result
echo "=== PREFLIGHT $(date +%H:%M) ==="
if [ ${#SIGNALS[@]} -eq 0 ]; then
  echo "PREFLIGHT_CLEAN"
  echo "No signals detected. Suggestion: leisure or discovery skill."
else
  echo "PREFLIGHT_WORK (${#SIGNALS[@]} signals)"
  for s in "${SIGNALS[@]}"; do
    echo "  -> $s"
  done
fi
