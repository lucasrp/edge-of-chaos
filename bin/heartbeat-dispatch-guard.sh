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
# Sentinel file: $EDGE_ROOT/state/current-beat.json
#   {
#     "active": bool,              # set true at Step 2 entry
#     "started_at": ISO8601,       # auto-expires after 1h
#     "skill_dispatched": bool,    # flipped to true immediately before dispatch
#     "skill": string|null
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

STATE_FILE="${EDGE_ROOT:-$HOME/edge}/state/current-beat.json"

# Read PreToolUse payload from stdin
TOOL_INPUT=$(cat)

# Fast path: if no sentinel file, not in heartbeat → allow immediately
[ -f "$STATE_FILE" ] || exit 0

python3 - <<'PY' "$STATE_FILE" "$TOOL_INPUT"
import json
import sys
import datetime
import pathlib

state_path = pathlib.Path(sys.argv[1])
try:
    payload = json.loads(sys.argv[2])
except Exception:
    sys.exit(0)  # malformed payload, do not block

tool_input = payload.get("tool_input", {}) or {}
file_path = tool_input.get("file_path", "") or ""

# Only guard artifact paths
GUARDED = ("/edge/blog/entries/", "/edge/reports/")
if not any(seg in file_path for seg in GUARDED):
    sys.exit(0)

try:
    state = json.loads(state_path.read_text())
except Exception:
    sys.exit(0)  # unreadable sentinel, fail open

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
    "  fix: run `edge-skill-step <skill> start` and flip "
    "state/current-beat.json:skill_dispatched to true before writing "
    "artifacts.\n"
    "  See /ed-heartbeat Step 2 and issue #212.\n"
)
sys.exit(2)
PY
