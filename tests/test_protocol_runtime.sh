#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-protocol-runtime-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
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

mkdir -p "$TMP_REPO/config" "$TMP_REPO/tools" "$TMP_STATE" "$TMP_HOME"

cat >"$TMP_REPO/config/preflight.yaml" <<'YAML'
version: 1
protocol: preflight
context_notes:
  - Watch the substrate first.
operator_notes:
  - Try the configured checks before improvising.
procedures:
  - id: health-snapshot
    kind: health.snapshot
  - id: edge-signals
    kind: signals.context
    scope: routing
    limit: 5
  - id: capability-probe
    kind: capability.probe
    capability: storage.sync
YAML

cat >"$TMP_REPO/config/postflight.yaml" <<'YAML'
version: 1
protocol: postflight
context_notes: []
operator_notes:
  - Record failures but keep the cycle moving.
procedures:
  - id: source-affordances
    kind: source_affordance.digest
  - id: pipeline-state
    kind: pipeline_state.refresh
  - id: briefing-refresh
    kind: briefing.refresh
  - id: async-inbox-response
    kind: async_inbox.respond
YAML

cat >"$TMP_REPO/config/capabilities.yaml" <<'YAML'
capabilities:
  - name: storage.sync
    kind: external_cli
    command: [echo]
    probe: [echo, ok]
    passthrough: true
    required: false
    skills: [report]
YAML

cat >"$TMP_REPO/tools/edge-primitives" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '{"summary":{},"sources":[]}'
SH
chmod +x "$TMP_REPO/tools/edge-primitives"

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="protocol-test"

echo "=== protocol runtime Smoke Test ==="
echo "Temp repo: $TMP_REPO"
echo ""

echo "--- Test 1: ensure_compiled_protocol writes compiled JSON with hashes ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE"
import json
import os
import sys
from pathlib import Path

edge_dir, state_dir = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.protocol_runtime import ensure_compiled_protocol

compiled = ensure_compiled_protocol("preflight")
assert compiled["protocol"] == "preflight"
assert compiled["source_hash"].startswith("sha256:")
assert compiled["compiled_hash"].startswith("sha256:")
compiled_path = Path(state_dir) / "state" / "runtime" / "preflight.compiled.json"
assert compiled_path.exists()
saved = json.loads(compiled_path.read_text(encoding="utf-8"))
assert saved["source_hash"] == compiled["source_hash"]
assert len(saved["procedures"]) == 3
signal_step = next(item for item in saved["procedures"] if item["kind"] == "signals.context")
assert signal_step["scope"] == "routing"
assert signal_step["limit"] == 5
PY
then
    pass "ensure_compiled_protocol writes compiled JSON with hashes"
else
    fail "ensure_compiled_protocol writes compiled JSON with hashes"
fi

echo "--- Test 2: postflight accepts source affordance and async inbox steps ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE"
import json
import sys
from pathlib import Path

edge_dir, state_dir = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.protocol_runtime import ensure_compiled_protocol

compiled = ensure_compiled_protocol("postflight")
assert compiled["protocol"] == "postflight"
kinds = [item["kind"] for item in compiled["procedures"]]
assert "source_affordance.digest" in kinds
assert "pipeline_state.refresh" in kinds
assert "async_inbox.respond" in kinds
compiled_path = Path(state_dir) / "state" / "runtime" / "postflight.compiled.json"
assert compiled_path.exists()
saved = json.loads(compiled_path.read_text(encoding="utf-8"))
assert any(item["kind"] == "source_affordance.digest" for item in saved["procedures"])
assert any(item["kind"] == "pipeline_state.refresh" for item in saved["procedures"])
assert any(item["kind"] == "async_inbox.respond" for item in saved["procedures"])
PY
then
    pass "postflight accepts source affordance and async inbox steps"
else
    fail "postflight accepts source affordance and async inbox steps"
fi

echo "--- Test 3: source edits trigger automatic recompilation on next ensure ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_REPO/config/preflight.yaml"
import sys
from pathlib import Path

edge_dir, source_path = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.protocol_runtime import ensure_compiled_protocol

first = ensure_compiled_protocol("preflight")
path = Path(source_path)
raw = path.read_text(encoding="utf-8")
path.write_text(raw.replace("health-snapshot", "health-snapshot-v2"), encoding="utf-8")
second = ensure_compiled_protocol("preflight")
assert first["source_hash"] != second["source_hash"]
assert first["compiled_hash"] != second["compiled_hash"]
PY
then
    pass "source edits trigger automatic recompilation on next ensure"
else
    fail "source edits trigger automatic recompilation on next ensure"
fi

echo "--- Test 4: unknown protocol kinds fail compilation ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_REPO/config/preflight.yaml"
import sys
from pathlib import Path

edge_dir, source_path = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.protocol_runtime import ProtocolCompileError, ensure_compiled_protocol

path = Path(source_path)
path.write_text(
    """version: 1
protocol: preflight
context_notes: []
operator_notes: []
procedures:
  - id: bad
    kind: unknown.kind
""",
    encoding="utf-8",
)
try:
    ensure_compiled_protocol("preflight")
except ProtocolCompileError:
    pass
else:
    raise AssertionError("expected ProtocolCompileError")
PY
then
    pass "unknown protocol kinds fail compilation"
else
    fail "unknown protocol kinds fail compilation"
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
