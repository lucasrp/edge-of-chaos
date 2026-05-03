#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-postflight-pipeline-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/state/projections" "$TMP_STATE/logs" "$TMP_HOME"

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="postflight-pipeline-test"
export EDGE_POSTFLIGHT_PIPELINE_SETTLE_ATTEMPTS=2
export EDGE_POSTFLIGHT_PIPELINE_SETTLE_INTERVAL_SEC=0
export EDGE_POSTFLIGHT_PIPELINE_SETTLE_MAX_EVENT_AGE_SEC=999999999

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-26T10:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-ok","artifact":"blog/entries/ok.md","payload":{"pipeline":"consolidate-state","phase":"pipeline","ok":true},"prev_hash":"sha256:root"}
{"ts":"2026-04-26T10:01:00+00:00","type":"ArtifactPublished","actor":"continuity","cycle_id":"cycle-ok","artifact":"blog/entries/ok.md","payload":{"source_skill":"research"},"prev_hash":"sha256:a"}
{"ts":"2026-04-26T11:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-bad","artifact":"blog/entries/bad.md","payload":{"pipeline":"consolidate-state","phase":"3","ok":false,"reason":"verification failed"},"prev_hash":"sha256:b"}
{"ts":"2026-04-26T12:00:00+00:00","type":"ArtifactStanddownRecorded","actor":"edge-runner","cycle_id":"cycle-standdown","artifact":"state/runtime/standdowns/cycle-standdown-discovery.md","payload":{"source_skill":"discovery","skill":"discovery","status":"standdown","reason":"principled_standdown"},"prev_hash":"sha256:c"}
{"ts":"2026-04-26T13:00:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-pending","artifact":"blog/entries/pending.md","payload":{"pipeline":"consolidate-state","phase":"0a","ok":true},"prev_hash":"sha256:d"}
{"ts":"2026-04-26T13:01:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-pending","artifact":"blog/entries/pending.md","payload":{"pipeline":"consolidate-state","phase":"0.3","ok":false,"reason":"review generated; pending resolution"},"prev_hash":"sha256:e"}
JSONL

echo "=== postflight pipeline-state Smoke Test ==="
echo "Temp state: $TMP_STATE"
echo ""

echo "--- Test 1: clean cycle satisfies pipeline-state step ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

result = module._execute_postflight_step(
    {"id": "pipeline-state", "kind": "pipeline_state.refresh"},
    {"cycle_id": "cycle-ok", "request": {}, "state": {}},
)
assert result["status"] == "ok", result
assert result["satisfied"] is True, result
assert result["payload"]["summary"]["counts_by_status"]["complete"] == 1
PY
then
    pass "postflight pipeline-state step is OK for a complete cycle"
else
    fail "postflight pipeline-state step is OK for a complete cycle"
fi

echo "--- Test 2: current-cycle pipeline attention becomes a soft warning ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

result = module._execute_postflight_step(
    {"id": "pipeline-state", "kind": "pipeline_state.refresh"},
    {"cycle_id": "cycle-bad", "request": {}, "state": {}},
)
assert result["status"] == "warning", result
assert result["satisfied"] is False, result
assert result["current_attention"][0]["artifact"] == "blog/entries/bad.md"
PY
then
    pass "postflight pipeline-state step warns on current-cycle blocked artifacts"
else
    fail "postflight pipeline-state step warns on current-cycle blocked artifacts"
fi

echo "--- Test 3: current-cycle accepted standdown satisfies pipeline-state step ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

result = module._execute_postflight_step(
    {"id": "pipeline-state", "kind": "pipeline_state.refresh"},
    {"cycle_id": "cycle-standdown", "request": {}, "state": {}},
)
assert result["status"] == "ok", result
assert result["satisfied"] is True, result
assert result["payload"]["summary"]["counts_by_status"]["standdown"] == 1
assert result.get("current_attention") in (None, []), result
PY
then
    pass "postflight pipeline-state step is OK for accepted standdown cycles"
else
    fail "postflight pipeline-state step is OK for accepted standdown cycles"
fi

echo "--- Test 4: current-cycle pending review is retried before warning ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

original = module.run_subprocess
calls = {"n": 0}

def wrapped(cmd):
    calls["n"] += 1
    result = original(cmd)
    if calls["n"] == 1:
        with (state_dir / "state" / "events" / "log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('{"ts":"2026-04-26T13:02:00+00:00","type":"PhaseCompleted","actor":"consolidate-state","cycle_id":"cycle-pending","artifact":"blog/entries/pending.md","payload":{"pipeline":"consolidate-state","phase":"pipeline","ok":true},"prev_hash":"sha256:f"}\n')
            handle.write('{"ts":"2026-04-26T13:03:00+00:00","type":"ArtifactPublished","actor":"consolidate-state","cycle_id":"cycle-pending","artifact":"blog/entries/pending.md","payload":{"source_skill":"report","pipeline":"consolidate-state"},"prev_hash":"sha256:g"}\n')
    return result

module.run_subprocess = wrapped
result = module._execute_postflight_step(
    {"id": "pipeline-state", "kind": "pipeline_state.refresh"},
    {"cycle_id": "cycle-pending", "request": {}, "state": {}},
)
assert calls["n"] >= 2, calls
assert result["status"] == "ok", result
assert result["satisfied"] is True, result
assert "settle_attempts=1" in result["detail"], result
assert result.get("current_attention") in (None, []), result
PY
then
    pass "postflight retries pending current-cycle pipeline attention before warning"
else
    fail "postflight retries pending current-cycle pipeline attention before warning"
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
