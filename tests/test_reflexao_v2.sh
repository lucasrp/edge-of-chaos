#!/usr/bin/env bash
set -euo pipefail

# Integration test for reflexao v2 system
# Verifies all pieces exist, produce valid output, and work together

PASS=0
FAIL=0
TEST_RUN_ID="test-reflexao-v2-$$"
# shellcheck source=../config/paths.sh
source "$(dirname "$0")/../config/paths.sh"
LEDGER="$LOGS_DIR/execution-ledger.jsonl"
LEDGER_BAK=""

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    echo ""
    echo "=== Cleanup ==="
    # Remove test entries from ledger
    if [[ -f "$LEDGER" ]]; then
        grep -v "$TEST_RUN_ID" "$LEDGER" > "${LEDGER}.tmp" 2>/dev/null || true
        mv "${LEDGER}.tmp" "$LEDGER"
        echo "Removed test entries from execution-ledger.jsonl"
    fi
    # Restore backup if we created one
    if [[ -n "$LEDGER_BAK" && -f "$LEDGER_BAK" ]]; then
        rm -f "$LEDGER_BAK"
    fi
}
trap cleanup EXIT

echo "=== reflexao v2 Integration Test ==="
echo "Run ID: $TEST_RUN_ID"
echo ""

# --- Test 1: edge-ledger record (5 sample events) ---
echo "--- Test 1: edge-ledger record ---"
# Back up ledger if it exists
if [[ -f "$LEDGER" ]]; then
    LEDGER_BAK="${LEDGER}.bak.$$"
    cp "$LEDGER" "$LEDGER_BAK"
fi

edge-ledger record --run-id "$TEST_RUN_ID" --skill reflexao --phase gather --tool edge-search --attempt 1 --ok --duration-ms 150 --target-id doc-1 >/dev/null 2>&1
edge-ledger record --run-id "$TEST_RUN_ID" --skill reflexao --phase gather --tool edge-search --attempt 1 --fail --duration-ms 3200 --error-class timeout --error-fingerprint "search_timeout_gather" --target-id doc-2 >/dev/null 2>&1
edge-ledger record --run-id "$TEST_RUN_ID" --skill reflexao --phase gather --tool edge-search --attempt 2 --ok --duration-ms 180 --resolved-on-retry --target-id doc-2 >/dev/null 2>&1
edge-ledger record --run-id "$TEST_RUN_ID" --skill blog --phase publish --tool bash --attempt 1 --fail --duration-ms 5000 --error-class permission --error-fingerprint "blog_publish_permission" --target-id blog-1 >/dev/null 2>&1
edge-ledger record --run-id "$TEST_RUN_ID" --skill blog --phase publish --tool bash --attempt 2 --ok --duration-ms 1200 --resolved-on-retry --target-id blog-1 >/dev/null 2>&1

# Verify events were recorded
COUNT=$(grep -c "$TEST_RUN_ID" "$LEDGER" 2>/dev/null || echo 0)
if [[ "$COUNT" -eq 5 ]]; then
    pass "edge-ledger recorded 5 events"
else
    fail "edge-ledger recorded $COUNT events (expected 5)"
fi

# --- Test 2: edge-ledger query ---
echo "--- Test 2: edge-ledger query ---"
QUERY_OUT=$(edge-ledger query --since 1h --run-id "$TEST_RUN_ID" 2>/dev/null)
if echo "$QUERY_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d)==5" 2>/dev/null; then
    pass "edge-ledger query returns valid JSON with 5 events"
else
    fail "edge-ledger query output invalid or wrong count"
fi

FAIL_QUERY=$(edge-ledger query --since 1h --run-id "$TEST_RUN_ID" --fails-only 2>/dev/null)
if echo "$FAIL_QUERY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d)==2" 2>/dev/null; then
    pass "edge-ledger query --fails-only returns 2 failures"
else
    fail "edge-ledger query --fails-only wrong count"
fi

