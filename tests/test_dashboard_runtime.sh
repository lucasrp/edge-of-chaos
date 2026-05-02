#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-runtime-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"
AUTONOMY_DIR="$EDGE_DIR/autonomy"
CAP_FILE="$AUTONOMY_DIR/capabilities.md"
FRONTIER_FILE="$AUTONOMY_DIR/frontier.md"
CAP_BACKUP="$TMP_BASE/capabilities.md.bak"
FRONTIER_BACKUP="$TMP_BASE/frontier.md.bak"

cleanup() {
    if [ -f "$CAP_BACKUP" ]; then
        mv "$CAP_BACKUP" "$CAP_FILE"
    else
        rm -f "$CAP_FILE"
    fi
    if [ -f "$FRONTIER_BACKUP" ]; then
        mv "$FRONTIER_BACKUP" "$FRONTIER_FILE"
    else
        rm -f "$FRONTIER_FILE"
    fi
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/logs" "$TMP_STATE/blog/entries" "$AUTONOMY_DIR"

if [ -f "$CAP_FILE" ]; then cp "$CAP_FILE" "$CAP_BACKUP"; fi
if [ -f "$FRONTIER_FILE" ]; then cp "$FRONTIER_FILE" "$FRONTIER_BACKUP"; fi

cat >"$TMP_STATE/state/current-dispatch.json" <<'JSON'
{
  "version": 1,
  "cycle_id": "cycle-20260420T210000Z-test01",
  "request": {
    "trigger": "heartbeat",
    "skill": "planner",
    "policy": "autonomous"
  },
  "state": {
    "active": true,
    "phase": "skill_dispatched",
    "skill_dispatched": true,
    "preflight_status": "completed",
    "skill_status": "running",
    "postflight_status": "pending",
    "opened_at": "2026-04-20T21:00:00+00:00",
    "dispatched_at": "2026-04-20T21:01:00+00:00",
    "updated_at": "2026-04-20T21:01:30+00:00"
  }
}
JSON

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-20T20:00:00+00:00","type":"CycleStarted","cycle_id":"cycle-a","payload":{"trigger":"heartbeat"}}
{"ts":"2026-04-20T20:01:00+00:00","type":"SkillDispatched","cycle_id":"cycle-a","payload":{"trigger":"heartbeat","skill":"planner","dispatch_mode":"normal"}}
{"ts":"2026-04-20T20:20:00+00:00","type":"CycleClosed","cycle_id":"cycle-a","payload":{"trigger":"heartbeat","skill":"planner","close_status":"completed"}}
{"ts":"2026-04-20T20:30:00+00:00","type":"CycleStarted","cycle_id":"cycle-b","payload":{"trigger":"operator"}}
{"ts":"2026-04-20T20:31:00+00:00","type":"SkillDispatched","cycle_id":"cycle-b","payload":{"trigger":"operator","skill":"research","dispatch_mode":"normal"}}
{"ts":"2026-04-20T20:40:00+00:00","type":"PrimitiveContractWritten","cycle_id":"cycle-b","payload":{"source":"overleaf","status":"contract-only"}}
{"ts":"2026-04-20T20:41:00+00:00","type":"PrimitiveProbeCompleted","cycle_id":"cycle-b","payload":{"source":"exa","exit_code":1,"ok":false}}
JSONL

cat >"$TMP_STATE/logs/skill-steps.jsonl" <<'JSONL'
{"skill":"planner","event":"end","expected":5,"done":4,"explicit_skips":1,"silent_skips":["crossref"],"completion_pct":80,"ts":"2026-04-20T20:02:00"}
{"skill":"research","event":"end","expected":6,"done":6,"explicit_skips":0,"silent_skips":[],"completion_pct":100,"ts":"2026-04-20T20:32:00"}
JSONL

cat >"$TMP_STATE/state/primitive-usage-rollup.json" <<'JSON'
{
  "window_days": 30,
  "total_calls": 17,
  "by_source": {
    "exa": {"calls": 10, "ok": 8, "fail": 2, "ok_rate": 0.8, "avg_ms": 410, "last_ts": "2026-04-20T20:41:00+00:00"},
    "grok": {"calls": 5, "ok": 5, "fail": 0, "ok_rate": 1.0, "avg_ms": 900, "last_ts": "2026-04-20T19:41:00+00:00"},
    "overleaf": {"calls": 2, "ok": 0, "fail": 2, "ok_rate": 0.0, "avg_ms": 120, "last_ts": "2026-04-20T20:40:00+00:00"}
  }
}
JSON

cat >"$TMP_STATE/state/primitives-status.json" <<'JSON'
{
  "generated_at": "2026-04-20T20:42:00+00:00",
  "summary": {
    "window_days": 30,
    "declared_total": 3,
    "degraded_total": 1,
    "active_total": 1,
    "probed_total": 0,
    "broken_total": 1,
    "usage_30d_total": 17,
    "counts_by_effective_status": {
      "broken": 1,
      "active": 1,
      "degraded": 1
    },
    "health_status": "fail"
  },
  "sources": [
    {
      "name": "exa",
      "effective_status": "broken",
      "probe_status": "fail",
      "usage_30d": 10,
      "manifest_status": "active",
      "problems": ["last_probe_failed"]
    },
    {
      "name": "grok",
      "effective_status": "active",
      "probe_status": "unknown",
      "usage_30d": 5,
      "manifest_status": "active",
      "problems": []
    },
    {
      "name": "overleaf",
      "effective_status": "degraded",
      "probe_status": "unknown",
      "usage_30d": 2,
      "manifest_status": "contract-only",
      "problems": []
    }
  ]
}
JSON

cat >"$TMP_STATE/state/sources-manifest.yaml" <<'YAML'
version: 1
sources:
  - name: exa
    status: active
  - name: grok
    status: active
  - name: overleaf
    status: contract-only
YAML

cat >"$CAP_FILE" <<'MD'
| # | Name | Sheridan |
|---|------|----------|
| 1 | Safe execution | 8 |
| 2 | Runtime transparency | 4 |
| 3 | Primitive stewardship | 3 |
MD

cat >"$FRONTIER_FILE" <<'MD'
### GAP-101: instrument explicit pre-skill evidence
### GAP-102: instrument explicit post-skill evidence
MD

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$VENV_PY" - <<'PY'
import os
import sys

edge_dir = os.environ["EDGE_REPO_DIR"]
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

client = app.test_client()
runtime = client.get("/api/dashboard/runtime")
assert runtime.status_code == 200, runtime.status_code
data = runtime.get_json()

assert data["runtime_current_cycle"]["active"] is True
assert data["runtime_current_cycle"]["skill"] == "planner"
assert data["runtime_skill_evidence"]["pre_skill"]["status"] == "gap"
assert data["runtime_skill_evidence"]["post_skill"]["status"] == "gap"
assert data["runtime_skill_evidence"]["skill_runs_total"] == 2
assert data["runtime_primitives"]["available"] is True
assert data["runtime_primitives"]["health_status"] == "fail"
assert data["runtime_primitives"]["declared_total"] == 3
assert data["runtime_primitives"]["degraded_total"] == 1
assert data["runtime_primitives"]["broken_total"] == 1
assert data["runtime_primitives"]["usage_30d_total"] == 17
assert data["runtime_autonomy"]["available"] is True
assert data["runtime_autonomy"]["avg"] == 5.0
assert len(data["runtime_recent_cycles"]) >= 2

partial = client.get("/partials/runtime")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "runtime transparency" in text
assert "planner" in text
assert "primitives status" in text
assert "degraded" in text
assert "broken" in text
assert "GAP-101" in text
print("ok")
PY
