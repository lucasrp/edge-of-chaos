#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-close-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$TMP_EDGE/state/events" "$TMP_EDGE/logs" "$TMP_EDGE/state"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"

DISPATCH_TOOL="$EDGE_DIR/tools/edge-dispatch"
CLOSE_TOOL="$EDGE_DIR/tools/edge-close"
STEP_TOOL="$EDGE_DIR/tools/edge-skill-step"

echo "=== edge-close Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: completed close is rejected without skill completion evidence ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-missing >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
set +e
"$CLOSE_TOOL" --status completed >/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
status = int(sys.argv[2])

assert status == 1
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "missing_skill_run_completed"
assert dispatch["state"]["postflight_status"] == "failed"
PY
then
    pass "edge-close downgrades incomplete cycles to failed"
else
    fail "edge-close downgrades incomplete cycles to failed"
fi

echo "--- Test 2: completed close succeeds with skill end evidence and postflight ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-complete --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
EDGE_CYCLE_ID=cycle-close-complete "$STEP_TOOL" discovery start >/dev/null
EDGE_CYCLE_ID=cycle-close-complete "$STEP_TOOL" discovery end >/dev/null
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/logs/post-skill.log"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
postflight = open(sys.argv[2], encoding="utf-8").read()
steps = dispatch["state"].get("postflight_steps", [])
delta = dispatch["state"].get("postflight_delta", {})
step_names = {step.get("step") for step in steps}

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["postflight_status"] == "completed"
assert "validate_recent" in postflight
assert {"validate_recent", "claims_digest", "primitives_status", "workflow_status", "briefing_digest"} <= step_names
assert "claims_open_delta" in delta
PY
then
    pass "edge-close completes only after skill end evidence and enriched postflight"
else
    fail "edge-close completes only after skill end evidence and enriched postflight"
fi

echo "--- Test 3: autofixable validate_recent becomes warning, not failed close ---"
TODAY="$(date +%Y-%m-%d)"
cat >"$TMP_EDGE/blog/entries/2026-04-22-warning.md" <<EOF
---
date: $TODAY
title: Warning Example
report: reports/2026-04-22-warning.html
tags: [note]
---

warning body
EOF
cat >"$TMP_EDGE/reports/2026-04-22-warning.html" <<'EOF'
<html><body>warning report</body></html>
EOF
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-warning --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
EDGE_CYCLE_ID=cycle-close-warning "$STEP_TOOL" discovery start >/dev/null
EDGE_CYCLE_ID=cycle-close-warning "$STEP_TOOL" discovery end >/dev/null
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/blog/entries/2026-04-22-warning.md"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
entry = open(sys.argv[2], encoding="utf-8").read()

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["close_reason"] == "validate_recent_warning"
assert dispatch["state"]["postflight_status"] == "warning"
assert "report: 2026-04-22-warning.html" in entry
PY
then
    pass "autofixable validate_recent closes as completed with warning"
else
    fail "autofixable validate_recent closes as completed with warning"
fi

echo "--- Test 4: mixed aware/naive completion timestamps still close successfully ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-naive-mixed --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch_path, events_path = sys.argv[1], sys.argv[2]
dispatch = json.load(open(dispatch_path, encoding="utf-8"))
dispatch["cycle_id"] = "cycle-close-naive-mixed"
dispatch["request"]["skill"] = "discovery"
dispatch["state"]["opened_at"] = "2026-04-22T00:00:00+00:00"
dispatch["state"]["dispatched_at"] = "2026-04-22T00:00:01+00:00"
json.dump(dispatch, open(dispatch_path, "w", encoding="utf-8"), indent=2)
with open(dispatch_path, "a", encoding="utf-8") as fh:
    fh.write("\n")

event = {
    "ts": "2026-04-22T00:00:02",
    "type": "SkillRunCompleted",
    "cycle_id": "cycle-close-naive-mixed",
    "payload": {"skill": "discovery", "registry_skill": "discovery"},
}
with open(events_path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
PY
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
PY
then
    pass "mixed aware/naive timestamps do not break edge-close"
else
    fail "mixed aware/naive timestamps do not break edge-close"
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
