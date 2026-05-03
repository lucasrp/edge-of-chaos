#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-curation-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
TMP_STATE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_REPO/tools" "$TMP_REPO/config" "$TMP_REPO/threads" "$TMP_REPO/topics" "$TMP_REPO/blog/entries" "$TMP_STATE/state/operator-pressure" "$TMP_STATE/state/projections"
cp "$EDGE_DIR/tools/edge-curation" "$TMP_REPO/tools/edge-curation"
cp -R "$EDGE_DIR/tools/_shared" "$TMP_REPO/tools/_shared"
cp "$EDGE_DIR/config/paths.py" "$TMP_REPO/config/paths.py"
cp "$EDGE_DIR/config/branding.py" "$TMP_REPO/config/branding.py"

cat >"$TMP_REPO/tools/curadoria-compute" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$EDGE_STATE_DIR/state"
cat >"$EDGE_STATE_DIR/state/curadoria-candidates.json" <<'JSON'
{"total_docs": 3, "stale_candidates": 1, "archive_auto": [], "merge_review": [], "strengthen_targets": []}
JSON
SH
chmod +x "$TMP_REPO/tools/curadoria-compute" "$TMP_REPO/tools/edge-curation"

cat >"$TMP_REPO/search-edge-index" <<'SH'
#!/usr/bin/env bash
exit 0
SH

mkdir -p "$TMP_REPO/search"
cat >"$TMP_REPO/search/edge-index" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$TMP_REPO/search/edge-index"

cat >"$TMP_STATE/state/operator-pressure/hot-digest.json" <<'JSON'
{
  "schema_version": 6,
  "summary": "operator pressure",
  "signal_from_operator_now": [
    {"item_id": "pressure-hot-state", "text": "threads de Meta precisam consolidar evidencias recentes", "target": "thread", "kind": "directive", "repeat_count": 2, "entities": ["meta"], "source_kinds": ["session"], "last_seen_at": "2026-05-01T10:00:00+00:00"}
  ],
  "memory_updates": [
    {"item_id": "pressure-memory-preskill", "text": "pre-skill context deve lembrar que tabelas densas precisam introducao narrativa", "target": "pre_skill_context", "kind": "memory_update", "repeat_count": 1, "entities": ["report"], "source_kinds": ["memory"], "last_seen_at": ""}
  ],
  "pre_skill_context": [
    {"item_id": "pressure-memory-preskill", "text": "pre-skill context deve lembrar que tabelas densas precisam introducao narrativa", "target": "pre_skill_context", "kind": "memory_update", "repeat_count": 1, "entities": ["report"], "source_kinds": ["memory"], "last_seen_at": ""}
  ],
  "operator_pains_resolvable_now": [],
  "operator_toil_optimizable_now": [],
  "mistakes_to_avoid_now": [],
  "implicit_needs_hypotheses": [],
  "capability_candidates": [],
  "substrate_gap_requests": [],
  "active_entities": ["meta", "report"],
  "item_ids": ["pressure-hot-state", "pressure-memory-preskill"]
}
JSON

cat >"$TMP_STATE/state/projections/open-gaps-digest.json" <<'JSON'
{
  "open_total": 1,
  "entries_with_gaps": 1,
  "gaps": [
    {"gap_id": "gap-meta", "text": "Meta evidence still needs a durable topic", "artifact_filename": "entry.md", "date": "2026-05-01", "threads": ["meta-evidence"]}
  ],
  "hot_threads_by_open_gaps": [{"thread_id": "meta-evidence", "open_gaps": 1, "latest": "2026-05-01"}],
  "recent_open_gaps": [{"gap_id": "gap-meta", "text": "Meta evidence still needs a durable topic"}]
}
JSON

export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"

echo "=== edge-curation Test ==="
echo ""

echo "--- Test 1: sync builds digest without retired artifacts ---"
if python3 - <<'PY' "$TMP_REPO/tools/edge-curation" "$TMP_STATE/state/curation-digest.json" "$TMP_REPO"
import importlib.util
import json
import os
import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader

tool, digest_path, _repo_root = sys.argv[1:]
loader = SourceFileLoader("edge_curation", tool)
spec = importlib.util.spec_from_loader("edge_curation", loader)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

digest = module.build_curation_digest(60)
digest_path = Path(digest_path)
state_root = Path(os.environ["EDGE_STATE_DIR"])

assert digest_path.exists()
assert digest["status"] == "ok"
assert "procedures" not in digest
assert "workflow_health" not in digest
assert "procedure_curation" not in digest["files"]
assert digest["operator_pressure"]["pre_skill_context_total"] == 1
assert digest["operator_pressure"]["topics_created"] >= 1
assert digest["operator_pressure"]["threads_created"] >= 1
assert digest["operator_pressure"]["pre_skill_context"]["candidates"][0]["judgement"] == "pre_skill_context"
assert not list((state_root / "blog" / "entries").glob("*.md"))
assert (state_root / "threads" / "meta-evidence.md").exists()
assert (state_root / "topics" / "meta-evidence.md").exists()
PY
then
    pass "sync builds digest and migrates operator guidance to topics/pre-skill context"
else
    fail "sync builds digest and migrates operator guidance to topics/pre-skill context"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
