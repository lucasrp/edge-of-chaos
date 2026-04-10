#!/bin/bash
# Heartbeat wrapper — called by systemd timer every {{ HEARTBEAT_INTERVAL }}
# Locks to prevent overlap, invokes Claude Code with the heartbeat skill.

set -uo pipefail

EDGE_DIR="{{ WORK_DIR }}"
LOCKFILE="/tmp/edge-heartbeat-{{ CODENAME }}.lock"
LOGFILE="$EDGE_DIR/logs/heartbeat-$(date +%Y-%m-%d).log"
SKILL="/{{ SKILL_PREFIX }}-heartbeat"

# Load secrets
[ -f "$EDGE_DIR/secrets/keys.env" ] && set -a && source "$EDGE_DIR/secrets/keys.env" && set +a

# Prevent overlapping heartbeats
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "[$(date +%H:%M)] SKIP — previous heartbeat still running" >> "$LOGFILE"
    exit 0
fi

mkdir -p "$(dirname "$LOGFILE")"

cd "$EDGE_DIR"

# Run Claude Code with the heartbeat skill
# No budget limit — subscription covers Claude tokens.
# Real API costs (OpenAI, Exa) are cents per heartbeat.
# Timeout controlled by systemd TimeoutStartSec (1h).
# External access uses primitives in libexec/ (work in any mode).
claude -p "$SKILL" \
    --dangerously-skip-permissions \
    >> "$LOGFILE" 2>&1

# Index new content after heartbeat (bulk — covers entries, reports, notes)
if command -v edge-index &>/dev/null; then
    index_output=$(edge-index "$EDGE_DIR/blog/entries/" "$EDGE_DIR/reports/" "$EDGE_DIR/notes/" --no-embed 2>&1 | tail -1)
    echo "[$(date +%H:%M)] INDEX: $index_output" >> "$LOGFILE"
    # Update health marker so check-infra.sh sees fresh index
    mkdir -p "$EDGE_DIR/health/last_success"
    jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{ts:$ts, source:"heartbeat"}' \
      > "$EDGE_DIR/health/last_success/index.ok"
fi
