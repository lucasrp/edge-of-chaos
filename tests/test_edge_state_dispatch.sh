#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-state-dispatch-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_REPO/tools" "$TMP_REPO/config" "$TMP_REPO/memory" "$TMP_STATE/state" "$TMP_STATE/logs"
cp "$EDGE_DIR/tools/edge-state-dispatch" "$TMP_REPO/tools/edge-state-dispatch"
cp -R "$EDGE_DIR/tools/_shared" "$TMP_REPO/tools/_shared"
cp "$EDGE_DIR/config/paths.py" "$TMP_REPO/config/paths.py"
cp "$EDGE_DIR/config/branding.py" "$TMP_REPO/config/branding.py"
chmod +x "$TMP_REPO/tools/edge-state-dispatch"

cat >"$TMP_REPO/config/CLAUDE.md" <<'MD'
# Runtime instructions
MD
cat >"$TMP_REPO/memory/MEMORY.md" <<'MD'
# Memory
MD

export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"
export MEMORY_PROJECT_DIR=""

cat >"$TMP_STATE/state/dispatch-queue.json" <<'JSON'
[
  {
    "skill": "planner",
    "source": "state-anchor-monitor",
    "entry_id": "state-anchor-monitor:stale",
    "reason": "State anchors changed | lint: 0 errors, 2 warnings",
    "created_at": "2026-05-03T00:00:00+00:00"
  }
]
JSON
cat >"$TMP_REPO/tools/edge-state-lint" <<'SH'
#!/usr/bin/env bash
cat <<'JSON'
{"timestamp":"2026-05-03T00:00:00","total":2,"by_severity":{"warn":2,"error":0},"findings":[]}
JSON
SH
chmod +x "$TMP_REPO/tools/edge-state-lint"

echo "=== edge-state-dispatch Test ==="
echo ""

echo "--- Test 0: edge-state-dispatch is directly executable ---"
if [[ -x "$EDGE_DIR/tools/edge-state-dispatch" ]]; then
    pass "edge-state-dispatch is directly executable"
else
    fail "edge-state-dispatch is directly executable"
fi

echo "--- Test 1: stale state-anchor queue clears when lint has no errors ---"
if "$TMP_REPO/tools/edge-state-dispatch" >/tmp/edge-state-dispatch.out && python3 - <<'PY' "$TMP_STATE/state/dispatch-queue.json" /tmp/edge-state-dispatch.out
import json
import sys
from pathlib import Path

queue = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2]).read_text(encoding="utf-8")
assert queue == []
assert "STATE_QUEUE planner cleared" in out
PY
then
    pass "stale state-anchor queue clears when lint has no errors"
else
    fail "stale state-anchor queue clears when lint has no errors"
fi

cat >"$TMP_STATE/state/dispatch-queue.json" <<'JSON'
[
  {
    "skill": "planner",
    "source": "state-anchor-monitor",
    "entry_id": "state-anchor-monitor:still-bad",
    "reason": "State anchors changed | lint: 1 errors, 0 warnings",
    "created_at": "2026-05-03T00:00:00+00:00"
  }
]
JSON
cat >"$TMP_REPO/tools/edge-state-lint" <<'SH'
#!/usr/bin/env bash
cat <<'JSON'
{"timestamp":"2026-05-03T00:00:00","total":1,"by_severity":{"warn":0,"error":1},"findings":[]}
JSON
SH
chmod +x "$TMP_REPO/tools/edge-state-lint"

echo "--- Test 2: state-anchor queue remains when lint errors remain ---"
if "$TMP_REPO/tools/edge-state-dispatch" >/tmp/edge-state-dispatch.out && python3 - <<'PY' "$TMP_STATE/state/dispatch-queue.json" /tmp/edge-state-dispatch.out
import json
import sys
from pathlib import Path

queue = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2]).read_text(encoding="utf-8")
assert len(queue) == 1
assert queue[0]["entry_id"] == "state-anchor-monitor:still-bad"
assert "STATE_QUEUE planner cleared" not in out
PY
then
    pass "state-anchor queue remains when lint errors remain"
else
    fail "state-anchor queue remains when lint errors remain"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
