#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-signals-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/health" "$TMP_STATE/state/events"

cat >"$TMP_STATE/health/current.json" <<'JSON'
{
  "schema_version": 2,
  "status": "degraded",
  "score": 74,
  "hard_fail": false,
  "dimensions": {
    "capabilities": {"status": "degraded", "detail": "primitive failures"},
    "runtime_flow": {"status": "ok", "detail": "dispatch ok"}
  }
}
JSON

cat >"$TMP_STATE/state/primitives-status.json" <<'JSON'
{
  "summary": {"health_status": "fail", "broken_total": 1, "degraded_total": 1},
  "sources": [
    {
      "name": "meta",
      "description": "Meta campaign snapshot",
      "effective_status": "broken",
      "problems": ["last_probe_failed"],
      "last_probe_ok": false
    },
    {
      "name": "grafana",
      "description": "Runtime logs",
      "effective_status": "degraded",
      "problems": ["declared_not_activated"]
    }
  ]
}
JSON

cat >"$TMP_STATE/state/capabilities-status.json" <<'JSON'
{
  "summary": {"health_status": "degraded", "broken_total": 0, "degraded_total": 1},
  "capabilities": [
    {
      "name": "source.meta",
      "kind": "primitive",
      "roles": ["signals"],
      "effective_status": "degraded",
      "description": "Meta campaign snapshot",
      "problems": ["missing credentials"]
    }
  ]
}
JSON

cat >"$TMP_STATE/state/current-dispatch.json" <<'JSON'
{
  "cycle_id": "cycle-test",
  "request": {"trigger": "heartbeat", "skill": ""},
  "state": {"active": true, "skill_dispatched": false, "phase": "opened"}
}
JSON

cat >"$TMP_STATE/state/dispatch-queue.json" <<'JSON'
[
  {"skill": "report", "status": "pending", "source": "operator"}
]
JSON

cat >"$TMP_STATE/state/workflow-health.json" <<'JSON'
{
  "summary": {"broken_total": 1, "stale_total": 0, "ignored_30d": 2}
}
JSON

cat >"$TMP_STATE/state/render-install-drift.json" <<'JSON'
{
  "summary": {"rendered_without_install": 0, "install_without_render": 0, "hash_mismatches": 0, "missing_on_disk": 0, "doctor_warn": 1, "doctor_fail": 0}
}
JSON

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-24T01:00:00+00:00","type":"PrimitiveProbeCompleted","payload":{"source":"meta","ok":false,"exit_code":1}}
{"ts":"2026-04-24T01:01:00+00:00","type":"CapabilityInvocationObserved","payload":{"capability":"source.meta","ok":false,"exit_code":77}}
JSONL

echo "=== edge-signals Smoke Test ==="
OUTPUT=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="sigtest" \
  "$EDGE_DIR/tools/edge-signals" --query "meta campaign heartbeat" --json --limit 20)

if python3 - <<'PY' "$OUTPUT"
import json
import sys

payload = json.loads(sys.argv[1])
summary = payload["summary"]
signals = {item["id"]: item for item in payload["signals"]}

assert payload["schema_version"] == 1
assert summary["signal_total"] >= 6
assert summary["critical_total"] >= 1
assert summary["warning_total"] >= 1
assert summary["primitive_health"] == "fail"
assert summary["capability_health"] == "degraded"
assert "health.current" in signals
assert "primitives.health" in signals
assert "capabilities.health" in signals
assert "dispatch.current" in signals
assert "dispatch.queue" in signals
assert "events.attention" in signals
assert signals["primitives.health"]["decision_effect"] == "gate"
assert signals["primitives.health"]["odi_id"].startswith("odi:")
assert payload["report_warning"]["required"] is True
attention = payload["report_warning"]["items"][0]["broken_or_degraded"]
assert any(item["name"] == "meta" for item in attention)
PY
then
  pass "edge-signals returns priority state signals and primitive warning"
else
  fail "edge-signals returns priority state signals and primitive warning"
fi

if grep -q '"type": "OdiObserved"' "$TMP_STATE/state/events/log.jsonl" && grep -q '"source_id": "signal.primitives"' "$TMP_STATE/state/events/log.jsonl"; then
  pass "edge-signals emits ODI observations for atomic signal channels"
else
  fail "edge-signals ODI observations missing"
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
