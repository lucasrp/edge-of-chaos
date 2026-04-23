#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-publish-scope-XXXXXX)"
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

mkdir -p "$TMP_REPO" "$TMP_STATE/state/events"

export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="publish-scope-test"

SCOPE_TOOL="$EDGE_DIR/tools/edge-publish-scope"
EVENTS_FILE="$TMP_STATE/state/events/log.jsonl"

git -C "$TMP_REPO" init -q
git -C "$TMP_REPO" config user.name "Codex"
git -C "$TMP_REPO" config user.email "codex@example.com"

cat >"$TMP_REPO/allowed.txt" <<'EOF'
allowed old
EOF
cat >"$TMP_REPO/other.txt" <<'EOF'
other old
EOF
git -C "$TMP_REPO" add allowed.txt other.txt
git -C "$TMP_REPO" commit -q -m "init"

echo "allowed new" >"$TMP_REPO/allowed.txt"
echo "other new" >"$TMP_REPO/other.txt"

echo "=== edge-publish-scope Smoke Test ==="
echo "Temp repo: $TMP_REPO"
echo ""

echo "--- Test 1: stages only allowlisted file when index is clean ---"
OUTPUT=$("$SCOPE_TOOL" stage --slug demo --allow "$TMP_REPO/allowed.txt" --json)
if python3 - <<'PY' "$OUTPUT" "$TMP_REPO"
import json
import subprocess
import sys
payload = json.loads(sys.argv[1])
repo = sys.argv[2]
staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=repo, text=True).splitlines()
assert payload["illegal_files"] == []
assert staged == ["allowed.txt"]
PY
then
    pass "scope stages only allowlisted file"
else
    fail "scope stages only allowlisted file"
fi

git -C "$TMP_REPO" reset -q HEAD -- .
git -C "$TMP_REPO" add other.txt

echo "--- Test 2: detects staged versioned file outside allowlist ---"
set +e
OUTPUT=$("$SCOPE_TOOL" stage --slug demo --allow "$TMP_REPO/allowed.txt" --json 2>/dev/null)
STATUS=$?
set -e
if python3 - <<'PY' "$STATUS" "$OUTPUT" "$EVENTS_FILE"
import json
import sys
status = int(sys.argv[1])
payload = json.loads(sys.argv[2])
events_path = sys.argv[3]
events = [json.loads(line) for line in open(events_path, encoding="utf-8") if line.strip()]
assert status == 2
assert payload["illegal_files"] == ["other.txt"]
event = [item for item in events if item["type"] == "PublishCommitScopeViolation"][-1]
assert event["payload"]["illegal_files"] == ["other.txt"]
PY
then
    pass "scope detects staged file outside allowlist and emits event"
else
    fail "scope detects staged file outside allowlist and emits event"
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