# --- Test 3: edge-ledger stats ---
echo "--- Test 3: edge-ledger stats ---"
STATS_OUT=$(edge-ledger stats --since 1h 2>/dev/null)
if echo "$STATS_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'total_events' in d and 'retry_rate' in d" 2>/dev/null; then
    pass "edge-ledger stats produces valid JSON with expected fields"
else
    fail "edge-ledger stats output invalid"
fi

# --- Test 4: ledger_rollup.py ---
echo "--- Test 4: ledger_rollup.py ---"
python3 ~/edge/tools/ledger_rollup.py --since 1h 2>/dev/null
if [[ -f ~/edge/state/ops-hotspots.json ]]; then
    if python3 -c "
import json
with open('$HOME/edge/state/ops-hotspots.json') as f:
    d = json.load(f)
assert 'generated_at' in d
assert 'incidents' in d
assert 'top_pain' in d
assert 'recovered_but_unstable' in d
assert 'codify_now' in d
" 2>/dev/null; then
        pass "ledger_rollup.py produces valid ops-hotspots.json"
    else
        fail "ops-hotspots.json missing expected fields"
    fi
else
    fail "ops-hotspots.json not created"
fi

# --- Test 5: git_signals.py ---
echo "--- Test 5: git_signals.py ---"
python3 ~/edge/tools/git_signals.py --since 7d 2>/dev/null
if [[ -f ~/edge/state/git-signals.json ]]; then
    if python3 -c "
import json
with open('$HOME/edge/state/git-signals.json') as f:
    d = json.load(f)
for field in ['generated_at','window','total_commits','fix_chains','duplicate_slugs',
              'pipeline_failures','state_violations','thread_coverage',
              'skill_distribution','claims_summary','persistent_gaps']:
    assert field in d, f'missing {field}'
" 2>/dev/null; then
        pass "git_signals.py produces valid git-signals.json"
    else
        fail "git-signals.json missing expected fields"
    fi
else
    fail "git-signals.json not created"
fi

# --- Test 6: search_events table exists ---
echo "--- Test 6: search_events table ---"
if python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/edge/search/edge-memory.db')
cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='search_events'\")
assert cursor.fetchone() is not None
cols = [r[1] for r in conn.execute('PRAGMA table_info(search_events)')]
for c in ['query_norm','doc_id','rank','score','ts']:
    assert c in cols, f'missing column {c}'
" 2>/dev/null; then
    pass "search_events table exists with correct schema"
else
    fail "search_events table missing or wrong schema"
fi

# --- Test 7: curadoria_compute.py --mode stats ---
echo "--- Test 7: curadoria_compute.py ---"
if python3 ~/edge/tools/curadoria_compute.py --mode stats 2>/dev/null; then
    pass "curadoria_compute.py --mode stats runs without error"
else
    fail "curadoria_compute.py --mode stats failed"
fi

# --- Test 8: debugging.md has 3 sections ---
echo "--- Test 8: debugging.md sections ---"
DBG="$MEMORY_BASE/debugging.md"
SECTIONS_OK=true
for section in "## Erros Operacionais" "## Regras de Operação" "## Segurança e Política"; do
    if ! grep -qF "$section" "$DBG" 2>/dev/null; then
        fail "debugging.md missing section: $section"
        SECTIONS_OK=false
    fi
done
if $SECTIONS_OK; then
    pass "debugging.md has all 3 sections"
fi

# --- Test 9: /reflexao SKILL.md mentions all 3 modes ---
echo "--- Test 9: reflexao SKILL.md modes ---"
REFLEXAO_SKILL="$HOME/.claude/skills/reflexao/SKILL.md"
MODES_OK=true
for mode in "heartbeat-normal" "heartbeat-escalated" "manual"; do
    if ! grep -q "$mode" "$REFLEXAO_SKILL" 2>/dev/null; then
        fail "reflexao SKILL.md missing mode: $mode"
        MODES_OK=false
    fi
done
if $MODES_OK; then
    pass "reflexao SKILL.md references all 3 modes"
fi

# --- Summary ---
echo ""
echo "=== Results ==="
echo "PASS: $PASS  FAIL: $FAIL"
if [[ $FAIL -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
