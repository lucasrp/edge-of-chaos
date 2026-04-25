#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-blog-publish-XXXXXX)"
TMP_RUNTIME="$TMP_BASE/runtime"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_RUNTIME/config" "$TMP_RUNTIME/blog" "$TMP_RUNTIME/logs" "$TMP_RUNTIME/state" "$TMP_HOME"

cat >"$TMP_RUNTIME/config/branding.yaml" <<'YAML'
agent_name: "drucker"
agent_bio: "test agent"
org_name: "OpenAI"
org_short: "OA"
logo_filename: "logo.svg"
css_var_prefix: "brand"
colors:
  primary: "#2b6cb0"
blog:
  port: 8766
  host: "127.0.0.1"
  auth_enabled: false
  auth_user: ""
  auth_pass: ""
edge_dir: ""
memory_project_dir: ""
skill_prefix: "dru"
YAML

echo "=== blog-publish Missing Codename Smoke Test ==="
echo "Temp runtime: $TMP_RUNTIME"
echo ""

echo "--- Test 1: paths.sh survives missing codename under pipefail ---"
if OUTPUT=$(env -u EDGE_STATE_DIR -u EDGE_HOME -u EDGE_CODENAME -u EDGE_INSTANCE HOME="$TMP_HOME" EDGE_REPO_DIR="$TMP_RUNTIME" bash -lc "set -euo pipefail; source \"$EDGE_DIR/config/paths.sh\"; printf '%s\n%s\n' \"\$EDGE_INSTANCE\" \"\$LIBEXEC_DIR\"" 2>&1); then
    if python3 - <<'PY' "$OUTPUT" "$TMP_RUNTIME"
import pathlib
import sys

lines = sys.argv[1].splitlines()
runtime = pathlib.Path(sys.argv[2])

assert lines[0] == "dru"
assert lines[1] == str(runtime / "libexec" / "dru")
PY
    then
        pass "paths.sh falls back to skill_prefix when codename is absent"
    else
        fail "paths.sh falls back to skill_prefix when codename is absent"
    fi
else
    fail "paths.sh falls back to skill_prefix when codename is absent"
fi

echo "--- Test 2: blog-publish no longer aborts silently without codename ---"
ENTRY_PATH="$TMP_BASE/issue-302-smoke.md"
cat >"$ENTRY_PATH" <<'EOF'
---
title: "Issue 302 Smoke"
date: 2026-04-22
tags: [note]
claims:
  - "blog publish should tolerate missing codename in branding"
threads: [issue-302]
keywords: [blog-publish, branding, codename]
report: reports/issue-302.html
---

This smoke test entry exists only to prove that publication reaches the
regular pipeline instead of exiting silently while sourcing config/paths.sh.
EOF

set +e
OUTPUT=$(env -u EDGE_STATE_DIR -u EDGE_HOME -u EDGE_CODENAME -u EDGE_INSTANCE HOME="$TMP_HOME" EDGE_REPO_DIR="$TMP_RUNTIME" CALLED_FROM_CONSOLIDAR_ESTADO=1 bash "$EDGE_DIR/blog/blog-publish.sh" "$ENTRY_PATH" 2>&1)
STATUS=$?
set -e

if python3 - <<'PY' "$STATUS" "$OUTPUT" "$TMP_RUNTIME/blog/changelog.md" "$TMP_RUNTIME/blog/entries/issue-302-smoke.md"
import pathlib
import sys

status = int(sys.argv[1])
output = sys.argv[2]
changelog = pathlib.Path(sys.argv[3])
entry = pathlib.Path(sys.argv[4])

assert status == 1
assert "=== blog-publish: issue-302-smoke ===" in output
assert "[3/5] Updating changelog..." in output
assert "Publish verification failed" in output
assert entry.exists()
assert changelog.exists()
assert "Issue 302 Smoke" in changelog.read_text(encoding="utf-8")
PY
then
    pass "blog-publish reaches the normal publish flow without codename"
else
    echo "$OUTPUT"
    fail "blog-publish reaches the normal publish flow without codename"
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
