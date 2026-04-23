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

mkdir -p "$TMP_REPO"/{tools,blog/entries,config} "$TMP_REPO/tools/_shared" "$TMP_STATE"/{state,topics,logs} "$TMP_HOME"

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
CURADORIA_CANDIDATES_FILE = EDGE_STATE_DIR / "state" / "curadoria-candidates.json"
CURATION_DIGEST_FILE = EDGE_STATE_DIR / "state" / "curation-digest.json"
ENTRIES_DIR = EDGE_REPO_DIR / "blog" / "entries"
PROCEDURE_CURATION_FILE = EDGE_STATE_DIR / "state" / "procedure-curation.json"
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

echo "=== edge-curation Smoke Test ==="
echo "Temp repo: $TMP_REPO"
echo ""

echo "--- Test 1: sync builds procedure-curation and digest ---"
if python3 - <<'PY' "$TMP_REPO/tools/edge-curation" "$TMP_STATE/state/procedure-curation.json" "$TMP_STATE/state/curation-digest.json"
import json
import subprocess
import sys
from pathlib import Path

tool, proc_path, digest_path = sys.argv[1:]
result = subprocess.run([tool, "sync", "--json"], capture_output=True, text=True, check=True)
payload = json.loads(result.stdout)
proc = json.loads(Path(proc_path).read_text(encoding="utf-8"))
digest = json.loads(Path(digest_path).read_text(encoding="utf-8"))

assert payload["procedures"]["candidate_total"] == 1
assert proc["crystallization_candidates"][0]["claim_count"] == 3
assert digest["corpus"]["stale_candidates"] == 2
assert digest["topics"]["total"] == 1
assert "funnel_tracked_total" in digest["workflow_health"]
assert "topics" in Path(f"{Path(digest_path).parent}/topics-index.args").read_text(encoding="utf-8")
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
