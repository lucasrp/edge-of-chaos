#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_STATE="$(mktemp -d)"
trap 'rm -rf "$TMP_STATE"' EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/state/projections"
cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-26T10:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-complete","payload":{"trigger":"heartbeat","skill":"planner","primary_thread_id":"thread-a"},"prev_hash":"sha256:root"}
{"ts":"2026-04-26T10:01:00+00:00","type":"SkillDispatched","actor":"edge-dispatch","cycle_id":"cycle-complete","payload":{"trigger":"heartbeat","skill":"planner","dispatch_mode":"normal","primary_thread_id":"thread-a"},"prev_hash":"sha256:a"}
{"ts":"2026-04-26T10:20:00+00:00","type":"CycleClosed","actor":"edge-dispatch","cycle_id":"cycle-complete","payload":{"trigger":"heartbeat","skill":"planner","close_status":"completed","reason":"","primary_thread_id":"thread-a"},"prev_hash":"sha256:b"}
{"ts":"2026-04-26T11:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-missing-dispatch","payload":{"trigger":"operator","skill":"research"},"prev_hash":"sha256:c"}
{"ts":"2026-04-26T12:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-missing-close","payload":{"trigger":"operator","skill":"research"},"prev_hash":"sha256:d"}
{"ts":"2026-04-26T12:01:00+00:00","type":"SkillDispatched","actor":"edge-dispatch","cycle_id":"cycle-missing-close","payload":{"trigger":"operator","skill":"research"},"prev_hash":"sha256:e"}
{"ts":"2026-04-26T13:00:00+00:00","type":"CycleStarted","actor":"edge-dispatch","cycle_id":"cycle-failed","payload":{"trigger":"heartbeat","skill":"autonomy"},"prev_hash":"sha256:f"}
{"ts":"2026-04-26T13:01:00+00:00","type":"SkillDispatched","actor":"edge-dispatch","cycle_id":"cycle-failed","payload":{"trigger":"heartbeat","skill":"autonomy"},"prev_hash":"sha256:g"}
{"ts":"2026-04-26T13:02:00+00:00","type":"CycleClosed","actor":"edge-dispatch","cycle_id":"cycle-failed","payload":{"trigger":"heartbeat","skill":"autonomy","close_status":"failed","reason":"backend_error"},"prev_hash":"sha256:h"}
JSONL

echo "=== dispatch cycle projection test ==="

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" \
  "$EDGE_DIR/tools/rollup-dispatch-cycles.py" --json >/tmp/dispatch-cycles.json

python3 - <<'PY' "$TMP_STATE/state/projections/dispatch-cycles.json"
import json
import sys
from pathlib import Path

projection = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = projection["summary"]
by_id = {cycle["cycle_id"]: cycle for cycle in projection["recent_cycles"]}

assert summary["cycles_total"] == 4, summary
assert summary["cycles_incomplete"] == 3, summary
assert summary["counts_by_status"]["closed"] == 1, summary
assert summary["counts_by_status"]["missing_dispatch"] == 1, summary
assert summary["counts_by_status"]["missing_close"] == 1, summary
assert summary["counts_by_status"]["failed"] == 1, summary
assert summary["counts_by_trigger"]["heartbeat"] == 2, summary
assert summary["counts_by_trigger"]["operator"] == 2, summary

assert by_id["cycle-complete"]["status"] == "closed"
assert by_id["cycle-complete"]["phase"] == "closed"
assert by_id["cycle-complete"]["primary_thread_id"] == "thread-a"
assert by_id["cycle-missing-dispatch"]["status"] == "missing_dispatch"
assert by_id["cycle-missing-close"]["status"] == "missing_close"
assert by_id["cycle-failed"]["status"] == "failed"
assert by_id["cycle-failed"]["close_reason"] == "backend_error"
PY

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" \
  "$EDGE_DIR/tools/edge-replay" dispatch-cycles --json >/tmp/edge-replay-dispatch-cycles.json

python3 - <<'PY' /tmp/edge-replay-dispatch-cycles.json
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["summary"]["cycles_total"] == 4
assert payload["summary"]["cycles_incomplete"] == 3
PY

TAIL_OUTPUT="$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$EDGE_DIR/tools/edge-replay" --tail --type CycleClosed -n 2)"
if echo "$TAIL_OUTPUT" | grep -q "cycle-failed" && echo "$TAIL_OUTPUT" | grep -q "close_status=failed"; then
  echo "PASS: edge-replay tail shows filtered cycle close events"
else
  echo "$TAIL_OUTPUT"
  echo "FAIL: edge-replay tail did not show expected close event" >&2
  exit 1
fi

echo "ALL TESTS PASSED"

