#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-curation-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
TMP_STATE="$TMP_BASE/state"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_REPO"/{tools,blog/entries,config} "$TMP_REPO/tools/_shared" "$TMP_STATE"/{state,topics,threads,logs} "$TMP_STATE/state/projections" "$TMP_STATE/state/operator-pressure" "$TMP_HOME"

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="curation-test"

cp "$EDGE_DIR/tools/edge-curation" "$TMP_REPO/tools/edge-curation"
cp "$EDGE_DIR/tools/rollup-workflow-funnel.py" "$TMP_REPO/tools/rollup-workflow-funnel.py"
chmod +x "$TMP_REPO/tools/edge-curation"

cat >"$TMP_REPO/config/paths.py" <<'PY'
import os
from pathlib import Path

EDGE_REPO_DIR = Path(os.environ["EDGE_REPO_DIR"])
EDGE_STATE_DIR = Path(os.environ["EDGE_STATE_DIR"])
CLAIMS_DIGEST_FILE = EDGE_STATE_DIR / "state" / "projections" / "claims-digest.json"
CURADORIA_CANDIDATES_FILE = EDGE_STATE_DIR / "state" / "curadoria-candidates.json"
CURATION_DIGEST_FILE = EDGE_STATE_DIR / "state" / "curation-digest.json"
ENTRIES_DIR = EDGE_REPO_DIR / "blog" / "entries"
ORPHAN_CLAIMS_FILE = EDGE_STATE_DIR / "state" / "projections" / "orphan-claims.json"
OPERATOR_PRESSURE_HOT_DIGEST_FILE = EDGE_STATE_DIR / "state" / "operator-pressure" / "hot-digest.json"
PROCEDURE_CURATION_FILE = EDGE_STATE_DIR / "state" / "procedure-curation.json"
THREADS_DIR = EDGE_STATE_DIR / "threads"
TOPICS_DIR = EDGE_STATE_DIR / "topics"
WORKFLOW_HEALTH_FILE = EDGE_STATE_DIR / "state" / "workflow-health.json"
EVENTS_FILE = EDGE_STATE_DIR / "logs" / "events.jsonl"
STATE_DIR = EDGE_STATE_DIR / "state"
PY

cat >"$TMP_REPO/tools/_shared/telemetry.py" <<'PY'
def emit_shadow_event(*args, **kwargs):
    return None

def log_event(*args, **kwargs):
    return None
PY

cat >"$TMP_REPO/tools/curadoria-compute" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
STATE_DIR="${EDGE_STATE_DIR}/state"
mkdir -p "$STATE_DIR"
cat >"$STATE_DIR/curadoria-candidates.json" <<'JSON'
{
  "total_docs": 12,
  "stale_candidates": 2,
  "archive_auto": [{"doc_id": 1}],
  "merge_review": [{"cluster_id": 1}],
  "strengthen_targets": [{"doc_id": 2}]
}
JSON
echo ok
SH
chmod +x "$TMP_REPO/tools/curadoria-compute"

mkdir -p "$TMP_REPO/search"
cat >"$TMP_REPO/search/edge-index" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" >"${EDGE_STATE_DIR}/state/topics-index.args"
SH
chmod +x "$TMP_REPO/search/edge-index"

cat >"$TMP_REPO/blog/entries/2026-04-20-one.md" <<'EOF'
---
title: "One"
date: 2026-04-20
tags: [note]
procedure:
  - "When the same pattern repeats, write it down."
workflows_used:
  - cluster-topic-refresh
---
EOF

cat >"$TMP_REPO/blog/entries/2026-04-21-two.md" <<'EOF'
---
title: "Two"
date: 2026-04-21
tags: [note]
procedure:
  - "When the same pattern repeats, write it down."
workflows_broken:
  - stale-workflow
---
EOF

cat >"$TMP_REPO/blog/entries/2026-04-22-three.md" <<'EOF'
---
title: "Three"
date: 2026-04-22
tags: [note]
procedure:
  - "When the same pattern repeats, write it down."
---
EOF

