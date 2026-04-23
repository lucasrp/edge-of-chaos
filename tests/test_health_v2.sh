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

cat >"$TMP_STATE/state/projections/claims-digest.json" <<'JSON'
{
  "open_total": 8,
  "verified_total": 13,
  "attention_count": 6,
  "unthreaded_count": 3,
  "stale_count": 4,
  "opened_30d": 6,
  "resolved_30d": 2,
  "fanout_ratio": 3.0,
  "hot_threads_by_open_claims": [{"thread_id":"alpha-thread","open_claims":5}]
}
JSON
cat >"$TMP_STATE/state/projections/orphan-claims.json" <<'JSON'
{
  "orphan_total": 3,
  "open_orphan_total": 2,
  "stale_orphan_total": 1,
  "candidate_clusters": [{"cluster_key":"alpha beta","score":6}]
}
JSON

cat >"$TMP_STATE/state/primitives-status.json" <<'JSON'
{
  "summary": {
    "health_status": "degraded",
    "declared_total": 3,
    "broken_total": 1,
    "degraded_total": 1,
    "usage_30d_total": 9
  },
  "sources": [
    {"name":"arxiv","effective_status":"active","usage_30d":4},
    {"name":"exa","effective_status":"broken","usage_30d":0},
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
    "broken_total": 1,
    "required_degraded_total": 0,
    "optional_degraded_total": 1
  },
  "capabilities": [
    {"name":"source.arxiv","effective_status":"available","invoke_30d":0},
    {"name":"source.github","effective_status":"available","invoke_30d":2},
    {"name":"search.corpus","effective_status":"broken","invoke_30d":1},
    {"name":"storage.sync","effective_status":"degraded","invoke_30d":0}
  ]
}
JSON

cat >"$TMP_STATE/blog/entries/2026-04-01-sources-research-consult-report.md" <<'MD'
---
title: Sources Research Consult Report
date: 2026-04-01
tags: [workflow]
---
MD
cat >"$TMP_STATE/blog/entries/2026-04-01-stale-playwright-validation.md" <<'MD'
---
title: Stale Playwright Validation
date: 2026-04-01
tags: [workflow]
---
MD
cat >"$TMP_STATE/state/workflow-health.json" <<'JSON'
{
  "citations": {
    "2026-04-01-sources-research-consult-report": {"used": 2, "broken": 0, "last_cited": "2026-04-22T10:00:00+00:00"},
    "2026-04-01-stale-playwright-validation": {"used": 1, "broken": 3, "last_cited": "2025-12-01T10:00:00+00:00"}
  }
}
JSON

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-23T10:00:00+00:00","type":"CycleStarted","cycle_id":"cycle-1","payload":{}}
{"ts":"2026-04-23T10:00:10+00:00","type":"SkillDispatched","cycle_id":"cycle-1","payload":{"skill":"research"}}
{"ts":"2026-04-23T10:00:20+00:00","type":"SkillRunCompleted","cycle_id":"cycle-1","payload":{"skill":"research"}}
{"ts":"2026-04-23T10:00:30+00:00","type":"PostflightCompleted","cycle_id":"cycle-1","payload":{}}
{"ts":"2026-04-23T10:00:31+00:00","type":"CycleClosed","cycle_id":"cycle-1","payload":{}}
{"ts":"2026-04-23T11:00:00+00:00","type":"CycleStarted","cycle_id":"cycle-2","payload":{}}
{"ts":"2026-04-23T11:01:00+00:00","type":"HeartbeatDispatchTimedOut","cycle_id":"cycle-2","payload":{}}
{"ts":"2026-04-23T11:02:00+00:00","type":"PostflightFailed","cycle_id":"cycle-2","payload":{}}
{"ts":"2026-04-23T10:05:00+00:00","type":"ThreadTouched","payload":{"thread_id":"alpha-thread"}}
{"ts":"2026-04-22T10:05:00+00:00","type":"ClaimPromotedToThread","payload":{"claim_id":"claim-x"}}
{"ts":"2026-04-23T10:06:00+00:00","type":"WorkflowRecommended","payload":{"slug":"2026-04-01-sources-research-consult-report"}}
{"ts":"2026-04-23T10:07:00+00:00","type":"WorkflowRecommended","payload":{"slug":"2026-04-01-stale-playwright-validation"}}
{"ts":"2026-04-23T10:08:00+00:00","type":"WorkflowUsedObserved","payload":{"slug":"2026-04-01-sources-research-consult-report"}}
{"ts":"2026-04-23T10:09:00+00:00","type":"WorkflowIgnoredObserved","payload":{"slug":"2026-04-01-stale-playwright-validation"}}
{"ts":"2026-04-23T10:10:00+00:00","type":"PrimitiveManifestUpdated","payload":{"source":"grafana"}}
{"ts":"2026-04-23T10:11:00+00:00","type":"PrimitiveMaterialized","payload":{"source":"grafana"}}
{"ts":"2026-04-23T10:12:00+00:00","type":"PrimitiveProbeCompleted","payload":{"source":"grafana","ok":true}}
{"ts":"2026-04-23T10:13:00+00:00","type":"PrimitiveBypassObserved","payload":{"source":"arxiv","capability":"source.arxiv"}}
{"ts":"2026-04-23T10:14:00+00:00","type":"CapabilityInvocationObserved","payload":{"capability":"source.github","ok":true}}
{"ts":"2026-04-23T10:15:00+00:00","type":"CapabilityProbeCompleted","payload":{"capability":"search.corpus","ok":false}}
{"ts":"2026-04-23T10:16:00+00:00","type":"ProviderProbeCompleted","payload":{"provider":"exa","ok":true,"status":"ok","http_status":"200"}}
{"ts":"2026-04-23T10:17:00+00:00","type":"ProviderProbeCompleted","payload":{"provider":"openai","ok":false,"status":"degraded","http_status":"401"}}
JSONL

