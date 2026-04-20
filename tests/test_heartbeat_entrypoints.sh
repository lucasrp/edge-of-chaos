#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== heartbeat entrypoint contract ==="
echo ""

echo "--- Test 1: manual docs no longer point to direct claude -p heartbeat ---"
if python3 - <<'PY' "$EDGE_DIR"
from pathlib import Path
import sys

root = Path(sys.argv[1])
targets = [
    root / "README.md",
    root / "docs" / "SETUP_GUIDE.md",
    root / "tools" / "edge-apply",
]
for path in targets:
    text = path.read_text(encoding="utf-8")
    assert "claude -p '/PREFIX-heartbeat'" not in text
    assert 'claude -p "/PREFIX-heartbeat"' not in text
    assert "claude -p '/{prefix}-heartbeat'" not in text
PY
then
    pass "manual docs avoid the direct slash-command bootstrap path"
else
    fail "manual docs avoid the direct slash-command bootstrap path"
fi

echo "--- Test 2: heartbeat skill carries fallback lifecycle + no-HITL contract ---"
if python3 - <<'PY' "$EDGE_DIR/skills/heartbeat/SKILL.md"
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "Direct slash-command invocation is still a full heartbeat",
    "Do **not** ask the operator whether to batch-run `first_steps`",
    "Never prompt the operator mid-beat.",
    "edge-dispatch open \\",
    '--trigger heartbeat',
    'if [ -z "${EDGE_CYCLE_ID:-}" ]; then',
    'edge-close --status completed',
]
for needle in required:
    assert needle in text, needle
PY
then
    pass "heartbeat skill documents manual fallback lifecycle and bans mid-beat confirmation"
else
    fail "heartbeat skill documents manual fallback lifecycle and bans mid-beat confirmation"
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
