#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-web-search-policy-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
FEATURES_FILE="$EDGE_DIR/config/features.yaml"
BACKUP_FEATURES="$TMP_BASE/features.yaml.bak"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  if [[ -f "$BACKUP_FEATURES" ]]; then
    mv "$BACKUP_FEATURES" "$FEATURES_FILE"
  else
    rm -f "$FEATURES_FILE"
  fi
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE"
if [[ -f "$FEATURES_FILE" ]]; then cp "$FEATURES_FILE" "$BACKUP_FEATURES"; fi

HOOK="$EDGE_DIR/hooks/web-search-policy-guard.sh"
INPUT='{"tool_name":"WebSearch","tool_input":{"query":"edge runtime search routing"}}'

echo "=== web search policy guard Smoke Test ==="
echo ""

echo "--- Test 1: builtin web search blocked by default policy ---"
cat >"$FEATURES_FILE" <<'YAML'
search:
  builtin_web_search: false
  web_provider: exa
  web_fallback: claude_web
  exa: auto
YAML

set +e
OUTPUT=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" bash "$HOOK" <<<"$INPUT" 2>&1)
STATUS=$?
set -e

if [[ "$STATUS" -eq 2 ]] && grep -q "BLOCKED" <<<"$OUTPUT" && grep -q "edge-sources first" <<<"$OUTPUT"; then
  pass "hook blocks WebSearch when builtin policy is disabled"
else
  echo "$OUTPUT"
  fail "hook blocks WebSearch when builtin policy is disabled"
fi

echo "--- Test 2: runtime allowance unlocks temporary fallback ---"
EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.search_runtime import write_builtin_web_search_allowance

write_builtin_web_search_allowance(
    "provider_failed_or_empty",
    query="edge runtime search routing",
    provider="exa",
    source="test",
)
PY

if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" bash "$HOOK" <<<"$INPUT" >/dev/null 2>&1; then
  pass "hook allows WebSearch during active fallback window"
else
  fail "hook allows WebSearch during active fallback window"
fi

echo "--- Test 3: builtin web search true bypasses the guard ---"
rm -f "$TMP_STATE/state/runtime/web-search-fallback.json"
cat >"$FEATURES_FILE" <<'YAML'
search:
  builtin_web_search: true
  web_provider: exa
  web_fallback: claude_web
  exa: auto
YAML

if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" bash "$HOOK" <<<"$INPUT" >/dev/null 2>&1; then
  pass "hook allows WebSearch when builtin policy is enabled"
else
  fail "hook allows WebSearch when builtin policy is enabled"
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
