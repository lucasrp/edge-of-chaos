#!/usr/bin/env bash
# Integration tests for Ops Console (US-001 through US-012)
# Uses Flask test client via Python — no server needed.

set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BLOG_DIR="$EDGE_DIR/blog"
export EDGE_REPO_DIR="$EDGE_DIR"
VENV_PY="${EDGE_BLOG_VENV:-$BLOG_DIR/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi
PASS=0
FAIL=0
ERRORS=""

pass_test() { PASS=$((PASS + 1)); echo "  ✓ $1"; }
fail_test() { FAIL=$((FAIL + 1)); ERRORS="$ERRORS\n  ✗ $1"; echo "  ✗ $1"; }

echo "=== Ops Console Integration Tests ==="
echo ""

# -------------------------------------------------------------------
# Test 1: Python imports for blueprints
# -------------------------------------------------------------------
echo "[1/3] Blueprint imports"

if cd "$EDGE_DIR" && "$VENV_PY" -c "from blog.api_dashboard import dashboard_bp" >/dev/null 2>&1; then
    pass_test "import blog.api_dashboard.dashboard_bp"
else
    fail_test "import blog.api_dashboard.dashboard_bp"
fi

if cd "$EDGE_DIR" && "$VENV_PY" -c "from blog.api_actions import actions_bp" >/dev/null 2>&1; then
    pass_test "import blog.api_actions.actions_bp"
else
    fail_test "import blog.api_actions.actions_bp"
fi

if cd "$EDGE_DIR" && "$VENV_PY" -c "from blog.services import load_json_safe" >/dev/null 2>&1; then
    pass_test "import blog.services"
else
    fail_test "import blog.services"
fi

# -------------------------------------------------------------------
# Test 2: Flask app starts
# -------------------------------------------------------------------
echo ""
echo "[2/3] Flask app starts"

if cd "$EDGE_DIR" && "$VENV_PY" - <<'PYEOF' "$EDGE_DIR" >/dev/null 2>&1
import os
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

print("OK")
PYEOF
then
    pass_test "Flask app creates successfully"
else
    fail_test "Flask app creates successfully"
fi

# -------------------------------------------------------------------
# Test 3: HTTP endpoint tests via test client
# -------------------------------------------------------------------
echo ""
echo "[3/3] HTTP endpoint tests"

cd "$EDGE_DIR"

TMPTEST=$(mktemp /tmp/test_ops_XXXXXX.py)
cat > "$TMPTEST" <<'PYEOF'
import sys, os

edge_dir = sys.argv[1]
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

client = app.test_client()

def check(name, response, expect_status=200):
    ok = response.status_code == expect_status
    mark = "PASS" if ok else "FAIL"
    print(f'{mark}|{name}|{response.status_code}|{expect_status}')

def check_redirect(name, response, expect_location, expect_status=302):
    ok = response.status_code == expect_status and response.headers.get("Location") == expect_location
    mark = "PASS" if ok else "FAIL"
    got = f'{response.status_code} {response.headers.get("Location")}'
    expected = f'{expect_status} {expect_location}'
    print(f'{mark}|{name}|{got}|{expected}')

check("GET /api/dashboard/overview", client.get("/api/dashboard/overview"))
check("GET /api/dashboard/alerts", client.get("/api/dashboard/alerts"))
check("GET /api/dashboard/pipeline", client.get("/api/dashboard/pipeline"))
check("GET /api/dashboard/runtime", client.get("/api/dashboard/runtime"))
check("GET /api/dashboard/epistemics", client.get("/api/dashboard/epistemics"))
check("GET /api/dashboard/interventions", client.get("/api/dashboard/interventions"))
check("GET /api/dashboard/hotspots", client.get("/api/dashboard/hotspots"))
check("GET /api/dashboard/corpus", client.get("/api/dashboard/corpus"))
check_redirect("GET / -> /dashboard", client.get("/"), "/dashboard")
check("GET /blog", client.get("/blog"))

r = client.post("/api/tasks/TASK-20260309-001/action",
                json={"action": "note", "value": "integration-test-ping"},
                content_type="application/json")
check("POST /api/tasks/TASK-20260309-001/action", r)

r = client.post("/api/heartbeat/trigger", content_type="application/json")
ok = r.status_code in (200, 429)
mark = "PASS" if ok else "FAIL"
print(f'{mark}|POST /api/heartbeat/trigger|{r.status_code}|200 or 429')

check("GET /partials/status-strip", client.get("/partials/status-strip"))
check("GET /partials/runtime", client.get("/partials/runtime"))
check("GET /partials/epistemics", client.get("/partials/epistemics"))
check("GET /partials/interventions", client.get("/partials/interventions"))
check("GET /dashboard", client.get("/dashboard"))
PYEOF

while IFS='|' read -r mark name status expected; do
    if [ "$mark" = "PASS" ]; then
        pass_test "$name → $status"
    else
        fail_test "$name → got $status, expected $expected"
    fi
done < <("$VENV_PY" "$TMPTEST" "$EDGE_DIR" 2>/dev/null)

rm -f "$TMPTEST"

# -------------------------------------------------------------------
# Revert test side effects
# -------------------------------------------------------------------
cd "$EDGE_DIR"
cleanup_path() {
    local path="$1"
    if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
        git checkout -- "$path" 2>/dev/null || true
    else
        rm -f "$path" 2>/dev/null || true
    fi
}

cleanup_path "state/tasks.snapshot.json"
cleanup_path "state/heartbeat-trigger.json"
cleanup_path "logs/operator-actions.jsonl"
rm -f search/edge-memory.db search/edge-memory.db-shm search/edge-memory.db-wal 2>/dev/null || true

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""
echo "================================"
echo "Total: $((PASS + FAIL)) tests"
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Failures:"
    echo -e "$ERRORS"
    exit 1
else
    echo ""
    echo "All tests pass ✓"
    exit 0
fi
