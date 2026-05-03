#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-health-v2-XXXXXX)"
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

mkdir -p "$TMP_HOME" "$TMP_STATE/health/raw" "$TMP_STATE/state/projections" "$TMP_STATE/state/events" \
  "$TMP_STATE/blog/entries" "$TMP_STATE/threads"

echo "=== health v2 Smoke Test ==="

for comp in disk fs_rw sqlite blog index consolidate git heartbeat mini_repos primitives; do
  cat >"$TMP_STATE/health/raw/${comp}.json" <<JSON
{"name":"$comp","status":"ok","detail":"${comp}=ok","ts":"2026-04-23T12:00:00+00:00"}
JSON
done
cat >"$TMP_STATE/health/raw/content.json" <<'JSON'
{"name":"content","status":"degraded","detail":"stale=2/8 threads_overdue=1","ts":"2026-04-23T12:00:00+00:00"}
JSON
cat >"$TMP_STATE/health/raw/quality.json" <<'JSON'
{"name":"quality","status":"degraded","detail":"adversarial=0% fontes=0% review_gate=false exa=ok openai=degraded","ts":"2026-04-23T12:00:00+00:00"}
JSON

cat >"$TMP_STATE/threads/alpha-thread.md" <<'MD'
---
title: Alpha Thread
status: active
updated: 2026-04-22
resurface: 2026-04-22
---
MD
cat >"$TMP_STATE/threads/beta-thread.md" <<'MD'
---
title: Beta Thread
status: waiting
updated: 2026-04-22
resurface: 2026-04-24
---
MD

cat >"$TMP_STATE/state/projections/open-gaps-digest.json" <<'JSON'
{
  "open_total": 8,
  "entries_with_gaps": 3,
  "hot_threads_by_open_gaps": [{"thread_id":"alpha-thread","open_gaps":5}],
  "gaps": [
    {"text":"alpha","threads":["alpha-thread"],"date":"2026-04-01T00:00:00+00:00"},
    {"text":"beta","threads":["alpha-thread"],"date":"2026-04-02T00:00:00+00:00"}
  ]
}
JSON

cat >"$TMP_STATE/state/primitives-status.json" <<'JSON'
{
  "summary": {
    "health_status": "degraded",
    "declared_total": 3,
    "broken_total": 2,
    "degraded_total": 1,
    "usage_30d_total": 9
  },
  "sources": [
    {"name":"arxiv","effective_status":"active","usage_30d":4},
    {"name":"exa","effective_status":"broken","usage_30d":0},
    {"name":"publer","effective_status":"broken","manifest_status":"suspended","usage_30d":0},
    {"name":"grafana","effective_status":"degraded","usage_30d":0}
  ]
}
JSON

cat >"$TMP_STATE/state/capabilities-status.json" <<'JSON'
{
  "summary": {
    "health_status": "degraded",
    "capability_total": 4,
    "available_total": 2,
    "degraded_total": 1,
    "broken_total": 2,
    "required_degraded_total": 0,
    "optional_degraded_total": 1
  },
  "capabilities": [
    {"name":"source.arxiv","effective_status":"available","invoke_30d":0},
    {"name":"source.github","effective_status":"available","invoke_30d":2},
    {"name":"search.corpus","effective_status":"broken","invoke_30d":1},
    {"name":"source.publer","primitive_name":"publer","effective_status":"broken","manifest_status":"suspended","invoke_30d":0},
    {"name":"storage.sync","effective_status":"degraded","invoke_30d":0}
  ]
}
JSON

ts_recent_1="$(date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%S+00:00)"
ts_recent_2="$(date -u -d '5 hours ago' +%Y-%m-%dT%H:%M:%S+00:00)"
ts_recent_3="$(date -u -d '4 hours ago' +%Y-%m-%dT%H:%M:%S+00:00)"
ts_recent_4="$(date -u -d '3 hours ago' +%Y-%m-%dT%H:%M:%S+00:00)"
ts_recent_5="$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%S+00:00)"
ts_recent_6="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S+00:00)"
ts_recent_7="$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%S+00:00)"

