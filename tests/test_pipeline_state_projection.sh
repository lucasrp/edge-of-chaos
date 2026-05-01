#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_STATE="$(mktemp -d)"
trap 'rm -rf "$TMP_STATE"' EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/state/projections"
cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-26T10:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-complete","artifact":"blog/entries/complete.md","payload":{"pipeline":"consolidate-state","phase":"1","ok":true},"prev_hash":"sha256:root"}
{"ts":"2026-04-26T10:02:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-complete","artifact":"blog/entries/complete.md","payload":{"pipeline":"consolidate-state","phase":"4","ok":true},"prev_hash":"sha256:a"}
{"ts":"2026-04-26T10:03:00+00:00","type":"ArtifactPublished","actor":"continuity","cycle_id":"cycle-complete","artifact":"blog/entries/complete.md","payload":{"hash":"sha256:complete","source_skill":"research"},"prev_hash":"sha256:b"}
{"ts":"2026-04-26T10:04:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-complete","artifact":"blog/entries/complete.md","payload":{"pipeline":"consolidate-state","phase":"pipeline","ok":true},"prev_hash":"sha256:b2"}
{"ts":"2026-04-26T11:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-partial","artifact":"blog/entries/partial.md","payload":{"pipeline":"consolidate-state","phase":"1","ok":true},"prev_hash":"sha256:c"}
{"ts":"2026-04-26T12:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-blocked","artifact":"blog/entries/blocked.md","payload":{"pipeline":"consolidate-state","phase":"3","ok":false,"reason":"review_gate_failed"},"prev_hash":"sha256:d"}
{"ts":"2026-04-26T13:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-failed","artifact":"blog/entries/failed.md","payload":{"pipeline":"consolidate-state","phase":"4","ok":false,"reason":"meta_report_failed"},"prev_hash":"sha256:e"}
{"ts":"2026-04-26T13:01:00+00:00","type":"ArtifactPublished","actor":"continuity","cycle_id":"cycle-failed","artifact":"blog/entries/failed.md","payload":{"hash":"sha256:failed","source_skill":"report"},"prev_hash":"sha256:f"}
{"ts":"2026-04-26T14:00:00+00:00","type":"ArtifactPublished","actor":"continuity","cycle_id":"cycle-orphan","artifact":"blog/entries/orphan.md","payload":{"hash":"sha256:orphan","source_skill":"reflection"},"prev_hash":"sha256:g"}
{"ts":"2026-04-26T15:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-no-artifact","payload":{"pipeline":"consolidate-state","phase":"1","ok":true},"prev_hash":"sha256:h"}
JSONL

echo "=== pipeline state projection test ==="

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" \
  "$EDGE_DIR/tools/rollup-pipeline-state.py" --json >/tmp/pipeline-state.json

python3 - <<'PY' "$TMP_STATE/state/projections/pipeline-state.json"
import json
import sys
from pathlib import Path

projection = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = projection["summary"]
by_artifact = {item["artifact"]: item for item in projection["recent_artifacts"]}

assert summary["artifacts_total"] == 5, summary
assert summary["artifacts_attention"] == 4, summary
assert summary["orphan_events_without_artifact"] == 1, summary
assert summary["counts_by_status"]["complete"] == 1, summary
assert summary["counts_by_status"]["partial"] == 1, summary
assert summary["counts_by_status"]["blocked"] == 1, summary
assert summary["counts_by_status"]["failed"] == 1, summary
assert summary["counts_by_status"]["orphaned_publish"] == 1, summary

complete = by_artifact["blog/entries/complete.md"]
assert complete["status"] == "complete"
assert complete["published"] is True
assert complete["phase_counts"]["ok"] == 3
assert complete["terminal_phase_status"] == "ok"
assert complete["source_skill"] == "research"

partial = by_artifact["blog/entries/partial.md"]
assert partial["status"] == "partial"
assert partial["published"] is False

blocked = by_artifact["blog/entries/blocked.md"]
assert blocked["status"] == "blocked"
assert blocked["reasons"] == ["review_gate_failed"]

failed = by_artifact["blog/entries/failed.md"]
assert failed["status"] == "failed"
assert failed["published"] is True
assert failed["reasons"] == ["meta_report_failed"]

orphaned = by_artifact["blog/entries/orphan.md"]
assert orphaned["status"] == "orphaned_publish"
assert orphaned["event_counts"]["PhaseCompleted"] == 0
PY

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" \
  "$EDGE_DIR/tools/edge-replay" pipeline-state --json >/tmp/edge-replay-pipeline-state.json

python3 - <<'PY' /tmp/edge-replay-pipeline-state.json
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["summary"]["artifacts_total"] == 5
assert payload["summary"]["artifacts_attention"] == 4
PY

SUMMARY_OUTPUT="$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$EDGE_DIR/tools/edge-replay" pipeline-state --no-write)"
if echo "$SUMMARY_OUTPUT" | grep -q "complete=1" && echo "$SUMMARY_OUTPUT" | grep -q "blocked=1"; then
  echo "PASS: edge-replay pipeline-state summarizes projection counts"
else
  echo "$SUMMARY_OUTPUT"
  echo "FAIL: edge-replay pipeline-state did not show expected summary" >&2
  exit 1
fi

echo "ALL TESTS PASSED"
