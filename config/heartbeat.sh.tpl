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

# Stale-lock recovery — issue #374. When the prior heartbeat's `claude -p` hangs
# (e.g. self-matching `pgrep -f` wait loops), the lockfile is held forever and
# every cron tick SKIPs silently. If the dispatch state has not advanced for
# longer than the threshold, kill the holders, force-close the cycle, and let
# this beat proceed. Set EDGE_HEARTBEAT_STALE_LOCK_SEC=0 to disable.
EDGE_HEARTBEAT_STALE_LOCK_SEC="${EDGE_HEARTBEAT_STALE_LOCK_SEC:-5400}"

try_recover_stale_lock() {
    [ "$EDGE_HEARTBEAT_STALE_LOCK_SEC" -gt 0 ] 2>/dev/null || return 1
    [ -f "$CURRENT_DISPATCH_FILE" ] || return 1
    local age stale_cycle holders
    age=$(python3 -c '
import json, sys, os
from datetime import datetime, timezone
try:
    state = json.load(open(sys.argv[1])).get("state", {}) or {}
except Exception:
    sys.exit(0)
ts = state.get("updated_at") or state.get("opened_at")
if not ts:
    sys.exit(0)
try:
    dt = datetime.fromisoformat(ts)
except ValueError:
    sys.exit(0)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
print(int((datetime.now(timezone.utc) - dt).total_seconds()))
' "$CURRENT_DISPATCH_FILE" 2>/dev/null)
    [ -n "$age" ] || return 1
    [ "$age" -gt "$EDGE_HEARTBEAT_STALE_LOCK_SEC" ] || return 1
    stale_cycle=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("cycle_id",""))' "$CURRENT_DISPATCH_FILE" 2>/dev/null)
    echo "[$(date +%H:%M)] STALE LOCK — cycle=$stale_cycle age=${age}s threshold=${EDGE_HEARTBEAT_STALE_LOCK_SEC}s; killing holders and force-closing" >> "$LOGFILE"
    holders=$(fuser "$LOCKFILE" 2>/dev/null | tr -s ' ')
    if [ -n "$holders" ]; then
        for pid in $holders; do kill -TERM "$pid" 2>/dev/null || true; done
        sleep 5
        for pid in $holders; do kill -KILL "$pid" 2>/dev/null || true; done
    fi
    if [ -n "$stale_cycle" ]; then
        EDGE_CYCLE_ID="$stale_cycle" "$EDGE_REPO_DIR/tools/edge-dispatch" close \
            --status failed --reason stale_lock >> "$LOGFILE" 2>&1 || true
    fi
    rm -f "$LOCKFILE"
    return 0
}

# Prevent overlapping heartbeats
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    if try_recover_stale_lock; then
        exec 200>"$LOCKFILE"
        if ! flock -n 200; then
            echo "[$(date +%H:%M)] SKIP — could not acquire lock after stale recovery" >> "$LOGFILE"
            exit 1
        fi
    else
        echo "[$(date +%H:%M)] SKIP — previous heartbeat still running" >> "$LOGFILE"
        exit 0
    fi
fi

mkdir -p "$LOGS_DIR"

cd "$EDGE_REPO_DIR"

run_heartbeat() {
    "$EDGE_REPO_DIR/tools/edge-runner" skill \
        --skill "$SKILL" \
        --dispatch-trigger heartbeat \
        --dispatch-policy autonomous \
        --dispatch-routing-mode auto \
        --dispatch-preflight-profile heartbeat_default \
        --dispatch-postflight-profile standard \
        --dispatch-force \
        --dangerously-skip-permissions
}

# Systemd should stay quiet and log to file. Manual terminal runs should show
# the dispatch and follow-on skill live while still keeping the same log trail.
HEARTBEAT_STATUS=0
if [[ -t 1 || "${EDGE_HEARTBEAT_FOREGROUND:-0}" == "1" ]]; then
    run_heartbeat 2>&1 | tee -a "$LOGFILE"
    HEARTBEAT_STATUS=${PIPESTATUS[0]}
else
    run_heartbeat >> "$LOGFILE" 2>&1
    HEARTBEAT_STATUS=$?
fi

# Index new content after heartbeat
if command -v edge-index &>/dev/null; then
    for f in "$ENTRIES_DIR/"*.md; do
        [ -f "$f" ] && edge-index "$f" 2>/dev/null
    done
fi

exit "$HEARTBEAT_STATUS"
