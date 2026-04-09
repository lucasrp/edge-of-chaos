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

# Index new content after heartbeat
if command -v edge-index &>/dev/null; then
    for f in "$EDGE_DIR/blog/entries/"*.md; do
        [ -f "$f" ] && edge-index "$f" 2>/dev/null
    done
fi
