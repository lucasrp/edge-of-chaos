#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_STATE="$(mktemp -d /tmp/edge-cqrs-audit-XXXXXX)"
trap 'rm -rf "$TMP_STATE"' EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/state/projections"
cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-26T10:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-audit","artifact":"blog/entries/audit.md","payload":{"pipeline":"consolidate-state","phase":"pipeline","ok":true},"prev_hash":"sha256:root"}
{"ts":"2026-04-26T10:01:00+00:00","type":"ArtifactPublished","actor":"continuity","cycle_id":"cycle-audit","artifact":"blog/entries/audit.md","payload":{"source_skill":"research"},"prev_hash":"sha256:a"}
JSONL

echo "=== CQRS migration audit Smoke Test ==="

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$EDGE_DIR/tools/audit-cqrs-migration.py" --json >/tmp/cqrs-audit.json

python3 - <<'PY' /tmp/cqrs-audit.json
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["ok"] is True, payload
checks = {item["check_id"]: item for item in payload["checks"]}
for required in [
    "publisher:phase-completed",
    "command-boundary:edge-cmd",
    "hook:write-guard-shim",
    "hook:heartbeat-guard-shim",
    "postflight:pipeline-state",
    "doctor:pipeline-state",
    "backfill:pipeline-phase-events",
    "projection:pipeline-state-replay",
    "repo:fleet-grafana-absent",
]:
    assert checks[required]["status"] == "ok", checks[required]
assert payload["legacy_residuals"], "expected shim/fallback residuals to be reported"
PY

echo "ALL TESTS PASSED"