echo "--- Test 1: rollup-health-v2 writes current.json with v2 dimensions ---"
if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" python3 "$EDGE_DIR/tools/rollup-health-v2.py" --write >/dev/null 2>&1; then
  if [[ "$(jq -r '.schema_version' "$TMP_STATE/health/current.json")" == "2" ]]; then
    pass "health/current.json uses schema_version=2"
  else
    fail "schema_version was not 2"
  fi
  if jq -e '.dimensions.runtime_flow and .dimensions.continuity and .dimensions.capabilities and .dimensions.workflows and .dimensions.renewal and .dimensions.substrate_discipline and .dimensions.api_runtime' "$TMP_STATE/health/current.json" >/dev/null; then
    pass "health v2 dimensions are present"
  else
    fail "health v2 dimensions missing"
  fi
  if [[ "$(jq -r '.dimensions.runtime_flow.metrics.heartbeat_dispatch_timeouts' "$TMP_STATE/health/current.json")" == "1" ]]; then
    pass "runtime_flow captured heartbeat timeouts"
  else
    fail "runtime_flow did not capture heartbeat timeouts"
  fi
  if [[ "$(jq -r '.dimensions.workflows.metrics.ignored_30d' "$TMP_STATE/health/current.json")" == "1" ]]; then
    pass "workflow dimension captured ignored recommendations"
  else
    fail "workflow ignored count wrong"
  fi
  if [[ "$(jq -r '.dimensions.substrate_discipline.metrics.primitive_bypass_30d' "$TMP_STATE/health/current.json")" == "1" ]]; then
    pass "substrate discipline captured primitive bypass"
  else
    fail "primitive bypass count wrong"
  fi
  if grep -q '"type": "HealthSnapshotComputed"' "$TMP_STATE/state/events/log.jsonl"; then
    pass "health snapshot emission wrote HealthSnapshotComputed"
  else
    fail "HealthSnapshotComputed event missing"
  fi
else
  fail "rollup-health-v2 execution failed"
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
