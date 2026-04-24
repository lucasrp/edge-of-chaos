#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$EDGE_DIR/hooks/shell-follow-guard.sh"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

run_hook() {
  local payload="$1"
  set +e
  OUTPUT=$(bash "$HOOK" <<<"$payload" 2>&1)
  STATUS=$?
  set -e
}

payload() {
  python3 - <<'PY' "$1" "$2"
import json
import sys
print(json.dumps({"tool_name": sys.argv[1], "tool_input": {"command": sys.argv[2]}}))
PY
}

echo "=== shell follow guard Smoke Test ==="
echo ""

echo "--- Test 1: blocks tail -f ---"
run_hook "$(payload Bash 'tail -f /tmp/output.log')"
if [[ "$STATUS" -eq 2 ]] && grep -q "BLOCKED" <<<"$OUTPUT"; then
  pass "hook blocks tail -f"
else
  echo "$OUTPUT"
  fail "hook blocks tail -f"
fi

echo "--- Test 2: blocks tail -F in a pipeline ---"
run_hook "$(payload Bash 'tail -F /tmp/output.log 2>&1 | head -200')"
if [[ "$STATUS" -eq 2 ]] && grep -q "tail -f/--follow" <<<"$OUTPUT"; then
  pass "hook blocks tail -F pipeline"
else
  echo "$OUTPUT"
  fail "hook blocks tail -F pipeline"
fi

echo "--- Test 3: blocks tail --follow ---"
run_hook "$(payload Bash 'tail --follow=name /tmp/output.log')"
if [[ "$STATUS" -eq 2 ]]; then
  pass "hook blocks tail --follow"
else
  echo "$OUTPUT"
  fail "hook blocks tail --follow"
fi

echo "--- Test 4: blocks nested bash -lc tail -f ---"
run_hook "$(payload Bash "bash -lc 'tail -f /tmp/output.log | head -200'")"
if [[ "$STATUS" -eq 2 ]]; then
  pass "hook blocks nested bash -lc tail -f"
else
  echo "$OUTPUT"
  fail "hook blocks nested bash -lc tail -f"
fi

echo "--- Test 5: allows finite tail reads ---"
run_hook "$(payload Bash 'tail -n 200 /tmp/output.log')"
if [[ "$STATUS" -eq 0 ]]; then
  pass "hook allows tail -n"
else
  echo "$OUTPUT"
  fail "hook allows tail -n"
fi

echo "--- Test 6: allows quoted text mentioning tail -f ---"
run_hook "$(payload Bash 'echo \"tail -f /tmp/output.log\"')"
if [[ "$STATUS" -eq 0 ]]; then
  pass "hook allows quoted tail -f text"
else
  echo "$OUTPUT"
  fail "hook allows quoted tail -f text"
fi

echo "--- Test 7: ignores non-Bash tools ---"
run_hook '{"tool_name":"WebSearch","tool_input":{"query":"tail -f bug"}}'
if [[ "$STATUS" -eq 0 ]]; then
  pass "hook ignores non-Bash tools"
else
  echo "$OUTPUT"
  fail "hook ignores non-Bash tools"
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
