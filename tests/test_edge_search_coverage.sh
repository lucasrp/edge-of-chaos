#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== edge-search Coverage Test ==="
echo ""

echo "--- Test 1: required groups covered when topic/workflow/memory all hit ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "search"))

import search as mod

def fake_hybrid(query, limit=10, fts_weight=0.3, vec_weight=0.7, doc_type=None, conn=None, _query_embedding=None):
    fixtures = {
        "topic": [{"id": 1, "path": "topics/alpha.md", "type": "topic", "title": "Alpha", "score": 0.9, "snippet": None}],
        "workflow": [{"id": 2, "path": "workflows/research.md", "type": "workflow", "title": "Research", "score": 0.8, "snippet": None}],
        "note": [{"id": 3, "path": "notes/ops.md", "type": "note", "title": "Ops", "score": 0.7, "snippet": None}],
        "blog": [],
        "report": [],
    }
    return list(fixtures.get(doc_type, []))

mod.hybrid_search = fake_hybrid
mod.search_with_sidecar = lambda query, limit=10, doc_type=None, wf_limit=3, min_wf_score=-0.15, conn=None: ([], [])
mod.embed_text = lambda query: [0.1, 0.2, 0.3]

results, coverage, workflows = mod.search_with_coverage(
    "heartbeat timeout",
    limit=5,
    required_types=["topic", "workflow", "memory"],
    conn=object(),
)

assert coverage["required_covered"] is True
assert coverage["missing_required_types"] == []
assert [item["name"] for item in coverage["required"]] == ["topic", "workflow", "memory"]
assert [item["hit_count"] for item in coverage["required"]] == [1, 1, 1]
assert [item["type"] for item in results[:3]] == ["topic", "workflow", "note"]
assert workflows == []
PY
then
    pass "search_with_coverage marks required groups as covered"
else
    fail "search_with_coverage marks required groups as covered"
fi

echo "--- Test 2: missing memory group is reported explicitly ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "search"))

import search as mod

def fake_hybrid(query, limit=10, fts_weight=0.3, vec_weight=0.7, doc_type=None, conn=None, _query_embedding=None):
    fixtures = {
        "topic": [{"id": 11, "path": "topics/beta.md", "type": "topic", "title": "Beta", "score": 0.9, "snippet": None}],
        "workflow": [{"id": 12, "path": "workflows/report.md", "type": "workflow", "title": "Report", "score": 0.8, "snippet": None}],
        "note": [],
        "blog": [],
        "report": [],
    }
    return list(fixtures.get(doc_type, []))

mod.hybrid_search = fake_hybrid
mod.search_with_sidecar = lambda query, limit=10, doc_type=None, wf_limit=3, min_wf_score=-0.15, conn=None: (
    [{"id": 90, "path": "misc/general.md", "type": "note", "title": "General", "score": 0.4, "snippet": None}],
    [],
)
mod.embed_text = lambda query: [0.4, 0.5, 0.6]

results, coverage, workflows = mod.search_with_coverage(
    "topic refresh",
    limit=5,
    required_types=["topic", "workflow", "memory"],
    conn=object(),
)

assert coverage["required_covered"] is False
assert coverage["missing_required_types"] == ["memory"]
assert [item["covered"] for item in coverage["required"]] == [True, True, False]
assert results[0]["type"] == "topic"
assert results[1]["type"] == "workflow"
assert workflows == []
assert "Coverage: MISSING memory" in mod.format_results(results, mode="hybrid-coverage", coverage=coverage)
PY
then
    pass "search_with_coverage reports missing required memory coverage"
else
    fail "search_with_coverage reports missing required memory coverage"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi

