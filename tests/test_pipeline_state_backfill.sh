#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_STATE="$(mktemp -d /tmp/edge-pipeline-backfill-XXXXXX)"
trap 'rm -rf "$TMP_STATE"' EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/state/projections"
cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-26T10:00:00+00:00","type":"ArtifactPublished","actor":"continuity","cycle_id":"cycle-legacy","artifact":"blog/entries/legacy.md","payload":{"source_skill":"research"},"prev_hash":"sha256:root"}
JSONL

echo "=== pipeline-state backfill Smoke Test ==="

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$EDGE_DIR/tools/backfill-pipeline-phase-events.py" --dry-run --json >/tmp/pipeline-backfill-dry.json
python3 - <<'PY' /tmp/pipeline-backfill-dry.json
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["candidate_total"] == 1, payload
assert payload["emitted_total"] == 0, payload
PY

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$EDGE_DIR/tools/backfill-pipeline-phase-events.py" --json >/tmp/pipeline-backfill.json
EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$EDGE_DIR/tools/rollup-pipeline-state.py" --json >/tmp/pipeline-after-backfill.json

python3 - <<'PY' /tmp/pipeline-backfill.json /tmp/pipeline-after-backfill.json
import json
import sys
backfill = json.load(open(sys.argv[1], encoding="utf-8"))
projection = json.load(open(sys.argv[2], encoding="utf-8"))
assert backfill["emitted_total"] == 1, backfill
counts = projection["summary"]["counts_by_status"]
assert counts["complete"] == 1, projection["summary"]
assert projection["summary"]["artifacts_attention"] == 0, projection["summary"]
PY

echo "ALL TESTS PASSED"