cat >"$TMP_REPO/blog/entries/2026-01-01-old-workflow.md" <<'EOF'
---
title: "workflow: Old workflow"
date: 2026-01-01
tags: [workflow]
---
EOF

cat >"$TMP_STATE/topics/topic-a.md" <<'EOF'
# Topic A
EOF

cat >"$TMP_STATE/state/projections/claims-digest.json" <<'JSON'
{
  "claims": [
    {
      "claim_id": "claim-alpha",
      "text": "Search substrate still has no topic producer.",
      "kind": "gap",
      "threads": ["search-substrate"],
      "support_count": 1,
      "latest_artifact_filename": "2026-04-24-research-topic-contract.md",
      "latest_date": "2026-04-24T00:00:00+00:00"
    },
    {
      "claim_id": "claim-beta",
      "text": "Runtime observability needs a canonical hot-state loop.",
      "kind": "gap",
      "threads": ["runtime-observability"],
      "support_count": 1,
      "latest_artifact_filename": "2026-04-24-runtime.md",
      "latest_date": "2026-04-24T00:00:00+00:00"
    }
  ],
  "hot_threads_by_open_claims": [
    {"thread_id": "search-substrate", "open_claims": 1},
    {"thread_id": "runtime-observability", "open_claims": 1}
  ]
}
JSON

cat >"$TMP_STATE/state/projections/orphan-claims.json" <<'JSON'
{
  "orphan_total": 0,
  "candidate_clusters": []
}
JSON

cat >"$TMP_STATE/state/operator-pressure/hot-digest.json" <<'JSON'
{
  "schema_version": 5,
  "generated_at": "2026-04-24T00:00:00+00:00",
  "summary": "operator feedback asks for hot-state curation",
  "signal_from_operator_now": [
    {
      "item_id": "pressure-hot-state",
      "text": "threads e topics sao o estado quente; direcionamento quente e conhecimento quente",
      "target": "thread",
      "kind": "directive",
      "repeat_count": 1,
      "status": "active",
      "entities": ["topic"],
      "last_seen_at": "2026-04-24T00:00:00+00:00"
    }
  ],
  "operator_pains_resolvable_now": [],
  "operator_toil_optimizable_now": [],
  "mistakes_to_avoid_now": [],
  "implicit_needs_hypotheses": [],
  "workflow_candidates": [],
  "capability_candidates": [],
  "memory_updates": [
    {
      "item_id": "pressure-memory-workflow",
      "text": "workflow para reports deve introduzir contexto antes de tabelas densas",
      "target": "workflow",
      "kind": "memory_update",
      "repeat_count": 1,
      "status": "active",
      "entities": ["memory", "report"],
      "source_kinds": ["memory"],
      "last_seen_at": ""
    },
    {
      "item_id": "pressure-memory-preskill",
      "text": "sempre introduza tabelas densas antes de renderizar seco",
      "target": "policy",
      "kind": "memory_update",
      "repeat_count": 1,
      "status": "active",
      "entities": ["memory", "report"],
      "source_kinds": ["memory"],
      "last_seen_at": ""
    }
  ],
  "pre_skill_context": [
    {
      "item_id": "pressure-memory-preskill",
      "text": "sempre introduza tabelas densas antes de renderizar seco",
      "target": "policy",
      "kind": "memory_update",
      "repeat_count": 1,
      "status": "active",
      "entities": ["memory", "report"],
      "source_kinds": ["memory"],
      "last_seen_at": ""
    }
  ],
  "substrate_gap_requests": [],
  "active_entities": ["topic"],
  "item_ids": ["pressure-hot-state", "pressure-memory-workflow", "pressure-memory-preskill"]
}
JSON

cat >"$TMP_STATE/threads/runtime-observability.md" <<'EOF'
---
id: runtime-observability
title: Runtime Observability
status: active
created: 2026-04-24
updated: 2026-04-24
---

Existing hot direction.
EOF

echo "=== edge-curation Smoke Test ==="
echo "Temp repo: $TMP_REPO"
echo ""

