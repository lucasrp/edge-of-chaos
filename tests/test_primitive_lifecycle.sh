#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-primitive-lifecycle-XXXXXX)"
TMP_EDGE="$TMP_BASE/agent"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="telemetry-test"

TOOL="$EDGE_DIR/tools/edge-primitive-lifecycle"
SHADOW_LOG="$TMP_EDGE/state/events/log.jsonl"
MANIFEST="$TMP_EDGE/state/sources-manifest.yaml"
LIBEXEC_DIR="$TMP_EDGE/libexec/telemetry-test"

echo "=== primitive lifecycle Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: missing emits PrimitiveMissingObserved ---"
EDGE_CYCLE_ID="primitive:test-missing" "$TOOL" missing overleaf --operation search >/dev/null
if python3 - <<'PY' "$SHADOW_LOG"
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
matches = [
    event for event in events
    if event.get("cycle_id") == "primitive:test-missing" and event.get("type") == "PrimitiveMissingObserved"
]
assert matches
payload = matches[-1]["payload"]
assert payload["source"] == "overleaf"
assert payload["operation"] == "search"
assert payload["exit_code"] == 127
PY
then
    pass "missing emits PrimitiveMissingObserved"
else
    fail "missing emits PrimitiveMissingObserved"
fi

echo "--- Test 2: contract writes meta + manifest ---"
EDGE_CYCLE_ID="primitive:test-contract" "$TOOL" contract overleaf \
    --description "Read LaTeX projects via git clone" \
    --operation search \
    --operation write >/dev/null
if python3 - <<'PY' "$SHADOW_LOG" "$MANIFEST" "$LIBEXEC_DIR"
import json
import sys
from pathlib import Path
import yaml

shadow_log, manifest_path, libexec_dir = sys.argv[1:]
meta_path = Path(libexec_dir) / "overleaf.meta.yaml"
assert meta_path.exists()
manifest = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
entry = next(item for item in manifest["sources"] if item["name"] == "overleaf")
assert entry["status"] == "contract-only"
assert entry["meta_path"] == str(meta_path)
events = [json.loads(line) for line in Path(shadow_log).read_text(encoding="utf-8").splitlines() if line.strip()]
assert any(event.get("cycle_id") == "primitive:test-contract" and event.get("type") == "PrimitiveContractWritten" for event in events)
assert any(event.get("cycle_id") == "primitive:test-contract" and event.get("type") == "PrimitiveManifestUpdated" for event in events)
PY
then
    pass "contract writes meta + manifest"
else
    fail "contract writes meta + manifest"
fi

echo "--- Test 3: materialize updates active manifest entry ---"
mkdir -p "$LIBEXEC_DIR"
cat >"$LIBEXEC_DIR/overleaf" <<'SH'
#!/usr/bin/env bash
printf '{"ok": true, "results": []}\n'
SH
chmod +x "$LIBEXEC_DIR/overleaf"
EDGE_CYCLE_ID="primitive:test-materialize" "$TOOL" materialize overleaf --ensure-executable >/dev/null
if python3 - <<'PY' "$SHADOW_LOG" "$MANIFEST" "$LIBEXEC_DIR/overleaf"
import json
import sys
from pathlib import Path
import yaml

shadow_log, manifest_path, binary_path = sys.argv[1:]
manifest = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
entry = next(item for item in manifest["sources"] if item["name"] == "overleaf")
assert entry["status"] == "active"
assert entry["binary_path"] == binary_path
events = [json.loads(line) for line in Path(shadow_log).read_text(encoding="utf-8").splitlines() if line.strip()]
assert any(event.get("cycle_id") == "primitive:test-materialize" and event.get("type") == "PrimitiveMaterialized" for event in events)
PY
then
    pass "materialize updates active manifest entry"
else
    fail "materialize updates active manifest entry"
fi

echo "--- Test 4: probe success emits PrimitiveProbeCompleted ---"
EDGE_CYCLE_ID="primitive:test-probe-ok" "$TOOL" probe overleaf --operation search --command "$LIBEXEC_DIR/overleaf" >/dev/null
if python3 - <<'PY' "$SHADOW_LOG"
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
matches = [
    event for event in events
    if event.get("cycle_id") == "primitive:test-probe-ok" and event.get("type") == "PrimitiveProbeCompleted"
]
assert matches
payload = matches[-1]["payload"]
assert payload["source"] == "overleaf"
assert payload["exit_code"] == 0
assert payload["ok"] is True
PY
then
    pass "probe success emits PrimitiveProbeCompleted"
else
    fail "probe success emits PrimitiveProbeCompleted"
fi

echo "--- Test 5: probe exit 77 emits PrimitiveOperationMissingObserved ---"
cat >"$LIBEXEC_DIR/overleaf-partial" <<'SH'
#!/usr/bin/env bash
echo "write operation not implemented yet" >&2
exit 77
SH
chmod +x "$LIBEXEC_DIR/overleaf-partial"
set +e
EDGE_CYCLE_ID="primitive:test-probe-77" "$TOOL" probe overleaf-partial --operation write --command "$LIBEXEC_DIR/overleaf-partial" >/dev/null
STATUS=$?
set -e
if python3 - <<'PY' "$SHADOW_LOG" "$STATUS"
import json
import sys
from pathlib import Path

shadow_log, status = sys.argv[1:]
assert int(status) == 77
events = [json.loads(line) for line in Path(shadow_log).read_text(encoding="utf-8").splitlines() if line.strip()]
assert any(event.get("cycle_id") == "primitive:test-probe-77" and event.get("type") == "PrimitiveProbeCompleted" and event["payload"]["exit_code"] == 77 for event in events)
assert any(event.get("cycle_id") == "primitive:test-probe-77" and event.get("type") == "PrimitiveOperationMissingObserved" for event in events)
PY
then
    pass "probe exit 77 emits PrimitiveOperationMissingObserved"
else
    fail "probe exit 77 emits PrimitiveOperationMissingObserved"
fi

echo "--- Test 6: probe command preserves leading-dash arguments ---"
cat >"$LIBEXEC_DIR/probe-args" <<'SH'
#!/usr/bin/env bash
if [ "$1" = "-f" ] && [ "$2" = "--max-time" ] && [ "$3" = "10" ]; then
  exit 0
fi
exit 64
SH
chmod +x "$LIBEXEC_DIR/probe-args"
EDGE_CYCLE_ID="primitive:test-probe-leading-dash" "$TOOL" probe curl-like --operation reachability --command "$LIBEXEC_DIR/probe-args" -f --max-time 10 >/dev/null
if python3 - <<'PY' "$SHADOW_LOG"
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
matches = [
    event for event in events
    if event.get("cycle_id") == "primitive:test-probe-leading-dash" and event.get("type") == "PrimitiveProbeCompleted"
]
assert matches
payload = matches[-1]["payload"]
assert payload["source"] == "curl-like"
assert payload["exit_code"] == 0
assert payload["ok"] is True
assert payload["command"][-3:] == ["-f", "--max-time", "10"]
PY
then
    pass "probe command preserves leading-dash arguments"
else
    fail "probe command preserves leading-dash arguments"
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
