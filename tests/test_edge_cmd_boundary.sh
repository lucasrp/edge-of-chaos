#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-cmd-boundary-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/blog/entries" "$TMP_STATE/reports" "$TMP_STATE/state/events" "$TMP_STATE/state" "$TMP_HOME"

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="cmd-boundary-test"

TOOL="$EDGE_DIR/tools/edge-cmd"
WRITE_GUARD="$EDGE_DIR/hooks/write-guard.sh"
HEARTBEAT_GUARD="$EDGE_DIR/bin/heartbeat-dispatch-guard.sh"
ENTRY_PATH="$TMP_STATE/blog/entries/protected.md"
UNPROTECTED_PATH="$TMP_BASE/free.md"

echo "=== edge-cmd boundary Smoke Test ==="
echo "Temp state: $TMP_STATE"
echo ""

echo "--- Test 1: protected writes are rejected outside command-owned context ---"
set +e
"$TOOL" validate-write --tool Write --path "$ENTRY_PATH" --source test >/tmp/edge-cmd-reject.out 2>/tmp/edge-cmd-reject.err
STATUS=$?
set -e
if [[ "$STATUS" -eq 2 ]] && grep -q "protected_write_requires_command_boundary" "$TMP_STATE/state/events/log.jsonl"; then
    pass "edge-cmd rejects protected writes and emits a canonical rejection"
else
    cat /tmp/edge-cmd-reject.out /tmp/edge-cmd-reject.err
    fail "edge-cmd rejects protected writes and emits a canonical rejection"
fi

echo "--- Test 2: consolidate-state context authorizes protected writes ---"
EDGE_CONSOLIDATE_ACTIVE=1 "$TOOL" validate-write --tool Write --path "$ENTRY_PATH" --source test >/tmp/edge-cmd-authorize.out
if grep -q "ArtifactWriteAuthorized" "$TMP_STATE/state/events/log.jsonl"; then
    pass "edge-cmd authorizes consolidate-state protected writes"
else
    cat /tmp/edge-cmd-authorize.out
    fail "edge-cmd authorizes consolidate-state protected writes"
fi

echo "--- Test 3: unprotected writes pass without command ceremony ---"
"$TOOL" validate-write --tool Write --path "$UNPROTECTED_PATH" --source test --json >/tmp/edge-cmd-free.out
if grep -q "unprotected_path" /tmp/edge-cmd-free.out; then
    pass "edge-cmd allows unprotected writes"
else
    cat /tmp/edge-cmd-free.out
    fail "edge-cmd allows unprotected writes"
fi

echo "--- Test 4: heartbeat dispatch invariant still blocks even during consolidate-state ---"
NOW_ISO="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
)"
cat >"$TMP_STATE/state/current-dispatch.json" <<JSON
{
  "cycle_id": "cycle-cmd-heartbeat",
  "request": {"trigger": "heartbeat", "skill": null},
  "state": {
    "active": true,
    "opened_at": "$NOW_ISO",
    "skill_dispatched": false
  }
}
JSON
set +e
EDGE_CONSOLIDATE_ACTIVE=1 "$TOOL" validate-write \
  --tool Write \
  --path "$ENTRY_PATH" \
  --source test \
  --require-dispatched-heartbeat >/tmp/edge-cmd-heartbeat.out 2>/tmp/edge-cmd-heartbeat.err
STATUS=$?
set -e
if [[ "$STATUS" -eq 2 ]] && grep -q "heartbeat_dispatch_required" "$TMP_STATE/state/events/log.jsonl"; then
    pass "edge-cmd keeps heartbeat dispatch invariant at the command boundary"
else
    cat /tmp/edge-cmd-heartbeat.out /tmp/edge-cmd-heartbeat.err
    fail "edge-cmd keeps heartbeat dispatch invariant at the command boundary"
fi

echo "--- Test 5: write-guard delegates to edge-cmd ---"
set +e
printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}\n' "$ENTRY_PATH" | "$WRITE_GUARD" >/tmp/write-guard.out 2>/tmp/write-guard.err
STATUS=$?
set -e
if [[ "$STATUS" -eq 2 ]] && grep -q "edge-cmd" /tmp/write-guard.err; then
    pass "write-guard delegates protected write rejection to edge-cmd"
else
    cat /tmp/write-guard.out /tmp/write-guard.err
    fail "write-guard delegates protected write rejection to edge-cmd"
fi

echo "--- Test 6: heartbeat-dispatch-guard delegates to edge-cmd ---"
set +e
printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}\n' "$ENTRY_PATH" | env EDGE_CONSOLIDATE_ACTIVE=1 "$HEARTBEAT_GUARD" >/tmp/heartbeat-guard.out 2>/tmp/heartbeat-guard.err
STATUS=$?
set -e
if [[ "$STATUS" -eq 2 ]] && grep -q "heartbeat is active" /tmp/heartbeat-guard.err; then
    pass "heartbeat-dispatch-guard delegates heartbeat rejection to edge-cmd"
else
    cat /tmp/heartbeat-guard.out /tmp/heartbeat-guard.err
    fail "heartbeat-dispatch-guard delegates heartbeat rejection to edge-cmd"
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
