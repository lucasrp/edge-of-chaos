#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-postflight-resilience-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/state" "$TMP_EDGE/logs"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="postflight-resilience-test"

echo "=== edge-postflight resilience Test ==="
echo ""

echo "--- Test 1: postflight step exception degrades to warning instead of aborting ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

original_protocol = module.ensure_compiled_protocol
original_execute = module._execute_postflight_step
original_before = module.before_snapshot
original_compute = module.compute_delta
try:
    module.ensure_compiled_protocol = lambda _stage: {
        "source_hash": "sha256:test",
        "compiled_hash": "sha256:test",
        "context_notes": [],
        "operator_notes": [],
        "procedures": [{"id": "boom", "kind": "validate.recent"}],
    }
    module._execute_postflight_step = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    module.before_snapshot = lambda _state: {
        "claims_open_total": 0,
        "orphans_total": 0,
        "primitive_broken_total": 0,
        "primitive_degraded_total": 0,
        "capability_broken_total": 0,
        "capability_degraded_total": 0,
        "workflow_broken_total": 0,
        "workflow_stale_total": 0,
    }
    module.compute_delta = lambda before, **_kwargs: {"claims_open_delta": 0}
    state = {"cycle_id": "cycle-postflight", "request": {"skill": "research"}, "state": {}}
    ok, postflight_status, reason, steps, delta = module.run_standard(state, "standard")
    assert ok is True
    assert postflight_status == "warning"
    assert reason == "postflight_step_warning"
    assert steps[0]["status"] == "warning"
    assert steps[0]["failure_mode"] == "exception"
    assert delta["claims_open_delta"] == 0
finally:
    module.ensure_compiled_protocol = original_protocol
    module._execute_postflight_step = original_execute
    module.before_snapshot = original_before
    module.compute_delta = original_compute
PY
then
    pass "postflight exceptions degrade to warning instead of aborting"
else
    fail "postflight exceptions degrade to warning instead of aborting"
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