cat >"$TMP_STATE/state/events/log.jsonl" <<JSONL
{"ts":"$ts_recent_1","type":"CycleStarted","cycle_id":"cycle-1","payload":{}}
{"ts":"$ts_recent_2","type":"SkillDispatched","cycle_id":"cycle-1","payload":{"skill":"research"}}
{"ts":"$ts_recent_3","type":"SkillRunCompleted","cycle_id":"cycle-1","payload":{"skill":"research"}}
{"ts":"$ts_recent_4","type":"PostflightCompleted","cycle_id":"cycle-1","payload":{}}
{"ts":"$ts_recent_5","type":"CycleClosed","cycle_id":"cycle-1","payload":{}}
{"ts":"$ts_recent_1","type":"CycleStarted","cycle_id":"cycle-2","payload":{}}
{"ts":"$ts_recent_2","type":"HeartbeatDispatchTimedOut","cycle_id":"cycle-2","payload":{}}
{"ts":"$ts_recent_3","type":"PostflightFailed","cycle_id":"cycle-2","payload":{}}
{"ts":"$ts_recent_4","type":"ThreadTouched","payload":{"thread_id":"alpha-thread"}}
{"ts":"$ts_recent_5","type":"OpenGapObserved","payload":{"text":"gap-x","threads":["alpha-thread"]}}
{"ts":"$ts_recent_7","type":"PrimitiveManifestUpdated","payload":{"source":"grafana"}}
{"ts":"$ts_recent_7","type":"PrimitiveMaterialized","payload":{"source":"grafana"}}
{"ts":"$ts_recent_7","type":"PrimitiveProbeCompleted","payload":{"source":"grafana","ok":true}}
{"ts":"$ts_recent_7","type":"PrimitiveBypassObserved","payload":{"source":"arxiv","capability":"source.arxiv"}}
{"ts":"$ts_recent_7","type":"CapabilityInvocationObserved","payload":{"capability":"source.github","ok":true}}
{"ts":"$ts_recent_7","type":"CapabilityProbeCompleted","payload":{"capability":"search.corpus","ok":false}}
{"ts":"$ts_recent_7","type":"ProviderProbeCompleted","payload":{"provider":"exa","ok":true,"status":"ok","http_status":"200"}}
{"ts":"$ts_recent_7","type":"ProviderProbeCompleted","payload":{"provider":"openai","ok":false,"status":"degraded","http_status":"401"}}
JSONL

echo "--- Test 1: rollup-health-v2 writes current.json with v2 dimensions ---"
if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" python3 "$EDGE_DIR/tools/rollup-health-v2.py" --write >/dev/null 2>&1; then
  if [[ "$(jq -r '.schema_version' "$TMP_STATE/health/current.json")" == "2" ]]; then
    pass "health/current.json uses schema_version=2"
  else
    fail "schema_version was not 2"
  fi
  if jq -e '.dimensions.runtime_flow and .dimensions.continuity and .dimensions.capabilities and .dimensions.renewal and .dimensions.substrate_discipline and .dimensions.api_runtime' "$TMP_STATE/health/current.json" >/dev/null; then
    pass "health v2 dimensions are present"
  else
    fail "health v2 dimensions missing"
  fi
  if [[ "$(jq -r '.dimensions.runtime_flow.metrics.heartbeat_dispatch_timeouts' "$TMP_STATE/health/current.json")" == "1" ]]; then
    pass "runtime_flow captured heartbeat timeouts"
  else
    fail "runtime_flow did not capture heartbeat timeouts"
  fi
  if [[ "$(jq -r '.dimensions.substrate_discipline.metrics.primitive_bypass_30d' "$TMP_STATE/health/current.json")" == "1" ]]; then
    pass "substrate discipline captured primitive bypass"
  else
    fail "primitive bypass count wrong"
  fi
  if [[ "$(jq -r '.dimensions.capabilities.metrics.broken_capabilities' "$TMP_STATE/health/current.json")" == "1" && "$(jq -r '.dimensions.capabilities.metrics.broken_primitives' "$TMP_STATE/health/current.json")" == "1" ]]; then
    pass "capabilities health excludes suspended broken rows"
  else
    fail "capabilities health counted suspended rows as broken"
  fi
  if grep -q '"type": "HealthSnapshotComputed"' "$TMP_STATE/state/events/log.jsonl"; then
    pass "health snapshot emission wrote HealthSnapshotComputed"
  else
    fail "HealthSnapshotComputed event missing"
  fi
else
  fail "rollup-health-v2 execution failed"
fi

echo "--- Test 2: cycle health observation scans bounded JSONL tails ---"
if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_JSONL_TAIL_BYTES=8192 python3 - "$EDGE_DIR" "$TMP_BASE" <<'PY'
import importlib
import json
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
tmp_base = Path(sys.argv[2])
state_dir = tmp_base / "cycle-health-tail" / "state" / "events"
state_dir.mkdir(parents=True, exist_ok=True)
events_path = state_dir / "log.jsonl"

cycle_id = "cycle-health-tail-proof"
large_payload = "x" * 2048
with events_path.open("w", encoding="utf-8") as handle:
    for index in range(5000):
        handle.write(json.dumps({
            "ts": "2026-05-01T00:00:00+00:00",
            "type": "PrimitiveInvocationObserved",
            "cycle_id": "old-cycle",
            "payload": {"source": "old", "noise": large_payload, "index": index},
        }) + "\n")
    handle.write(json.dumps({
        "ts": "2026-05-02T00:01:00+00:00",
        "type": "PrimitiveInvocationObserved",
        "cycle_id": cycle_id,
        "payload": {"source": "exa"},
    }) + "\n")

sys.path.insert(0, str(edge_dir / "tools"))
module = importlib.import_module("_shared.health_runtime")

def fail_full_read(path):
    raise AssertionError("cycle health must not read the full JSONL file")

module._read_jsonl = fail_full_read
observations = module.observe_cycle_health_events({"cycle_id": cycle_id}, path=events_path)
assert observations["primitive_bypass"] == 1
assert events_path.stat().st_size > 8 * 1024 * 1024
PY
then
  pass "cycle health observation scans bounded JSONL tails"
else
  fail "cycle health observation scans bounded JSONL tails"
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
