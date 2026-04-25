#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== heartbeat entrypoint contract ==="
echo ""

echo "--- Test 0: heartbeat.sh.tpl parses as bash with stale-lock recovery wired (issue #374) ---"
TMP_HB=$(mktemp /tmp/heartbeat-rendered-XXXXXX.sh)
trap 'rm -f "$TMP_HB"' EXIT
sed \
    -e 's|{{ WORK_DIR }}|/tmp/edge-test|g' \
    -e 's|{{ CODENAME }}|test|g' \
    -e 's|{{ SKILL_PREFIX }}|test|g' \
    -e 's|{{ HEARTBEAT_INTERVAL }}|2h|g' \
    "$EDGE_DIR/config/heartbeat.sh.tpl" > "$TMP_HB"
if bash -n "$TMP_HB" 2>&1; then
    pass "rendered heartbeat.sh parses without syntax errors"
else
    fail "rendered heartbeat.sh has syntax errors"
fi
if grep -q "try_recover_stale_lock" "$TMP_HB" && grep -q "EDGE_HEARTBEAT_STALE_LOCK_SEC" "$TMP_HB"; then
    pass "rendered heartbeat.sh wires stale-lock recovery"
else
    fail "rendered heartbeat.sh missing stale-lock recovery"
fi

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

echo "--- Test 2: direct heartbeat slash re-enters through wrapper instead of manual lifecycle ---"
if python3 - <<'PY' "$EDGE_DIR/skills/heartbeat/SKILL.md"
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "Direct `/ed-heartbeat` invocation is still a full beat.",
    "Direct Slash Re-entry",
    "The heartbeat is a router, not a worker.",
    "It must dispatch exactly one internal skill.",
    "Router-only rule:",
    "does not draft the final artifact",
    "After `edge-dispatch dispatch --skill <skill>` succeeds, stop doing inline work",
    'if [ -z "${EDGE_CYCLE_ID:-}" ]; then',
    'EDGE_HEARTBEAT_FOREGROUND=1 ~/.local/bin/heartbeat.sh',
    "Do not call `edge-dispatch open`",
    "invocation re-enters via `~/.local/bin/heartbeat.sh`",
]
for needle in required:
    assert needle in text, needle
for forbidden in [
    "edge-dispatch open \\",
    "--trigger heartbeat",
    "edge-close --status completed",
]:
    assert forbidden not in text, forbidden
PY
then
    pass "heartbeat skill delegates direct slash invocation to the wrapper"
else
    fail "heartbeat skill delegates direct slash invocation to the wrapper"
fi

echo "--- Test 3: heartbeat wrapper streams manual runs while preserving systemd logging ---"
if python3 - <<'PY' "$EDGE_DIR/config/heartbeat.sh.tpl"
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "run_heartbeat()",
    'if [[ -t 1 || "${EDGE_HEARTBEAT_FOREGROUND:-0}" == "1" ]]; then',
    'run_heartbeat 2>&1 | tee -a "$LOGFILE"',
    "HEARTBEAT_STATUS=${PIPESTATUS[0]}",
    'run_heartbeat >> "$LOGFILE" 2>&1',
    'exit "$HEARTBEAT_STATUS"',
]
for needle in required:
    assert needle in text, needle
PY
then
    pass "heartbeat wrapper shows manual runs and keeps systemd log behavior"
else
    fail "heartbeat wrapper shows manual runs and keeps systemd log behavior"
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
