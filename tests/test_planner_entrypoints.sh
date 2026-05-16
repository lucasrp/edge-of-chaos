#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== planner entrypoint contract ==="
echo ""

echo "--- Test 1: direct planner slash re-enters through edge-runner lifecycle ---"
if python3 - <<'PY' "$EDGE_DIR/skills/planner/SKILL.md"
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "Direct Slash Re-entry",
    'if [ -z "${EDGE_CYCLE_ID:-}" ]; then',
    "~/.local/bin/edge-runner skill \\",
    "--skill /ed-planner",
    "--dispatch-trigger user",
    "--dispatch-policy operator",
    "--dispatch-routing-mode explicit",
    "--dispatch-preflight-profile operator_default",
    "--dispatch-postflight-profile standard",
    "--dispatch-force",
    "--dangerously-skip-permissions",
    '--arg prompt="<operator slash-command arguments>"',
    "Replace `<operator slash-command arguments>` with the exact text",
    "Do not answer inline from the direct slash process",
    "If `EDGE_CYCLE_ID` is already set, continue normally",
]
for needle in required:
    assert needle in text, needle
for forbidden in [
    "edge-dispatch open",
    "edge-close --status completed",
    "consolidate-state",
]:
    assert forbidden not in text, forbidden
PY
then
    pass "planner skill delegates direct slash invocation to edge-runner"
else
    fail "planner skill delegates direct slash invocation to edge-runner"
fi

echo ""
echo "=== Results ==="
echo "PASS: $PASS  FAIL: $FAIL"
if [[ "$FAIL" -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
