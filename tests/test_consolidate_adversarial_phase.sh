#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-consolidate-adversarial-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_BIN="$TMP_BASE/bin"
TMP_ENTRY="$TMP_STATE/blog/entries/test-entry.md"
TMP_REPORT="$TMP_STATE/reports/test-spec.yaml"
TMP_REPORT_HTML="$TMP_STATE/reports/test-report.html"
TEST_LOG="$TMP_BASE/test-consolidate-adversarial.log"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE"/{blog/entries,reports,logs,state/events,state/runtime,state/audits,health,db,threads,topics,notes,builds,search,config,search} "$TMP_BIN"

cat >"$TMP_ENTRY" <<'EOF'
---
title: "Test entry"
date: "2026-04-23"
tags: [test]
open_gaps: []
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

cat >"$TMP_REPORT_HTML" <<'EOF'
<!doctype html>
<html lang="pt-BR">
<head><title>Test HTML report</title></head>
<body>
<h1>Test HTML report</h1>
<p>Em termos simples, este relatorio testa o gate de HTML pre-renderizado.</p>
<h2>O que Nao Sei</h2>
<p>Nao sabemos se o ambiente externo esta disponivel.</p>
</body>
</html>
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
set +e
"$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT" --review-only >"$TEST_LOG" 2>&1
STATUS=$?
set -e
if python3 - <<'PY' "$STATUS" "$TMP_REPORT" "$EVENTS_MIRROR_FILE"
import json, pathlib, sys
status = int(sys.argv[1])
report = pathlib.Path(sys.argv[2])
events_path = pathlib.Path(sys.argv[3])
review = report.with_suffix(".review.json")
feynman = pathlib.Path(str(report).replace(".yaml", ".feynman-review.json"))
resolved = report.with_suffix(".resolved")
assert status == 3
assert review.exists(), "review.json missing"
assert not feynman.exists(), "feynman-review should not run before adversarial resolution"
assert not resolved.exists(), "resolved marker should not be auto-created"
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
steps = [e for e in events if e.get("type") == "run_step"]
phase03 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.3"]
assert ("phase-0.3", "started", "adversarial_review") in phase03
assert ("phase-0.3", "failed", "adversarial_review_pending") in phase03
PY
then
    pass "phase-0.3 generates review and blocks until resolved"
else
    cat "$TEST_LOG"
    fail "phase-0.3 generates review and blocks until resolved"
fi

touch "${TMP_REPORT%.yaml}.resolved"
if "$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT" --review-only >"$TEST_LOG" 2>&1; then
    if python3 - <<'PY' "$TMP_REPORT" "$EVENTS_MIRROR_FILE"
import json, pathlib, sys
report = pathlib.Path(sys.argv[1])
events_path = pathlib.Path(sys.argv[2])
feynman = pathlib.Path(str(report).replace(".yaml", ".feynman-review.json"))
resolved = report.with_suffix(".resolved")
assert feynman.exists(), "feynman-review.json missing"
assert resolved.exists(), "resolved marker missing"
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
steps = [e for e in events if e.get("type") == "run_step"]
phase03 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.3"]
phase045 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.45"]
phase05 = [(e["phase"], e["status"]) for e in steps if e["phase"] == "phase-0.5"]
assert ("phase-0.3", "completed", "adversarial_review") in phase03
assert ("phase-0.45", "started", "feynman_judge") in phase045
assert ("phase-0.45", "completed", "feynman_judge") in phase045
assert ("phase-0.5", "started") in phase05
assert ("phase-0.5", "completed") in phase05
PY
    then
        pass "resolved adversarial review allows review-only completion"
        if python3 "$EDGE_DIR/tools/generate_report.py" --yaml "$TMP_REPORT" --output "$TMP_STATE/reports/rendered.html" >/dev/null 2>&1 \
          && grep -q "Desafio Adversarial" "$TMP_STATE/reports/rendered.html"; then
            pass "YAML report render includes adversarial section"
        else
            fail "YAML report render includes adversarial section"
        fi
    else
        fail "resolved adversarial review allows review-only completion"
    fi
else
    cat "$TEST_LOG"
    fail "review-only publish with resolved review succeeds"
fi

echo "--- Test 2: unresolved existing review.json still blocks ---"
rm -f "${TMP_REPORT%.yaml}.resolved"
set +e
"$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT" --review-only >"$TEST_LOG" 2>&1
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
    cat "$TEST_LOG"
    fail "unresolved existing review still blocks phase-0.3"
fi

echo "--- Test 3: HTML report path also runs mandatory gates ---"
set +e
"$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT_HTML" --review-only >"$TEST_LOG" 2>&1
STATUS=$?
set -e
if python3 - <<'PY' "$STATUS" "$TMP_REPORT_HTML"
import pathlib, sys
status = int(sys.argv[1])
report = pathlib.Path(sys.argv[2])
stem = report.with_suffix("")
review = stem.with_suffix(".review.json")
resolved = stem.with_suffix(".resolved")
assert status == 3
assert review.exists(), "html review.json missing"
assert not resolved.exists(), "html resolved marker should not be auto-created"
PY
then
    pass "HTML report path generates review and blocks until resolved"
