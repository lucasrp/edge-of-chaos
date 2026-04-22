#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-cap-invoke-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_BIN="$TMP_BASE/bin"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/libexec/captest" "$TMP_BIN"

cat >"$TMP_BIN/edge-search" <<'EOF'
#!/usr/bin/env bash
printf 'SEARCH:%s\n' "$*"
EOF
cat >"$TMP_BIN/edge-sources" <<'EOF'
#!/usr/bin/env bash
printf 'SOURCES:%s\n' "$*"
EOF
cat >"$TMP_BIN/edge-workflows" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "status" ]]; then
  echo '{"summary":{"workflow_total":1,"cited_total":1,"broken_total":0,"stale_total":0,"top_used":[],"top_broken":[]},"workflows":[]}'
else
  printf 'WF:%s\n' "$*"
fi
EOF
cat >"$TMP_BIN/git" <<'EOF'
#!/usr/bin/env bash
printf 'git version test\n'
EOF
chmod +x "$TMP_BIN/edge-search" "$TMP_BIN/edge-sources" "$TMP_BIN/edge-workflows" "$TMP_BIN/git"

cat >"$TMP_STATE/state/sources-manifest.yaml" <<'YAML'
sources:
  - name: arxiv
    description: Academic preprints
    status: active
YAML
cat >"$TMP_STATE/libexec/captest/arxiv" <<'EOF'
#!/usr/bin/env bash
printf '{"query":"%s","source":"arxiv"}\n' "${2:-}"
EOF
chmod +x "$TMP_STATE/libexec/captest/arxiv"
cat >"$TMP_STATE/libexec/captest/arxiv.meta.yaml" <<'YAML'
name: arxiv
description: Academic preprints
YAML

echo "=== edge-cap invoke/probe Smoke Test ==="

SEARCH_OUT=$(env PATH="$TMP_BIN:/bin" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="captest" \
  /usr/bin/python3 "$EDGE_DIR/tools/edge-cap" invoke search.corpus -- --type workflow -k 2 "prompt recall")
if grep -q 'SEARCH:--type workflow -k 2 prompt recall' <<<"$SEARCH_OUT"; then
  pass "invoke forwards args to static capability"
else
  fail "invoke forwards args to static capability"
fi

PRIM_OUT=$(env PATH="$TMP_BIN:/bin" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="captest" \
  /usr/bin/python3 "$EDGE_DIR/tools/edge-cap" invoke source.arxiv -- --query transformers)
if grep -q '"source":"arxiv"' <<<"$PRIM_OUT"; then
  pass "invoke runs primitive capability"
else
  fail "invoke runs primitive capability"
fi

if env PATH="$TMP_BIN:/bin" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="captest" \
  /usr/bin/python3 "$EDGE_DIR/tools/edge-cap" probe repo.status >/dev/null; then
  pass "probe runs static capability probe"
else
  fail "probe runs static capability probe"
fi

if python3 - <<'PY' "$TMP_STATE/state/events/log.jsonl"
import json, sys
from pathlib import Path
events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
types = {(event.get("type"), (event.get("payload") or {}).get("capability")) for event in events}
assert ("CapabilityInvocationObserved", "search.corpus") in types
assert ("CapabilityInvocationObserved", "source.arxiv") in types
assert ("CapabilityProbeCompleted", "repo.status") in types
PY
then
  pass "capability telemetry is emitted"
else
  fail "capability telemetry is emitted"
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
