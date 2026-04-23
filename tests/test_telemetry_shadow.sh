#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-telemetry-shadow-XXXXXX)"
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

echo "=== telemetry shadow Smoke Test ==="

if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="shadow-test" \
  python3 - <<'PY'
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.environ["EDGE_REPO_DIR"])
from tools._shared.telemetry import log_event
from config.paths import EVENTS_FILE, STATE_EVENTS_FILE

log_event("demo_event", answer=42)
events = [json.loads(line) for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
assert events[-1]["type"] == "demo_event"
assert not STATE_EVENTS_FILE.exists() or "LegacyTelemetryObserved" not in STATE_EVENTS_FILE.read_text(encoding="utf-8")
PY
then
  pass "legacy shadow is disabled by default"
else
  fail "legacy shadow is disabled by default"
fi

rm -rf "$TMP_STATE"
mkdir -p "$TMP_STATE"

if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="shadow-test" EDGE_EMIT_LEGACY_SHADOW=1 \
  python3 - <<'PY'
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.environ["EDGE_REPO_DIR"])
from tools._shared.telemetry import log_event
from config.paths import STATE_EVENTS_FILE

log_event("demo_event", answer=42)
events = [json.loads(line) for line in STATE_EVENTS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
assert any(event.get("type") == "LegacyTelemetryObserved" for event in events)
PY
then
  pass "legacy shadow can be re-enabled explicitly"
else
  fail "legacy shadow can be re-enabled explicitly"
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
