#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-primitives-status-XXXXXX)"
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
name: Primitive Status Test
codename: primitive-status-test
skill_prefix: primitive-status-test
mission: Validate primitive status read model
voice: Direct and factual
domain: testing
edge_home: $TMP_EDGE
blog_port: 8766
onboarding_mode: true
sources:
  - name: arxiv
    description: Recent preprints
  - name: exa
    description: Web search
YAML

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="primitive-status-test"

STATUS_TOOL="$EDGE_DIR/tools/edge-primitives"
LIFECYCLE_TOOL="$EDGE_DIR/tools/edge-primitive-lifecycle"
STATUS_FILE="$TMP_EDGE/state/primitives-status.json"
MANIFEST="$TMP_EDGE/state/sources-manifest.yaml"
LIBEXEC_DIR="$TMP_EDGE/libexec/primitive-status-test"

echo "=== primitives status Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: phase_seed seeds manifest from declared sources ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir, config_path = sys.argv[1:]
loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
cfg = mod.load_config(Path(config_path))
assert mod.phase_dirs(cfg, dry_run=False) is True
assert mod.phase_seed(cfg, dry_run=False) is True
PY
then
    if python3 - <<'PY' "$MANIFEST"
import sys
from pathlib import Path
import yaml

manifest = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
entries = {item["name"]: item for item in manifest["sources"]}
assert set(entries) == {"arxiv", "exa"}
assert entries["arxiv"]["status"] == "declared"
assert entries["exa"]["status"] == "declared"
PY
    then
        pass "phase_seed seeds declared sources into manifest"
    else
        fail "phase_seed seeds declared sources into manifest"
    fi
else
    fail "phase_seed seeds declared sources into manifest"
fi

echo "--- Test 2: edge-primitives status reports declared sources and writes snapshot ---"
if python3 - <<'PY' "$STATUS_TOOL" "$STATUS_FILE"
import json
import subprocess
import sys
from pathlib import Path

tool, status_file = sys.argv[1:]
result = subprocess.run([tool, "status", "--json"], capture_output=True, text=True, check=True)
payload = json.loads(result.stdout)
assert payload["summary"]["declared_total"] == 2
assert payload["summary"]["degraded_total"] == 0
rows = {row["name"]: row for row in payload["sources"]}
assert rows["arxiv"]["effective_status"] == "unknown"
assert rows["exa"]["effective_status"] == "unknown"
assert "declared_unbound" in rows["arxiv"]["problems"]
assert "declared_unbound" in rows["exa"]["problems"]
assert Path(status_file).exists()
PY
then
    pass "edge-primitives status reports declared sources"
else
    fail "edge-primitives status reports declared sources"
fi

echo "--- Test 3: lifecycle transitions update the read model ---"
mkdir -p "$LIBEXEC_DIR"
cat >"$LIBEXEC_DIR/arxiv" <<'SH'
#!/usr/bin/env bash
printf '{"ok": true, "results": []}\n'
SH
chmod +x "$LIBEXEC_DIR/arxiv"

EDGE_CYCLE_ID="primitive-status:test-contract" "$LIFECYCLE_TOOL" contract arxiv --description "Recent preprints" --operation search >/dev/null
EDGE_CYCLE_ID="primitive-status:test-materialize" "$LIFECYCLE_TOOL" materialize arxiv --ensure-executable >/dev/null
EDGE_CYCLE_ID="primitive-status:test-probe" "$LIFECYCLE_TOOL" probe arxiv --operation search --command "$LIBEXEC_DIR/arxiv" >/dev/null

if python3 - <<'PY' "$STATUS_TOOL"
import json
import subprocess
import sys

tool = sys.argv[1]
payload = json.loads(subprocess.run([tool, "status", "--json"], capture_output=True, text=True, check=True).stdout)
rows = {row["name"]: row for row in payload["sources"]}
assert payload["summary"]["probed_total"] == 1
assert payload["summary"]["degraded_total"] == 0
assert rows["arxiv"]["effective_status"] == "probed"
assert rows["exa"]["effective_status"] == "unknown"
assert rows["arxiv"]["probe_status"] == "ok"
PY
then
    pass "lifecycle transitions update status to probed"
else
    fail "lifecycle transitions update status to probed"
fi

echo "--- Test 4: missing active binary is reported as degraded ---"
rm -f "$LIBEXEC_DIR/arxiv"
if python3 - <<'PY' "$STATUS_TOOL"
import json
import subprocess
import sys

tool = sys.argv[1]
payload = json.loads(subprocess.run([tool, "status", "--json"], capture_output=True, text=True, check=True).stdout)
rows = {row["name"]: row for row in payload["sources"]}
assert payload["summary"]["degraded_total"] == 1
assert rows["arxiv"]["effective_status"] == "degraded"
assert rows["exa"]["effective_status"] == "unknown"
PY
then
    pass "status reports degraded when active binary disappears"
else
    fail "status reports degraded when active binary disappears"
fi

echo "--- Test 5: checkup probes capabilities and reports candidate actions without aborting ---"
if OUTPUT=$("$STATUS_TOOL" status --json --checkup --skill autonomy --skip-primitive-probes); then
    if python3 - <<'PY' "$OUTPUT"
import json
import sys

payload = json.loads(sys.argv[1])
checkup = payload["checkup"]
assert checkup["status"] in {"ok", "warning"}
assert checkup["capability_probe_total"] >= 1
assert checkup["candidate_action_total"] >= 1
assert "capabilities_status" in payload
assert "configured_integrations" in payload
PY
    then
        pass "checkup refreshes primitives/capabilities and emits decisions"
    else
        fail "checkup refreshes primitives/capabilities and emits decisions"
    fi
else
    fail "checkup refreshes primitives/capabilities and emits decisions"
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
