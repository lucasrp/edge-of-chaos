#!/usr/bin/env bash
# heartbeat-dispatch-guard.sh — enforce heartbeat Step 2 skill dispatch
#
# Claude Code PreToolUse hook. Receives tool invocation JSON on stdin.
# Blocks Write/Edit into artifact paths (~/edge/blog/entries, ~/edge/reports)
# when a heartbeat beat is active but no skill has been dispatched yet.
#
# Rationale: /ed-heartbeat Step 2 mandates dispatching one skill per beat.
# Under strong operator signal, the instruction-level rule fails (see #212,
# research enforcement-ladder 2026-04-09). This hook enforces the invariant
# at L3 (executable) — the earliest checkpoint in the pipeline.
#
# Exit codes:
#   0 — allow tool call (not in heartbeat, or skill already dispatched, or
#       write target is outside guarded paths)
#   2 — block tool call (message on stderr)
#
# Sentinel file (legacy): $EDGE_ROOT/state/current-beat.json
#   {
#     "active": bool,              # set true at Step 2 entry
#     "started_at": ISO8601,       # auto-expires after 1h
#     "skill_dispatched": bool,    # flipped to true immediately before dispatch
#     "skill": string|null
#   }
#
# Dispatch-cycle file (shadow rollout): $EDGE_ROOT/state/current-dispatch.json
#   {
#     "cycle_id": "...",
#     "request": {"trigger": "heartbeat", ...},
#     "state": {"active": true, "skill_dispatched": false, ...}
#   }
#
# Wire-up: add to ~/.claude/settings.json:
#   "hooks": {
#     "PreToolUse": [{
#       "matcher": "Write|Edit",
#       "hooks": [{ "type": "command",
#                   "command": "bash ~/edge/bin/heartbeat-dispatch-guard.sh" }]
#     }]
#   }

set -euo pipefail

EDGE_ROOT="${EDGE_ROOT:-$HOME/edge}"
STATE_FILE="${EDGE_ROOT}/state/current-beat.json"
DISPATCH_FILE="${EDGE_ROOT}/state/current-dispatch.json"

# Read PreToolUse payload from stdin
TOOL_INPUT=$(cat)
TOOL_NAME=$(python3 -c 'import json,sys; print((json.loads(sys.stdin.read() or "{}").get("tool_name") or ""))' <<<"$TOOL_INPUT" 2>/dev/null || true)
PATH_ARG=$(python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read() or "{}").get("tool_input", {}) or {}
    print(d.get("file_path") or d.get("notebook_path") or "")
except Exception:
    print("")
' <<<"$TOOL_INPUT" 2>/dev/null || true)

EDGE_CMD="${EDGE_REPO_DIR:-$EDGE_ROOT}/tools/edge-cmd"
if [ -n "$PATH_ARG" ] && [ -x "$EDGE_CMD" ]; then
  set +e
  "$EDGE_CMD" validate-write \
    --tool "${TOOL_NAME:-unknown}" \
    --path "$PATH_ARG" \
    --source heartbeat-dispatch-guard \
    --require-dispatched-heartbeat \
    --heartbeat-only
  STATUS=$?
  set -e
  exit "$STATUS"
fi

# Fast path: if neither state file exists, not in heartbeat → allow immediately
if [ ! -f "$STATE_FILE" ] && [ ! -f "$DISPATCH_FILE" ]; then
  exit 0
fi

python3 - <<'PY' "$STATE_FILE" "$DISPATCH_FILE" "$TOOL_INPUT"
import json
import sys
import datetime
import pathlib

legacy_path = pathlib.Path(sys.argv[1])
dispatch_path = pathlib.Path(sys.argv[2])
try:
    payload = json.loads(sys.argv[3])
except Exception:
    sys.exit(0)  # malformed payload, do not block

tool_input = payload.get("tool_input", {}) or {}
file_path = tool_input.get("file_path", "") or ""

# Only guard artifact paths
GUARDED = ("/edge/blog/entries/", "/edge/reports/")
if not any(seg in file_path for seg in GUARDED):
    sys.exit(0)

state = None
state_source = None

if dispatch_path.exists():
    try:
        dispatch = json.loads(dispatch_path.read_text())
        request = dispatch.get("request", {}) or {}
        state_block = dispatch.get("state", {}) or {}
        if state_block.get("active") and request.get("trigger") != "heartbeat":
            sys.exit(0)
        if request.get("trigger") == "heartbeat":
            state = {
                "active": state_block.get("active"),
                "started_at": state_block.get("opened_at"),
                "skill_dispatched": state_block.get("skill_dispatched"),
                "skill": request.get("skill"),
            }
            state_source = "current-dispatch.json"
    except Exception:
        state = None

if state is None and legacy_path.exists():
    try:
        state = json.loads(legacy_path.read_text())
        state_source = "current-beat.json"
    except Exception:
        sys.exit(0)  # unreadable sentinel, fail open

if state is None:
    sys.exit(0)

# Stale sentinel (>1h) — not a live beat
started_at = state.get("started_at")
if started_at:
    try:
        started = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        age_s = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
        if age_s > 3600:
            sys.exit(0)
    except Exception:
        pass

if not state.get("active"):
    sys.exit(0)

if state.get("skill_dispatched"):
    sys.exit(0)

# Active heartbeat, no skill dispatched, writing guarded path → block
sys.stderr.write(
    "BLOCK(heartbeat-dispatch-guard): heartbeat is active but no skill "
    "has been dispatched yet.\n"
    f"  target: {file_path}\n"
    f"  state: {state_source}\n"
    "  fix: run `edge-dispatch dispatch --skill <skill>` and then "
    "`edge-skill-step <skill> start` before writing artifacts.\n"
    "  See /ed-heartbeat Step 2 and issue #212.\n"
)
sys.exit(2)
PY
