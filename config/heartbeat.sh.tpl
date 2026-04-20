#!/bin/bash
# Heartbeat wrapper — called by systemd timer every {{ HEARTBEAT_INTERVAL }}
# Locks to prevent overlap, invokes edge-runner with the heartbeat skill.

set -uo pipefail

EDGE_REPO_DIR="{{ WORK_DIR }}"
# shellcheck source=../config/paths.sh
source "$EDGE_REPO_DIR/config/paths.sh"

LOCKFILE="/tmp/edge-heartbeat-{{ CODENAME }}.lock"
LOGFILE="$LOGS_DIR/heartbeat-$(date +%Y-%m-%d).log"
SKILL="/{{ SKILL_PREFIX }}-heartbeat"

# Load secrets
[ -f "$SECRETS_DIR/keys.env" ] && set -a && source "$SECRETS_DIR/keys.env" && set +a

# Prevent overlapping heartbeats
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "[$(date +%H:%M)] SKIP — previous heartbeat still running" >> "$LOGFILE"
    exit 0
fi

mkdir -p "$LOGS_DIR"

cd "$EDGE_REPO_DIR"

# Run heartbeat through our CLI boundary. The runner owns the shadow
# dispatch lifecycle so the skill body no longer needs to open/close it.
"$EDGE_REPO_DIR/tools/edge-runner" skill \
    --skill "$SKILL" \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force \
    --dangerously-skip-permissions \
    >> "$LOGFILE" 2>&1

# Index new content after heartbeat
if command -v edge-index &>/dev/null; then
    for f in "$ENTRIES_DIR/"*.md; do
        [ -f "$f" ] && edge-index "$f" 2>/dev/null
    done
fi
