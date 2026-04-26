#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_STATE="$(mktemp -d)"
trap 'rm -rf "$TMP_STATE"' EXIT

mkdir -p "$TMP_STATE/state/events"
cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-26T10:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-complete","payload":{"trigger":"heartbeat","skill":"planner","primary_thread_id":"thread-a"}}
{"ts":"2026-04-26T10:01:00+00:00","type":"SkillDispatched","actor":"edge-dispatch","cycle_id":"cycle-complete","payload":{"trigger":"heartbeat","skill":"planner","primary_thread_id":"thread-a"}}
{"ts":"2026-04-26T10:20:00+00:00","type":"CycleClosed","actor":"edge-dispatch","cycle_id":"cycle-complete","payload":{"trigger":"heartbeat","skill":"planner","close_status":"completed","primary_thread_id":"thread-a"}}
{"ts":"2026-04-26T11:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-missing-dispatch","payload":{"trigger":"operator","skill":"research"}}
{"ts":"2026-04-26T12:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-missing-close","payload":{"trigger":"operator","skill":"research"}}
{"ts":"2026-04-26T12:01:00+00:00","type":"SkillDispatched","actor":"edge-dispatch","cycle_id":"cycle-missing-close","payload":{"trigger":"operator","skill":"research"}}
{"ts":"2026-04-26T13:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-failed","payload":{"trigger":"heartbeat","skill":"autonomy"}}
{"ts":"2026-04-26T13:01:00+00:00","type":"SkillDispatched","actor":"edge-dispatch","cycle_id":"cycle-failed","payload":{"trigger":"heartbeat","skill":"autonomy"}}
{"ts":"2026-04-26T13:02:00+00:00","type":"CycleClosed","actor":"edge-dispatch","cycle_id":"cycle-failed","payload":{"trigger":"heartbeat","skill":"autonomy","close_status":"failed","reason":"backend_error"}}
JSONL

EDGE_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_HOST=test-host EDGE_INSTANCE=test-instance \
  "$EDGE_DIR/observability/fleet/publish_dispatch_projection.py" --dry-run \
  >"$TMP_STATE/projection-event.json"

python3 - <<'PY' "$TMP_STATE/projection-event.json"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
events = payload["events"]
event = next(item for item in events if item["type"] == "DispatchCycleProjectionPublished")
projection = event["payload"]["projection"]
summary = projection["summary"]
status_counts = {item["status"]: item["count"] for item in events if item["type"] == "DispatchCycleStatusCountPublished"}
skill_counts = {item["skill"]: item["count"] for item in events if item["type"] == "DispatchCycleSkillCountPublished"}
metric_counts = {item["metric"]: item["count"] for item in events if item["type"] == "DispatchCycleMetricPublished"}

assert event["type"] == "DispatchCycleProjectionPublished", event
assert event["instance"] == "test-instance", event
assert event["summary_cycles_total"] == 4, event
assert event["summary_cycles_incomplete"] == 3, event
assert event["summary_closed"] == 1, event
assert event["summary_failed"] == 1, event
assert event["summary_missing_dispatch"] == 1, event
assert event["summary_missing_close"] == 1, event
assert status_counts == {"closed": 1, "failed": 1, "missing_close": 1, "missing_dispatch": 1}, status_counts
assert skill_counts == {"autonomy": 1, "planner": 1, "research": 2}, skill_counts
assert metric_counts["cycles_total"] == 4, metric_counts
assert metric_counts["cycles_incomplete"] == 3, metric_counts
assert all(item["_loki_line"] == str(item["count"]) for item in events if item["type"].endswith("CountPublished")), events
assert summary["counts_by_skill"]["planner"] == 1, summary
assert summary["counts_by_skill"]["research"] == 2, summary
assert summary["counts_by_skill"]["autonomy"] == 1, summary
PY

python3 -m json.tool "$EDGE_DIR/observability/fleet/grafana/dashboards/fleet-dispatch-cycles.json" >/dev/null

echo "ALL TESTS PASSED"
