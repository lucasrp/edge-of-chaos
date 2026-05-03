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

mkdir -p "$TMP_REPO/config" "$TMP_REPO/tools" "$TMP_STATE/state" "$TMP_HOME"

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
  - id: source-bindings
    kind: source.bindings
  - id: asset-inventory
    kind: asset_inventory.status
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
  - name: sources.aggregate
    kind: external_cli
    command: [edge-sources]
    probe: [edge-sources, --help]
    passthrough: true
    required: true
    roles: [search, source]
    skills: [research]
  - name: storage.sync
    kind: external_cli
    command: [echo]
    probe: [echo, ok]
    passthrough: true
    required: false
    skills: [report]
YAML

cat >"$TMP_STATE/state/sources-manifest.yaml" <<'YAML'
sources:
  - name: exa
    description: Web search
    roles: [search]
    primary: true
  - name: meta
    description: Campaign state
    roles: [signals]
YAML

cat >"$TMP_REPO/tools/edge-sources" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "edge-sources $*"
SH
cat >"$TMP_REPO/tools/edge-primitives" <<'PY'
#!/usr/bin/env python3
import json
import os
from pathlib import Path

payload = {"summary": {}, "sources": []}
path = Path(os.environ["EDGE_STATE_DIR"]) / "state" / "primitives-status.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
PY
chmod +x "$TMP_REPO/tools/edge-primitives" "$TMP_REPO/tools/edge-sources"

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
assert len(saved["procedures"]) == 5
signal_step = next(item for item in saved["procedures"] if item["kind"] == "signals.context")
assert signal_step["scope"] == "routing"
assert signal_step["limit"] == 5
source_step = next(item for item in saved["procedures"] if item["kind"] == "source.bindings")
bindings = {item["source"]: item for item in source_step["source_bindings"]}
assert bindings["exa"]["binding_status"] == "present"
assert bindings["exa"]["binding_mode"] == "sources.aggregate"
assert bindings["exa"]["capability"] == "sources.aggregate"
assert bindings["meta"]["binding_status"] == "absent"
assert bindings["meta"]["warning"] == "configured_integration_without_binding"
assert any("meta: configured_integration_without_binding" in item for item in saved["warnings"])
assert saved["dependency_hashes"]
primitive_hash = saved["dependency_hashes"][str(Path(state_dir) / "state" / "primitives-status.json")]
assert primitive_hash.startswith("sha256:")
asset_hash = saved["dependency_hashes"][str(Path(state_dir) / "state" / "asset-inventory.json")]
assert asset_hash == "missing"
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

echo "--- Test 4: volatile primitive timestamps do not force recompilation ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE/state/primitives-status.json"
import json
import sys
from pathlib import Path

edge_dir, status_path = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.protocol_runtime import ensure_compiled_protocol

first = ensure_compiled_protocol("preflight")
path = Path(status_path)
payload = json.loads(path.read_text(encoding="utf-8"))
payload["generated_at"] = "2026-05-01T00:00:00+00:00"
payload.setdefault("summary", {})["generated_at"] = "2026-05-01T00:00:00+00:00"
path.write_text(json.dumps(payload), encoding="utf-8")
second = ensure_compiled_protocol("preflight")
payload["generated_at"] = "2026-05-01T00:01:00+00:00"
payload["summary"]["generated_at"] = "2026-05-01T00:01:00+00:00"
path.write_text(json.dumps(payload), encoding="utf-8")
third = ensure_compiled_protocol("preflight")
assert first["compiled_hash"] == second["compiled_hash"] == third["compiled_hash"]
PY
then
    pass "volatile primitive timestamps do not force recompilation"
else
    fail "volatile primitive timestamps do not force recompilation"
fi

echo "--- Test 5: manifest edits trigger automatic recompilation on next ensure ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE/state/sources-manifest.yaml"
import sys
from pathlib import Path

edge_dir, manifest_path = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.protocol_runtime import ensure_compiled_protocol

first = ensure_compiled_protocol("preflight")
path = Path(manifest_path)
raw = path.read_text(encoding="utf-8")
path.write_text(raw + "  - name: reddit\n    description: Community search\n    roles: [search]\n", encoding="utf-8")
second = ensure_compiled_protocol("preflight")
assert first["dependency_hashes"] != second["dependency_hashes"]
assert first["compiled_hash"] != second["compiled_hash"]
PY
then
    pass "manifest edits trigger automatic recompilation on next ensure"
else
    fail "manifest edits trigger automatic recompilation on next ensure"
fi

echo "--- Test 6: unknown protocol kinds fail compilation ---"
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
