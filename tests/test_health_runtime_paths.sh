#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-health-paths-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_STATE="$TMP_BASE/state"
TMP_BIN="$TMP_BASE/bin"
TMP_REPO="$TMP_BASE/heartbeat-repo"
TMP_STATE_HEARTBEAT="$TMP_BASE/heartbeat-state"
TMP_INSTALL="$TMP_BASE/materialized-install"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_HOME" "$TMP_STATE" "$TMP_BIN" "$TMP_REPO/config" "$TMP_REPO/tools" "$TMP_REPO/bin" "$TMP_STATE_HEARTBEAT" "$TMP_INSTALL"

echo "=== health/heartbeat path split Smoke Test ==="

echo "--- Test 1: survival-lib derives HEALTH_DIR from EDGE_STATE_DIR ---"
if OUTPUT=$(env HOME="$TMP_HOME" EDGE_DIR="$EDGE_DIR" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" bash -lc 'source "$EDGE_DIR/bin/survival-lib.sh"; printf "%s\n%s\n%s\n" "$HEALTH_DIR" "$CONFIG_FILE" "$RAW_DIR"' 2>/dev/null); then
  mapfile -t lines <<<"$OUTPUT"
  if [[ "${lines[0]}" == "$TMP_STATE/health" ]] && [[ "${lines[1]}" == "$TMP_STATE/health/config.yaml" ]] && [[ "${lines[2]}" == "$TMP_STATE/health/raw" ]]; then
    pass "survival-lib uses state-root health paths"
  else
    fail "survival-lib health paths wrong: ${OUTPUT//$'\n'/ | }"
  fi
else
  fail "survival-lib could not be sourced"
fi

echo "--- Test 2: check-infra uses state sqlite/meta paths ---"
mkdir -p "$TMP_STATE/health" "$TMP_STATE/meta-reports" "$TMP_STATE/search"
printf 'meta\n' > "$TMP_STATE/meta-reports/test-meta.md"
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$TMP_STATE/search/edge-memory.db" "create table if not exists t(x integer); insert into t values (1);" >/dev/null
fi
if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" bash "$EDGE_DIR/bin/check-infra.sh" >/dev/null 2>&1; then
  consolidate_status=$(jq -r '.status' "$TMP_STATE/health/raw/consolidate.json" 2>/dev/null || echo "missing")
  if [[ "$consolidate_status" == "ok" || "$consolidate_status" == "degraded" || "$consolidate_status" == "fail" ]]; then
    pass "check-infra reads meta-reports from state root"
  else
    fail "check-infra consolidate status unexpected: $consolidate_status"
  fi

  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite_status=$(jq -r '.status' "$TMP_STATE/health/raw/sqlite.json" 2>/dev/null || echo "missing")
    if [[ "$sqlite_status" == "ok" || "$sqlite_status" == "degraded" ]]; then
      pass "check-infra reads sqlite db from state root"
    else
      fail "check-infra sqlite status unexpected: $sqlite_status"
    fi
  else
    pass "sqlite3 unavailable; sqlite path assertion skipped"
  fi

  cat >"$TMP_INSTALL/agent.yaml" <<'YAML'
codename: materialized-test
YAML
  if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" REPO_ROOT="$TMP_INSTALL" bash "$EDGE_DIR/bin/check-infra.sh" >/dev/null 2>&1; then
    git_status=$(jq -r '.status' "$TMP_STATE/health/raw/git.json" 2>/dev/null || echo "missing")
  else
    git_status="missing"
  fi
  if [[ "$git_status" == "unknown" ]]; then
    pass "check-infra treats materialized installs without .git as unknown"
  else
    fail "check-infra git status unexpected: $git_status"
  fi
else
  fail "check-infra execution failed"
fi

echo "--- Test 3: check-content truncates oversized glob scans ---"
mkdir -p "$TMP_STATE/content/blog" "$TMP_STATE/health" "$TMP_STATE/threads"
for i in 1 2 3 4 5; do
  printf -- '---\ntitle: Entry %s\n---\n' "$i" > "$TMP_STATE/content/blog/entry-$i.md"
done
cat >"$TMP_STATE/health/config.yaml" <<YAML
monitored_files:
  - path: "$TMP_STATE/content/blog"
    glob: "*.md"
    category: blog
    threshold_days: 9999
monitored_skills: []
YAML

if env HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CONTENT_MAX_FILES=3 bash "$EDGE_DIR/bin/check-content.sh" >/dev/null 2>&1; then
  content_status="$(jq -r '.status' "$TMP_STATE/health/raw/content.json" 2>/dev/null || echo "missing")"
  content_detail="$(jq -r '.detail' "$TMP_STATE/health/raw/content.json" 2>/dev/null || echo "")"
  if [[ "$content_status" == "degraded" ]] && [[ "$content_detail" == *"scan_truncated=3/5 limit=3"* ]]; then
    pass "check-content reports bounded scans instead of walking every file"
  else
    fail "check-content truncation detail unexpected: status=$content_status detail=$content_detail"
  fi
else
  fail "check-content execution failed"
fi

echo "--- Test 4: edge-repair reindexes state paths ---"
mkdir -p "$TMP_STATE/blog/entries" "$TMP_STATE/reports" "$TMP_STATE/notes"
cat >"$TMP_STATE/health/current.json" <<'JSON'
{
  "infra": {
    "blog": {"status": "ok"},
    "sqlite": {"status": "ok"},
    "index": {"status": "fail"},
    "git": {"status": "ok"},
    "mini_repos": {"status": "ok"}
  }
}
JSON
cat >"$TMP_BIN/edge-index" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" > "$TMP_BASE/edge-index.args"
exit 0
EOF
chmod +x "$TMP_BIN/edge-index"

if env PATH="$TMP_BIN:/usr/bin:/bin" HOME="$TMP_HOME" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" bash "$EDGE_DIR/bin/edge-repair.sh" >/dev/null 2>&1; then
  expected="$TMP_STATE/blog/entries/ $TMP_STATE/reports/ $TMP_STATE/notes/ $TMP_STATE/topics/"
  actual="$(cat "$TMP_BASE/edge-index.args" 2>/dev/null || true)"
  if [[ "$actual" == "$expected" ]]; then
    pass "edge-repair reindexes state-root content"
  else
    fail "edge-repair used wrong edge-index args: $actual"
  fi
else
  fail "edge-repair execution failed"
fi

echo "--- Test 5: heartbeat-preflight reads health from state root ---"
cp "$EDGE_DIR/tools/heartbeat-preflight.sh" "$TMP_REPO/tools/heartbeat-preflight.sh"
cp "$EDGE_DIR/config/paths.sh" "$TMP_REPO/config/paths.sh"
cat >"$TMP_REPO/bin/edge-check.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMP_REPO/bin/edge-check.sh" "$TMP_REPO/tools/heartbeat-preflight.sh"
cat >"$TMP_REPO/config/branding.yaml" <<YAML
codename: hbtest
skill_prefix: hbtest
edge_state_dir: "$TMP_STATE_HEARTBEAT"
blog:
  port: 9
  auth_enabled: false
YAML
mkdir -p "$TMP_STATE_HEARTBEAT/health" "$TMP_STATE_HEARTBEAT/blog/entries" "$TMP_STATE_HEARTBEAT/threads" "$TMP_STATE_HEARTBEAT/state" "$TMP_STATE_HEARTBEAT/libexec/hbtest"
cat >"$TMP_STATE_HEARTBEAT/health/current.json" <<'JSON'
{"status":"degraded","score":80}
JSON

if OUTPUT=$(env PATH="/usr/bin:/bin" HOME="$TMP_HOME" EDGE_REPO_DIR="$TMP_REPO" EDGE_STATE_DIR="$TMP_STATE_HEARTBEAT" bash "$TMP_REPO/tools/heartbeat-preflight.sh" 2>/dev/null); then
  if grep -q 'HEALTH:DEGRADED score=80' <<<"$OUTPUT"; then
    pass "heartbeat-preflight reads health snapshot from state root"
  else
    fail "heartbeat-preflight did not emit health signal from state root"
  fi
else
  fail "heartbeat-preflight execution failed"
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