else
    cat "$TEST_LOG"
    fail "HTML report path generates review and blocks until resolved"
fi

touch "${TMP_REPORT_HTML%.html}.resolved"
if "$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT_HTML" --review-only >"$TEST_LOG" 2>&1; then
    if python3 - <<'PY' "$TMP_REPORT_HTML" "$EVENTS_MIRROR_FILE"
import json, pathlib, sys
report = pathlib.Path(sys.argv[1])
events_path = pathlib.Path(sys.argv[2])
stem = report.with_suffix("")
review = stem.with_suffix(".review.json")
feynman = stem.with_suffix(".feynman-review.json")
resolved = stem.with_suffix(".resolved")
assert review.exists(), "html review.json missing"
assert feynman.exists(), "html feynman-review.json missing"
assert resolved.exists(), "html resolved marker missing"
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
steps = [e for e in events if e.get("type") == "run_step"]
phase03 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.3"]
phase045 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.45"]
phase05 = [(e["phase"], e["status"]) for e in steps if e["phase"] == "phase-0.5"]
assert ("phase-0.3", "completed", "adversarial_review") in phase03
assert ("phase-0.45", "completed", "feynman_judge") in phase045
assert ("phase-0.5", "completed") in phase05
PY
    then
        pass "HTML report path runs adversarial, Feynman, and review gates"
    else
        cat "$TEST_LOG"
        fail "HTML report path runs adversarial, Feynman, and review gates"
    fi
else
    cat "$TEST_LOG"
    fail "review-only HTML publish with generated review succeeds"
fi

echo "--- Test 4: heartbeat review-gate degradation records metadata and continues ---"
TMP_DEGRADED_ENTRY="$TMP_STATE/blog/entries/degraded-entry.md"
TMP_DEGRADED_REPORT="$TMP_STATE/reports/spec-report-degraded-gate.yaml"
cat >"$TMP_DEGRADED_ENTRY" <<'EOF'
---
title: "Degraded gate entry"
date: "2026-04-23"
tags: [test]
open_gaps: []
threads: [test-thread]
---

Test body for degraded review-gate.
EOF
cat >"$TMP_DEGRADED_REPORT" <<'EOF'
title: "Degraded gate report"
subtitle: "Heartbeat degraded review-gate smoke"
date: "23/04/2026"
sections:
  - title: "1. Test"
    content: "This report exists to test degraded review-gate metadata."
EOF
cat >"${TMP_DEGRADED_REPORT%.yaml}.review.json" <<'EOF'
{"resolved": true, "response": "already resolved"}
EOF
touch "${TMP_DEGRADED_REPORT%.yaml}.resolved"
cat >"$TMP_BIN/review-gate" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${EDGE_REVIEW_GATE_LLM_TIMEOUT_SEC:-}" > "$EDGE_REVIEW_GATE_TIMEOUT_CAPTURE"
echo "simulated review-gate provider failure" >&2
exit 2
EOF
chmod +x "$TMP_BIN/review-gate"
if EDGE_REVIEW_GATE_TIMEOUT_CAPTURE="$TMP_BASE/review-timeout-env" \
   EDGE_CONSOLIDATE_REVIEW_GATE_DEGRADED_OK=1 \
   EDGE_REVIEW_GATE_HEARTBEAT_TIMEOUT_SEC=11 \
   "$CONSOLIDATE" "$TMP_DEGRADED_ENTRY" "$TMP_DEGRADED_REPORT" --review-only >"$TEST_LOG" 2>&1; then
    if python3 - <<'PY' "$TMP_DEGRADED_REPORT" "$EVENTS_MIRROR_FILE" "$TMP_BASE/review-timeout-env"
import json, pathlib, sys
report = pathlib.Path(sys.argv[1])
events_path = pathlib.Path(sys.argv[2])
timeout_capture = pathlib.Path(sys.argv[3])
feedback = pathlib.Path(str(report).replace(".yaml", ".feedback.json"))
assert feedback.exists(), "degraded feedback json missing"
data = json.loads(feedback.read_text(encoding="utf-8"))
final = data["final_review"]
assert final["status"] == "degraded", final
assert final["_meta"]["degraded"] is True
assert timeout_capture.read_text(encoding="utf-8").strip() == "11"
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
steps = [e for e in events if e.get("type") == "run_step"]
phase05 = [(e["phase"], e["status"], e.get("operation")) for e in steps if e["phase"] == "phase-0.5"]
assert ("phase-0.5", "degraded", "review_gate") in phase05
PY
    then
        pass "heartbeat degraded review-gate continues with explicit metadata"
    else
        cat "$TEST_LOG"
        fail "heartbeat degraded review-gate continues with explicit metadata"
    fi
else
    cat "$TEST_LOG"
    fail "heartbeat degraded review-gate exits successfully"
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