echo "--- Test 1: sync builds procedure-curation and digest ---"
if python3 - <<'PY' "$TMP_REPO/tools/edge-curation" "$TMP_STATE/state/procedure-curation.json" "$TMP_STATE/state/curation-digest.json"
import json
import runpy
import subprocess
import sys
from pathlib import Path

tool, proc_path, digest_path = sys.argv[1:]
result = subprocess.run([tool, "sync", "--json"], capture_output=True, text=True, check=True)
payload = json.loads(result.stdout)
proc = json.loads(Path(proc_path).read_text(encoding="utf-8"))
digest = json.loads(Path(digest_path).read_text(encoding="utf-8"))
repo_root = Path(tool).parents[1]
module = runpy.run_path(tool)
assert module["_is_memory_workflow_item"]({
    "sections": ["memory_updates"],
    "source_kinds": ["memory"],
    "target": "workflow",
    "text": "workflow para reports deve introduzir contexto",
}) is True
assert module["_is_memory_workflow_item"]({
    "sections": ["memory_updates"],
    "source_kinds": ["memory"],
    "target": "capability",
    "text": "Google Drive e a pasta edge sao o lugar padrao de upload",
}) is False
assert module["_is_operator_pre_skill_context_item"]({
    "sections": ["memory_updates", "pre_skill_context"],
    "source_kinds": ["memory"],
    "target": "policy",
    "text": "sempre introduza tabelas densas antes de renderizar seco",
}) is True
assert module["_is_memory_workflow_item"]({
    "sections": ["memory_updates", "pre_skill_context"],
    "source_kinds": ["memory"],
    "target": "policy",
    "text": "sempre introduza tabelas densas antes de renderizar seco",
}) is False

assert payload["procedures"]["candidate_total"] == 1
assert proc["crystallization_candidates"][0]["claim_count"] == 3
assert digest["corpus"]["stale_candidates"] == 2
assert digest["topics"]["total"] == 5
assert digest["hot_state"]["threads"]["referenced_total"] == 2
assert digest["hot_state"]["threads"]["created_total"] == 1
assert digest["hot_state"]["topics"]["created_total"] == 2
assert digest["operator_pressure"]["items_total"] == 3
assert digest["operator_pressure"]["groups_total"] == 2
assert digest["operator_pressure"]["threads_created"] == 2
assert digest["operator_pressure"]["topics_created"] == 2
assert digest["operator_pressure"]["workflows_created"] == 1
assert digest["operator_pressure"]["pre_skill_context_total"] == 1
state_root = Path(digest_path).parents[1]
assert (state_root / "threads" / "search-substrate.md").exists()
assert (state_root / "threads" / "threads-topics-hot-state.md").exists()
assert (state_root / "topics" / "search-substrate.md").exists()
assert (state_root / "topics" / "runtime-observability.md").exists()
assert (state_root / "topics" / "threads-topics-hot-state.md").exists()
workflows = list((repo_root / "blog" / "entries").glob("*memory-workflow-para-reports*.md"))
assert workflows
workflow_text = workflows[0].read_text(encoding="utf-8")
assert "tags: [workflow, memory-derived, operator-pressure]" in workflow_text
assert "workflow-draft" not in workflow_text
assert "funnel_tracked_total" in digest["workflow_health"]
assert "topics" in Path(f"{Path(digest_path).parent}/topics-index.args").read_text(encoding="utf-8")

second = subprocess.run([tool, "sync", "--json"], capture_output=True, text=True, check=True)
second_payload = json.loads(second.stdout)
second_digest = json.loads(Path(digest_path).read_text(encoding="utf-8"))
assert second_payload["topics"]["total"] == 5
assert second_digest["hot_state"]["threads"]["created_total"] == 0
assert second_digest["hot_state"]["topics"]["created_total"] == 0
assert second_digest["operator_pressure"]["threads_created"] == 0
assert second_digest["operator_pressure"]["topics_created"] == 0
assert second_digest["operator_pressure"]["workflows_created"] == 0
assert second_digest["operator_pressure"]["pre_skill_context_total"] == 1
PY
then
    pass "sync builds procedure-curation and digest"
else
    fail "sync builds procedure-curation and digest"
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
