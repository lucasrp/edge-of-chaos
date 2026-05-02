#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-self-healing-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_LIBEXEC="$TMP_STATE/libexec/self-healing-test"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_LIBEXEC"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="self-healing-test"

cat >"$TMP_STATE/state/sources-manifest.yaml" <<YAML
version: 1
sources:
  - name: exa
    description: Web search
    status: active
    meta_path: "$TMP_LIBEXEC/exa.meta.yaml"
    binary_path: "$TMP_LIBEXEC/exa"
    operations: [search]
YAML

cat >"$TMP_LIBEXEC/exa.meta.yaml" <<'YAML'
name: exa
description: Web search
status: active
operations:
  - name: search
    status: active
YAML

cat >"$TMP_LIBEXEC/exa" <<'SH'
#!/usr/bin/env bash
printf '{"ok": true, "results": []}\n'
SH
chmod +x "$TMP_LIBEXEC/exa"

cat >"$TMP_STATE/state/events/log.jsonl" <<JSONL
{"ts":"2026-05-02T20:00:00+00:00","type":"PrimitiveProbeCompleted","actor":"test","payload":{"source":"exa","ok":false,"exit_code":1},"prev_hash":"sha256:root"}
JSONL

TOOL="$EDGE_DIR/tools/edge-self-healing"
STATUS_TOOL="$EDGE_DIR/tools/edge-primitives"

echo "=== edge-self-healing Smoke Test ==="
echo "Temp state: $TMP_STATE"
echo ""

echo "--- Test 1: broken primitive is reprobed and recovered ---"
if python3 - <<'PY' "$TOOL" "$STATUS_TOOL"
import json
import subprocess
import sys

tool, status_tool = sys.argv[1:]
before = json.loads(subprocess.run([status_tool, "status", "--json"], capture_output=True, text=True, check=True).stdout)
rows = {row["name"]: row for row in before["sources"]}
assert rows["exa"]["effective_status"] == "broken"

payload = json.loads(subprocess.run([tool, "--json"], capture_output=True, text=True, check=True).stdout)
assert payload["ok"] is True
assert payload["summary"]["broken_total"] == 1
assert payload["summary"]["recovered_total"] == 1
assert payload["summary"]["needs_llm_total"] == 0
assert payload["actions"][0]["action"] == "reprobe_success"

after = json.loads(subprocess.run([status_tool, "status", "--json"], capture_output=True, text=True, check=True).stdout)
rows = {row["name"]: row for row in after["sources"]}
assert rows["exa"]["effective_status"] == "probed"
PY
then
    pass "broken primitive is reprobed and recovered"
else
    fail "broken primitive is reprobed and recovered"
fi

echo "--- Test 2: self-healing emits telemetry facts ---"
if python3 - <<'PY' "$TMP_STATE/state/events/log.jsonl" "$TMP_STATE/logs/events.jsonl"
import json
import sys
from pathlib import Path

shadow = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
typed = [json.loads(line) for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if line.strip()]
assert any(row.get("type") == "PrimitiveSelfHealingCompleted" for row in shadow)
assert any(row.get("type") == "self_healing" and row.get("action") == "reprobe_success" for row in typed)
PY
then
    pass "self-healing emits telemetry facts"
else
    fail "self-healing emits telemetry facts"
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
