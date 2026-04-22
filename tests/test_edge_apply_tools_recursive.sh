#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-tools-recursive-XXXXXX)"
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
name: Recursive Tools Test
codename: recursive-tools
skill_prefix: recursive-tools
mission: Validate recursive tools copy
voice: Direct and factual
domain: testing
edge_home: $TMP_EDGE
blog_port: 8766
onboarding_mode: true
YAML

echo "=== edge-apply recursive tools Smoke Test ==="

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="recursive-tools"
export EDGE_CYCLE_ID="install:test-recursive-tools"

python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG"
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
assert mod.phase_tools(cfg, dry_run=False) is True
PY

for path in \
  "$TMP_EDGE/tools/_shared/telemetry.py" \
  "$TMP_EDGE/tools/primitives/_shared/usage_log.py" \
  "$TMP_EDGE/tools/assets/logo.svg"
do
  if [[ -f "$path" ]]; then
    pass "$(realpath --relative-to="$TMP_EDGE" "$path") copied"
  else
    fail "$(realpath --relative-to="$TMP_EDGE" "$path") missing"
  fi
done

if [[ -x "$TMP_HOME/.local/bin/edge-primitives" ]]; then
  pass "top-level tool wrapper still linked"
else
  fail "top-level tool wrapper missing"
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
