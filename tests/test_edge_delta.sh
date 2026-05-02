#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-delta-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"

DELTA_TOOL="$EDGE_DIR/tools/edge-delta"

echo "=== edge-delta Test ==="
echo ""

echo "--- Test 1: show returns an empty normalized digest ---"
if "$DELTA_TOOL" show --json >"$TMP_BASE/empty.json" && python3 - <<'PY' "$TMP_BASE/empty.json"
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["kind"] == "edge_delta_digest"
assert payload["work"]["open_work"] == []
assert payload["learning"]["recent_failures"] == []
assert payload["handoff"]["inject_to_next_skill"] == []
assert payload["digest_hash"].startswith("sha256:")
PY
then
    pass "show normalizes an empty digest"
else
    fail "show normalizes an empty digest"
fi

echo "--- Test 2: planner update persists work and handoff sections ---"
cat >"$TMP_BASE/planner.json" <<'JSON'
{
  "summary": "runtime delta work is active",
  "work": {
    "open_work": [
      {
        "id": "work-delta",
        "title": "Curate delta digest",
        "surface": "runtime",
        "status": "active",
        "priority": "high",
        "evidence": ["issue #390"]
      }
    ],
    "archived_work_recent": [
      {"id": "old-work", "summary": "obsolete backlog", "status": "archived"}
    ],
    "priority_threads": [
      {"id": "thread-runtime", "summary": "runtime continuity", "priority": "high"}
    ],
    "surface_baselines": {
      "github:lucasrp/edge-of-chaos": {
        "kind": "git",
        "last_seen_ref": "abc123",
        "summary": "baseline"
      }
    }
  },
  "handoff": {
    "inject_to_next_skill": [
      {"summary": "keep delta_frame in context", "priority": "high"}
    ]
  }
}
JSON

if "$DELTA_TOOL" validate --payload-file "$TMP_BASE/planner.json" >/dev/null \
    && "$DELTA_TOOL" update --skill planner --payload-file "$TMP_BASE/planner.json" >"$TMP_BASE/planner-update.json" \
    && python3 - <<'PY' "$TMP_STATE/state/projections/continuity-deltas/runtime-latest.json"
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["summary"] == "runtime delta work is active"
assert payload["work"]["open_work"][0]["id"] == "work-delta"
assert payload["open_work"][0]["id"] == "work-delta"
assert payload["surface_baselines"]["github:lucasrp/edge-of-chaos"]["last_seen_ref"] == "abc123"
assert payload["handoff"]["inject_to_next_skill"][0]["summary"] == "keep delta_frame in context"
assert payload["updates"][-1]["skill"] == "planner"
assert payload["digest_hash"].startswith("sha256:")
PY
then
    pass "planner update persists work and handoff"
else
    fail "planner update persists work and handoff"
fi

echo "--- Test 3: research update preserves work and updates learning ---"
cat >"$TMP_BASE/research.json" <<'JSON'
{
  "summary": "learning digest updated",
  "learning": {
    "recent_failures": [
      {"id": "failure-repeat", "summary": "operator had to repeat delta continuity", "status": "active"}
    ],
    "rules_to_preserve": [
      {"id": "rule-delta", "summary": "delta digest updates are deterministic", "status": "active"}
    ],
    "protocol_gaps": [],
    "skill_patch_candidates": [
      {"id": "patch-planner", "summary": "planner must preserve curation context", "status": "active"}
    ],
    "archived_guidance_recent": []
  }
}
JSON

if "$DELTA_TOOL" update --skill research --payload-file "$TMP_BASE/research.json" >/dev/null \
    && python3 - <<'PY' "$TMP_STATE/state/projections/continuity-deltas/runtime-latest.json"
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["summary"] == "learning digest updated"
assert payload["work"]["open_work"][0]["id"] == "work-delta"
assert payload["learning"]["recent_failures"][0]["id"] == "failure-repeat"
assert payload["learning"]["rules_to_preserve"][0]["id"] == "rule-delta"
assert payload["updates"][-1]["skill"] == "research"
PY
then
    pass "research update preserves work and updates learning"
else
    fail "research update preserves work and updates learning"
fi

echo "--- Test 4: invalid payload is rejected ---"
cat >"$TMP_BASE/bad.json" <<'JSON'
{"work": {"open_work": "not-a-list"}}
JSON

set +e
"$DELTA_TOOL" validate --skill planner --payload-file "$TMP_BASE/bad.json" >/dev/null 2>&1
STATUS=$?
set -e
if [[ "$STATUS" -ne 0 ]]; then
    pass "invalid payload is rejected"
else
    fail "invalid payload is rejected"
fi

echo "--- Test 5: action-skill update accepts mixed digest sections ---"
cat >"$TMP_BASE/mixed.json" <<'JSON'
{
  "summary": "mixed digest update from action skill",
  "work": {
    "priority_threads": [
      {"id": "thread-action", "summary": "action skills can curate work", "status": "active"}
    ]
  },
  "learning": {
    "recent_failures": [
      {"id": "failure-action", "summary": "action skills can record learning", "status": "active"}
    ]
  }
}
JSON

if "$DELTA_TOOL" update --skill report --payload-file "$TMP_BASE/mixed.json" >/dev/null \
    && python3 - <<'PY' "$TMP_STATE/state/projections/continuity-deltas/runtime-latest.json"
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["summary"] == "mixed digest update from action skill"
assert payload["work"]["priority_threads"][0]["id"] == "thread-action"
assert payload["learning"]["recent_failures"][0]["id"] == "failure-action"
assert payload["updates"][-1]["skill"] == "report"
PY
then
    pass "action-skill update accepts mixed digest sections"
else
    fail "action-skill update accepts mixed digest sections"
fi

echo "--- Test 6: no-op update records explicit continuity decision ---"
if "$DELTA_TOOL" update --skill planner --no-op --summary "no heartbeat curation changes" >/dev/null \
    && python3 - <<'PY' "$TMP_STATE/state/projections/continuity-deltas/runtime-latest.json"
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["updates"][-1]["no_op"] is True
assert payload["updates"][-1]["summary"] == "no heartbeat curation changes"
PY
then
    pass "no-op update records explicit continuity decision"
else
    fail "no-op update records explicit continuity decision"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
