#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-consolidate-adversarial-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_BIN="$TMP_BASE/bin"
TMP_ENTRY="$TMP_STATE/blog/entries/test-entry.md"
TMP_REPORT="$TMP_STATE/reports/test-spec.yaml"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE"/{blog/entries,reports,meta-reports,logs,state/events,state/runtime,health,db,threads,topics,notes,builds,search,config,search} "$TMP_BIN"

cat >"$TMP_ENTRY" <<'EOF'
---
title: "Test entry"
date: "2026-04-23"
tags: [test]
claims:
  - "Verified test claim"
threads: [test-thread]
---

Test body.
EOF

cat >"$TMP_REPORT" <<'EOF'
title: "Test spec"
subtitle: "Adversarial phase smoke"
date: "23/04/2026"
sections:
  - title: "1. Test"
    content: "Test content"
EOF

cat >"$TMP_BIN/review-gate" <<'EOF'
#!/usr/bin/env python3
import json
print(json.dumps({
  "final_review": {
    "overall": 4.2,
    "critical_issues": [],
    "suggestions": [],
    "_meta": {"cost_estimate": "$0.0010"}
  },
  "coauthor": {
    "suggestions": [],
    "_meta": {"cost_estimate": "$0.0010"}
  },
  "rounds": []
}))
EOF
chmod +x "$TMP_BIN/review-gate"

cat >"$TMP_BIN/edge-consult" <<'EOF'
#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
gate = None
for i, arg in enumerate(args):
    if arg == "--gate" and i + 1 < len(args):
        gate = pathlib.Path(args[i + 1])
        break
if gate is None:
    print("missing gate path", file=sys.stderr)
    raise SystemExit(2)
gate.with_suffix(".review.json").write_text(json.dumps({
    "timestamp": "2026-04-23T00:00:00+00:00",
    "spec": str(gate),
    "mode": "adversarial",
    "response": "stub review",
    "resolved": False
}, indent=2), encoding="utf-8")
print("stub adversarial review")
EOF
chmod +x "$TMP_BIN/edge-consult"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="adversarial-phase-test"
export PATH="$TMP_BIN:$PATH"

CONSOLIDATE="$EDGE_DIR/blog/consolidate-state.sh"
EVENTS_FILE="$TMP_STATE/state/events/log.jsonl"
EVENTS_MIRROR_FILE="$TMP_STATE/logs/events.jsonl"

echo "=== consolidate-state adversarial phase test ==="
echo "Temp state: $TMP_STATE"
echo ""

echo "--- Test 1: missing review.json triggers phase-0.3 generation ---"
if "$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT" --review-only >/tmp/test-consolidate-adversarial.log 2>&1; then
    if python3 - <<'PY' "$TMP_REPORT" "$EVENTS_MIRROR_FILE"
import json, pathlib, sys
report = pathlib.Path(sys.argv[1])
events_path = pathlib.Path(sys.argv[2])
review = report.with_suffix(".review.json")
feynman = pathlib.Path(str(report).replace(".yaml", ".feynman-review.json"))
resolved = report.with_suffix(".resolved")
assert review.exists(), "review.json missing"
assert feynman.exists(), "feynman-review.json missing"
assert resolved.exists(), "resolved marker missing"
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
steps = [e for e in events if e.get("type") == "run_step"]
phase03 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.3"]
phase045 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.45"]
phase05 = [(e["phase"], e["status"]) for e in steps if e["phase"] == "phase-0.5"]
assert ("phase-0.3", "started", "adversarial_review") in phase03
assert ("phase-0.3", "completed", "adversarial_review_generated") in phase03
assert ("phase-0.45", "started", "feynman_judge") in phase045
assert ("phase-0.45", "completed", "feynman_judge") in phase045
assert ("phase-0.5", "started") in phase05
assert ("phase-0.5", "completed") in phase05
PY
    then
        pass "phase-0.3 generates review and review-only completes"
    else
        fail "phase-0.3 generates review and review-only completes"
    fi
else
    cat /tmp/test-consolidate-adversarial.log
    fail "review-only publish with generated review succeeds"
fi

echo "--- Test 2: unresolved existing review.json still blocks ---"
rm -f "${TMP_REPORT%.yaml}.resolved"
set +e
"$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT" --review-only >/tmp/test-consolidate-adversarial.log 2>&1
STATUS=$?
set -e
if python3 - <<'PY' "$STATUS" "$EVENTS_MIRROR_FILE"
import json, sys, pathlib
status = int(sys.argv[1])
events_path = pathlib.Path(sys.argv[2])
assert status == 3
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
steps = [e for e in events if e.get("type") == "run_step"]
phase03 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.3"]
assert ("phase-0.3", "failed", "adversarial_review") in phase03
PY
then
    pass "unresolved existing review still blocks phase-0.3"
else
    cat /tmp/test-consolidate-adversarial.log
    fail "unresolved existing review still blocks phase-0.3"
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
