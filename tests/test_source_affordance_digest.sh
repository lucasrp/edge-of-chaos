#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-affordance-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state/events"

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-24T01:00:00+00:00","type":"OdiObserved","payload":{"odi_id":"odi-hn-1","source_id":"source.hn","primitive":"edge-sources","context":"discovery","query":"agent search patterns","title":"HN discussion","url":"https://news.ycombinator.com/item?id=1","rank":1,"score":120}}
{"ts":"2026-04-24T01:01:00+00:00","type":"OdiObserved","payload":{"odi_id":"odi-docs-1","source_id":"source.docs","primitive":"edge-sources","context":"confirmation","query":"agent search patterns","title":"Official docs","url":"https://example.com/docs","rank":1,"score":10}}
JSONL

echo "=== source affordance digest Smoke Test ==="

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="afftest" \
  "$EDGE_DIR/tools/edge-affordance" evaluate source.hn \
  --affordance novelty \
  --score 5 \
  --context "early technical signal" \
  --odi odi-hn-1 \
  --query "agent search patterns" \
  --reason "surfaced a new source pattern before official docs" >/dev/null

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="afftest" \
  "$EDGE_DIR/tools/edge-affordance" evaluate source.docs \
  --affordance confirmation \
  --score 4 \
  --context "primary evidence" \
  --odi odi-docs-1 \
  --query "agent search patterns" \
  --reason "confirmed exact behavior" >/dev/null

if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="afftest" \
  python3 "$EDGE_DIR/tools/rollup-affordances.py" >/dev/null; then
  if python3 - <<'PY' "$TMP_STATE/state/source-affordance-digest.json"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sources = payload["sources"]
hn = sources["source.hn"]["learned_affordances"]["novelty"]
docs = sources["source.docs"]["learned_affordances"]["confirmation"]
assert payload["schema_version"] == 1
assert hn["score_5"] == 5.0
assert hn["score"] == 1.0
assert hn["evidence_count"] == 1
assert hn["recent_odis"][0]["odi_id"] == "odi-hn-1"
assert hn["recent_odis"][0]["title"] == "HN discussion"
assert docs["score_5"] == 4.0
assert docs["top_contexts"][0]["context"] == "primary evidence"
PY
  then
    pass "rollup builds per-source affordance digest from ODI-anchored grades"
  else
    fail "source affordance digest content was wrong"
  fi
else
  fail "rollup-affordances execution failed"
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
