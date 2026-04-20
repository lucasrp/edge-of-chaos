#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-install-telemetry-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_EDGE="$TMP_BASE/agent"
TMP_CONFIG="$TMP_BASE/agent.yaml"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_HOME" "$TMP_EDGE"

cat >"$TMP_CONFIG" <<YAML
name: Telemetry Test
codename: telemetry-test
skill_prefix: telemetry-test
mission: Validate install telemetry
voice: Direct and factual
domain: testing
edge_home: $TMP_EDGE
blog_port: 8766
onboarding_mode: true
YAML

export EDGE_REPO_DIR="$EDGE_DIR"

echo "=== install telemetry Smoke Test ==="
echo "Temp base: $TMP_BASE"
echo ""

echo "--- Test 1: edge-render emits RenderProduced for rendered artifacts ---"
python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE" "$TMP_EDGE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

edge_dir, tmp_base, tmp_edge = sys.argv[1:]
repo = Path(tmp_base) / "render-repo"
repo.mkdir(parents=True, exist_ok=True)
(repo / "example.txt.tpl").write_text("hello {{ NAME }}\n", encoding="utf-8")

os.environ["EDGE_STATE_DIR"] = tmp_edge
os.environ["EDGE_CYCLE_ID"] = "install:test-render"
os.environ["EDGE_CODENAME"] = "telemetry-test"

loader = importlib.machinery.SourceFileLoader("edge_render_mod", f"{edge_dir}/tools/edge-render")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

mod.render_all(repo, {"NAME": "world"}, dry_run=False)

shadow_log = Path(tmp_edge) / "state" / "events" / "log.jsonl"
events = [json.loads(line) for line in shadow_log.read_text(encoding="utf-8").splitlines() if line.strip()]
matches = [
    event for event in events
    if event.get("cycle_id") == "install:test-render" and event.get("type") == "RenderProduced"
]
assert matches, "expected at least one RenderProduced event"
payload = matches[-1]["payload"]
assert payload["source_template"] == "example.txt.tpl"
assert payload["residual_count"] == 0
assert matches[-1]["artifact"].endswith("example.txt")
PY
if [[ $? -eq 0 ]]; then
    pass "edge-render emits RenderProduced"
else
    fail "edge-render emits RenderProduced"
fi

echo "--- Test 2: edge-apply dry-run emits run_step lifecycle ---"
export HOME="$TMP_HOME"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="telemetry-test"
export EDGE_CYCLE_ID="install:test-apply-dry-run"
if python3 "$EDGE_DIR/tools/edge-apply" --config "$TMP_CONFIG" --dry-run --skip-venv >/dev/null; then
    :
fi
if python3 - <<'PY' "$TMP_EDGE/logs/events.jsonl"
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
run_steps = [
    event for event in events
    if event.get("type") == "run_step" and event.get("run_id") == "install:test-apply-dry-run"
]
phases = {(event.get("run_kind"), event.get("phase"), event.get("status")) for event in run_steps}
assert ("edge-install", "edge-apply", "started") in phases
assert ("edge-install", "render", "started") in phases
assert ("edge-install", "render", "completed") in phases
assert ("edge-install", "edge-apply", "completed") in phases
PY
then
    pass "edge-apply dry-run emits run_step lifecycle"
else
    fail "edge-apply dry-run emits run_step lifecycle"
fi

echo "--- Test 3: phase_identity emits InstallApplied on real materialization ---"
python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG" "$TMP_HOME" "$TMP_EDGE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

edge_dir, config_path, home_dir, edge_state = sys.argv[1:]
os.environ["HOME"] = home_dir
os.environ["EDGE_STATE_DIR"] = edge_state
os.environ["EDGE_CODENAME"] = "telemetry-test"
os.environ["EDGE_CYCLE_ID"] = "install:test-phase-identity"

loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

cfg = mod.load_config(Path(config_path))
assert mod.phase_identity(cfg, dry_run=False) is True

shadow_log = Path(edge_state) / "state" / "events" / "log.jsonl"
events = [json.loads(line) for line in shadow_log.read_text(encoding="utf-8").splitlines() if line.strip()]
matches = [
    event for event in events
    if event.get("cycle_id") == "install:test-phase-identity" and event.get("type") == "InstallApplied"
]
assert matches, "expected InstallApplied events from phase_identity"
assert any(event["artifact"].endswith("/.claude/CLAUDE.md") for event in matches)
assert any(event["payload"].get("phase") == "identity" for event in matches)
PY
if [[ $? -eq 0 ]]; then
    pass "phase_identity emits InstallApplied"
else
    fail "phase_identity emits InstallApplied"
fi

echo "--- Test 4: edge-doctor emits InstallCheckObserved even on failing install ---"
export HOME="$TMP_HOME"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="telemetry-test"
export EDGE_CYCLE_ID="install:test-doctor"
set +e
python3 "$EDGE_DIR/tools/edge-doctor" --config "$TMP_CONFIG" >/dev/null
DOCTOR_STATUS=$?
set -e
if python3 - <<'PY' "$TMP_EDGE/state/events/log.jsonl"
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
checks = [
    event for event in events
    if event.get("cycle_id") == "install:test-doctor" and event.get("type") == "InstallCheckObserved"
]
assert checks, "expected InstallCheckObserved events from edge-doctor"
assert any(event["payload"].get("check_id") == "dir:edge-home" for event in checks)
assert any(event["payload"].get("status") in {"warn", "fail"} for event in checks)
PY
then
    pass "edge-doctor emits InstallCheckObserved (exit=$DOCTOR_STATUS)"
else
    fail "edge-doctor emits InstallCheckObserved"
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
