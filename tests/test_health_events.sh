#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-health-events-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_HOME" "$TMP_STATE/state/events" "$TMP_STATE/health"

echo "=== health events Smoke Test ==="

echo "--- Test 1: emit_component also emits HealthComponentObserved ---"
if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_DIR="$EDGE_DIR" \
  bash -lc 'source "'"$EDGE_DIR"'/bin/survival-lib.sh"; emit_component demo ok "works"' >/dev/null 2>&1; then
  if grep -q '"type": "HealthComponentObserved"' "$TMP_STATE/state/events/log.jsonl" && grep -q '"name": "demo"' "$TMP_STATE/state/events/log.jsonl"; then
    pass "HealthComponentObserved emitted from emit_component"
  else
    fail "HealthComponentObserved missing after emit_component"
  fi
else
  fail "emit_component execution failed"
fi

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-23T11:00:00+00:00","type":"PrimitiveInvocationObserved","cycle_id":"cycle-health-1","payload":{"source":"arxiv"}}
{"ts":"2026-04-23T11:00:10+00:00","type":"CapabilityInvocationObserved","cycle_id":"cycle-health-1","payload":{"capability":"source.github","ok":true}}
{"ts":"2026-04-23T11:00:20+00:00","type":"WorkflowUsedObserved","cycle_id":"cycle-health-1","payload":{"slug":"wf-used"}}
JSONL

echo "--- Test 2: observe_cycle_health_events emits workflow ignored and primitive bypass ---"
if OUTPUT=$(env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

repo = Path(os.environ["EDGE_REPO_DIR"])
sys.path.insert(0, str(repo / "tools"))
from _shared.health_runtime import observe_cycle_health_events

state = {
    "cycle_id": "cycle-health-1",
    "request": {
        "skill": "research",
        "corpus_query": "claim continuity graph",
        "workflow_recommendations": [
            {"slug": "wf-used", "source": "search_sidecar"},
            {"slug": "wf-ignored", "source": "search_sidecar"},
        ],
    },
}

print(json.dumps(observe_cycle_health_events(state), ensure_ascii=False))
PY
); then
  if [[ "$(jq -r '.workflow_ignored' <<<"$OUTPUT")" == "1" ]]; then
    pass "workflow ignored observation count correct"
  else
    fail "workflow ignored observation count wrong: $OUTPUT"
  fi
  if [[ "$(jq -r '.primitive_bypass' <<<"$OUTPUT")" == "1" ]]; then
    pass "primitive bypass observation count correct"
  else
    fail "primitive bypass observation count wrong: $OUTPUT"
  fi
  if grep -q '"type": "WorkflowIgnoredObserved"' "$TMP_STATE/state/events/log.jsonl" && grep -q '"slug": "wf-ignored"' "$TMP_STATE/state/events/log.jsonl"; then
    pass "WorkflowIgnoredObserved emitted"
  else
    fail "WorkflowIgnoredObserved missing"
  fi
  if grep -q '"type": "PrimitiveBypassObserved"' "$TMP_STATE/state/events/log.jsonl" && grep -q '"source": "arxiv"' "$TMP_STATE/state/events/log.jsonl"; then
    pass "PrimitiveBypassObserved emitted"
  else
    fail "PrimitiveBypassObserved missing"
  fi
else
  fail "observe_cycle_health_events execution failed"
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
