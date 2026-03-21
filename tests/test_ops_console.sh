#!/usr/bin/env bash
# Integration tests for Ops Console (US-001 through US-012)
# Uses Flask test client via Python — no server needed.

set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BLOG_DIR="$EDGE_DIR/blog"
VENV_PY="$BLOG_DIR/.venv/bin/python3"
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

if cd "$BLOG_DIR" && "$VENV_PY" -c "from app import app; print('OK')" >/dev/null 2>&1; then
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

check("GET /api/dashboard/overview", client.get("/api/dashboard/overview"))
check("GET /api/dashboard/alerts", client.get("/api/dashboard/alerts"))
check("GET /api/dashboard/pipeline", client.get("/api/dashboard/pipeline"))
check("GET /api/dashboard/hotspots", client.get("/api/dashboard/hotspots"))
check("GET /api/dashboard/corpus", client.get("/api/dashboard/corpus"))

r = client.post("/api/tasks/TASK-20260309-001/action",
                json={"action": "note", "value": "integration-test-ping"},
                content_type="application/json")
check("POST /api/tasks/TASK-20260309-001/action", r)

r = client.post("/api/heartbeat/trigger", content_type="application/json")
ok = r.status_code in (200, 429)
mark = "PASS" if ok else "FAIL"
print(f'{mark}|POST /api/heartbeat/trigger|{r.status_code}|200 or 429')

check("GET /partials/status-strip", client.get("/partials/status-strip"))
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
git checkout -- state/tasks.snapshot.json state/tasks.jsonl 2>/dev/null || true
rm -f state/heartbeat-trigger.json 2>/dev/null || true
if [ -f logs/operator-actions.jsonl ]; then
    git checkout -- logs/operator-actions.jsonl 2>/dev/null || true
fi

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
