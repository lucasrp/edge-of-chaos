#!/usr/bin/env bash
# write-guard.sh — Claude Code PreToolUse hook (enforcement #218, Peça 2)
#
# Blocks Write/Edit/NotebookEdit on protected artifact paths unless the
# consolidate-state pipeline is the caller (EDGE_CONSOLIDATE_ACTIVE=1).
#
# Protected paths (relative to $HOME/edge or absolute equivalents):
#   - blog/entries/          blog posts (phenotype output, only via pipeline)
#   - state/                 signals, claims, threads
#   - reports/               generated HTML reports
#   - meta-reports/          cognitive mirrors
#   - threads/               thread state
#   - health/                health markers
#   - logs/                  pipeline logs
#
# Input: Claude Code sends a JSON event on stdin describing the pending tool call.
# Output: exit 0 = allow; exit 2 = deny with message to stderr.
#
# If EDGE_CONSOLIDATE_ACTIVE=1, all writes pass through (pipeline is active).
# Memory writes (~/.claude/projects/*/memory/) are always allowed.

set -uo pipefail

if [[ "${EDGE_CONSOLIDATE_ACTIVE:-0}" == "1" ]]; then
    exit 0
fi

INPUT="$(cat)"
TOOL_NAME=$(echo "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_name",""))' 2>/dev/null || echo "")

case "$TOOL_NAME" in
    Write|Edit|NotebookEdit) ;;
    *) exit 0 ;;
esac

PATH_ARG=$(echo "$INPUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin).get("tool_input", {})
    print(d.get("file_path") or d.get("notebook_path") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

[[ -z "$PATH_ARG" ]] && exit 0

EDGE_ROOT="${EDGE_DIR:-$HOME/edge}"
EDGE_CMD="${EDGE_REPO_DIR:-$EDGE_ROOT}/tools/edge-cmd"

# Canonicalize
ABS_PATH="$PATH_ARG"
[[ "$ABS_PATH" != /* ]] && ABS_PATH="$PWD/$ABS_PATH"

# Memory always allowed
case "$ABS_PATH" in
    "$HOME/.claude/projects/"*/memory/*) exit 0 ;;
esac

if [[ -x "$EDGE_CMD" ]]; then
    "$EDGE_CMD" validate-write --tool "$TOOL_NAME" --path "$PATH_ARG" --source write-guard
    exit $?
fi

for sub in blog/entries state reports meta-reports threads health logs; do
    prefix="$EDGE_ROOT/$sub"
    case "$ABS_PATH" in
        "$prefix"/*|"$prefix")
            cat >&2 <<MSG
[write-guard #218] BLOCKED: $TOOL_NAME on $ABS_PATH
Artifact paths are only writable through the consolidate-state pipeline.
Run: consolidate-state <entry.md> [report.yaml]
(Pipeline sets EDGE_CONSOLIDATE_ACTIVE=1 which unblocks writes.)
MSG
            exit 2
            ;;
    esac
done

exit 0
