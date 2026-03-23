#!/usr/bin/env bash
# notify.sh — Unified notification routing
# Usage: notify <type> <message> [--file <path>]
#
# Types: heartbeat, alert, report, default
# Routes to the correct Slack channel based on config/features.yaml
# Falls back gracefully: bot_token > webhook > chat API > silent
#
# Examples:
#   notify heartbeat "Beat #5 — /ed-pesquisa sobre DSPy"
#   notify report "Relatório: IAA Protocol" --file ~/edge/reports/report.html
#   notify alert "Health degraded: score 45"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EDGE_DIR="$(dirname "$SCRIPT_DIR")"

TYPE="${1:-default}"
MESSAGE="${2:-}"
FILE=""

# Parse --file argument
shift 2 2>/dev/null || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --file) FILE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$MESSAGE" ]]; then
  echo "Usage: notify <type> <message> [--file <path>]" >&2
  exit 1
fi

# ─── Load config ─────────────────────────────────────────────────────────────

FEATURES_FILE="$EDGE_DIR/config/features.yaml"
SECRETS_FILE="$EDGE_DIR/secrets/_shared.yaml"

# Read a YAML value (simple — no nested arrays)
yaml_val() {
  local file="$1" key="$2"
  python3 -c "
import yaml, sys
with open('$file') as f:
    data = yaml.safe_load(f) or {}
keys = '$key'.split('.')
obj = data
for k in keys:
    if isinstance(obj, dict):
        obj = obj.get(k, '')
    else:
        obj = ''
        break
print(obj if obj else '')
" 2>/dev/null
}

# Check if Slack is enabled
SLACK_ENABLED=$(yaml_val "$FEATURES_FILE" "notifications.slack.enabled" 2>/dev/null || echo "auto")

# Load secrets
BOT_TOKEN=$(yaml_val "$SECRETS_FILE" "communication.slack.bot_token" 2>/dev/null || echo "")
WEBHOOK_URL=$(yaml_val "$SECRETS_FILE" "communication.slack.webhook_url" 2>/dev/null || echo "")

# Resolve "auto"
if [[ "$SLACK_ENABLED" == "auto" ]]; then
  if [[ -n "$BOT_TOKEN" ]] || [[ -n "$WEBHOOK_URL" ]]; then
    SLACK_ENABLED="true"
  else
    SLACK_ENABLED="false"
  fi
fi

# ─── Resolve channel ────────────────────────────────────────────────────────

CHANNEL=""
if [[ "$SLACK_ENABLED" == "true" ]]; then
  CHANNEL=$(yaml_val "$FEATURES_FILE" "notifications.slack.channels.$TYPE" 2>/dev/null || echo "")
  if [[ -z "$CHANNEL" ]]; then
    CHANNEL=$(yaml_val "$FEATURES_FILE" "notifications.slack.channels.default" 2>/dev/null || echo "")
  fi
fi

# ─── Send ────────────────────────────────────────────────────────────────────

SENT=false

# Method 1: Slack Bot Token (rich — threading, upload, DMs)
if [[ -n "$BOT_TOKEN" ]] && [[ -n "$CHANNEL" ]]; then
  # Send text message
  RESPONSE=$(curl -s -X POST "https://slack.com/api/chat.postMessage" \
    -H "Authorization: Bearer $BOT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"channel\": \"$CHANNEL\", \"text\": \"[$TYPE] $MESSAGE\"}" 2>/dev/null)

  if echo "$RESPONSE" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('ok') else 1)" 2>/dev/null; then
    SENT=true

    # Upload file if provided
    if [[ -n "$FILE" ]] && [[ -f "$FILE" ]]; then
      # Get upload URL
      FILENAME=$(basename "$FILE")
      FILESIZE=$(stat -c%s "$FILE" 2>/dev/null || stat -f%z "$FILE" 2>/dev/null)
      UPLOAD_INFO=$(curl -s -X GET \
        "https://slack.com/api/files.getUploadURLExternal?filename=$FILENAME&length=$FILESIZE" \
        -H "Authorization: Bearer $BOT_TOKEN" 2>/dev/null)

      UPLOAD_URL=$(echo "$UPLOAD_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin).get('upload_url',''))" 2>/dev/null)
      FILE_ID=$(echo "$UPLOAD_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin).get('file_id',''))" 2>/dev/null)

      if [[ -n "$UPLOAD_URL" ]] && [[ -n "$FILE_ID" ]]; then
        # Upload the file
        curl -s -X POST "$UPLOAD_URL" \
          -F "file=@$FILE" 2>/dev/null

        # Complete upload
        curl -s -X POST "https://slack.com/api/files.completeUploadExternal" \
          -H "Authorization: Bearer $BOT_TOKEN" \
          -H "Content-Type: application/json" \
          -d "{\"files\": [{\"id\": \"$FILE_ID\"}], \"channel_id\": \"$CHANNEL\"}" 2>/dev/null >/dev/null
      fi
    fi
  fi
fi

# Method 2: Webhook (simple text — fallback)
if [[ "$SENT" == "false" ]] && [[ -n "$WEBHOOK_URL" ]]; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"[$TYPE] $MESSAGE\"}" 2>/dev/null)
  [[ "$HTTP_CODE" == "200" ]] && SENT=true
fi

# Method 3: Local chat API (always available)
BLOG_PORT=$(yaml_val "$EDGE_DIR/config/branding.yaml" "blog.port" 2>/dev/null || echo "8080")
curl -s -X POST "http://localhost:${BLOG_PORT}/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"author\": \"system\", \"text\": \"[$TYPE] $MESSAGE\"}" 2>/dev/null >/dev/null || true

# Log
echo "[$(date '+%Y-%m-%d %H:%M')] notify $TYPE: $MESSAGE (slack=$SENT)" >> "$EDGE_DIR/logs/notify.log" 2>/dev/null || true

if [[ "$SENT" == "true" ]]; then
  echo "sent via slack → $CHANNEL"
else
  echo "sent via local chat (slack unavailable)"
fi
