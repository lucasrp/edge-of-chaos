#!/usr/bin/env bash
# shell-follow-guard.sh — Claude Code PreToolUse hook for Bash.
#
# Blocks unbounded shell follow commands that can keep autonomous beats open
# after useful work has finished. The observed failure mode was:
#
#   tail -f /tmp/claude-.../tasks/<id>.output 2>&1 | head -200
#
# If the followed file stops before head receives enough lines, tail keeps the
# pipe open forever. Use finite reads (`tail -n`, `sed -n`) for diagnostics
# inside autonomous runs.

set -euo pipefail

if [[ "${EDGE_ALLOW_FOLLOW_COMMANDS:-0}" == "1" ]]; then
    exit 0
fi

INPUT="$(cat)"

python3 - <<'PY' "$INPUT"
import json
import os
import shlex
import sys

raw_payload = sys.argv[1]
try:
    payload = json.loads(raw_payload)
except Exception:
    raise SystemExit(0)

tool_name = str(payload.get("tool_name") or "").strip()
if tool_name != "Bash":
    raise SystemExit(0)

tool_input = payload.get("tool_input") or {}
command = str(tool_input.get("command") or tool_input.get("cmd") or "").strip()
if not command:
    raise SystemExit(0)


def _is_tail_token(token: str) -> bool:
    return os.path.basename(token) in {"tail", "gtail"}


def _tail_has_follow_flag(tokens: list[str], start: int) -> bool:
    idx = start + 1
    while idx < len(tokens):
        token = tokens[idx]
        if token in {"|", ";", "&&", "||", "&"}:
            return False
        if token == "--":
            return False
        if token in {"--follow", "-f", "-F"}:
            return True
        if token.startswith("--follow="):
            return True
        if token.startswith("-") and not token.startswith("--") and any(ch in token[1:] for ch in ("f", "F")):
            return True
        if not token.startswith("-"):
            return False
        idx += 1
    return False


def _contains_blocked_follow(command_text: str, depth: int = 0) -> bool:
    if depth > 2:
        return False
    try:
        tokens = shlex.split(command_text, posix=True)
    except ValueError:
        # If the command cannot be parsed safely, do not block on a guess.
        return False

    for idx, token in enumerate(tokens):
        if _is_tail_token(token) and _tail_has_follow_flag(tokens, idx):
            return True
        if os.path.basename(token) in {"bash", "sh", "zsh"}:
            for offset, candidate in enumerate(tokens[idx + 1 :], start=idx + 1):
                if candidate in {"-c", "-lc", "-ic"} and offset + 1 < len(tokens):
                    if _contains_blocked_follow(tokens[offset + 1], depth + 1):
                        return True
    return False


if not _contains_blocked_follow(command):
    raise SystemExit(0)

sys.stderr.write(
    "[shell-follow-guard] BLOCKED: unbounded follow command in Bash tool.\n"
    f"  command: {command[:240]}\n"
    "  reason: tail -f/--follow can keep autonomous heartbeats open forever.\n"
    "  use: finite reads such as `tail -n 200 <file>` or `sed -n '1,200p' <file>`.\n"
    "  escape hatch for manual debugging only: EDGE_ALLOW_FOLLOW_COMMANDS=1.\n"
)
raise SystemExit(2)
PY
