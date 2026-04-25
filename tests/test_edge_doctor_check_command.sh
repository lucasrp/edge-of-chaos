#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP=$(mktemp -d /tmp/edge-doctor-XXXXXX)
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== edge-doctor check_command (issue #376) ==="

mkdir -p "$TMP/home/.local/bin"
cat >"$TMP/home/.local/bin/edge-runner" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$TMP/home/.local/bin/edge-runner"

run_check() {
    local home="$1"
    local extra_path="$2"
    HOME="$home" PATH="$extra_path:/usr/bin:/bin" python3 - <<PY "$EDGE_DIR" 2>&1
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "tools" / "_shared"))
import telemetry
telemetry.log_install_check = lambda *a, **kw: None  # silence

import importlib.util
from importlib.machinery import SourceFileLoader
loader = SourceFileLoader("edge_doctor", str(Path(sys.argv[1]) / "tools" / "edge-doctor"))
spec = importlib.util.spec_from_loader("edge_doctor", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

mod.CHECKS_PASSED = 0
mod.CHECKS_WARNED = 0
mod.CHECKS_FAILED = 0
mod.check_command("edge-runner", "Edge runner CLI")
print(f"PASSED={mod.CHECKS_PASSED} WARNED={mod.CHECKS_WARNED} FAILED={mod.CHECKS_FAILED}")
PY
}

echo "--- Test 1: edge-runner on PATH → ok ---"
out=$(run_check "$TMP/home" "$TMP/home/.local/bin")
if echo "$out" | grep -q "PASSED=1 WARNED=0 FAILED=0"; then
    pass "PATH hit increments PASSED, no warn/fail"
else
    fail "expected PASSED=1, got: $out"
fi

echo "--- Test 2: edge-runner only at ~/.local/bin (PATH stale) → warn, not fail ---"
out=$(run_check "$TMP/home" "/nonexistent")
if echo "$out" | grep -q "PASSED=0 WARNED=1 FAILED=0"; then
    pass "stale PATH but binary present → WARNED, not FAILED"
else
    fail "expected WARNED=1, got: $out"
fi
if echo "$out" | grep -q "source ~/.edge-env"; then
    pass "warn message tells user to source ~/.edge-env"
else
    fail "warn message missing source hint: $out"
fi

echo "--- Test 3: edge-runner truly missing → fail ---"
out=$(run_check "$TMP/empty-home" "/nonexistent")
if echo "$out" | grep -q "PASSED=0 WARNED=0 FAILED=1"; then
    pass "binary genuinely absent → FAILED"
else
    fail "expected FAILED=1, got: $out"
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
