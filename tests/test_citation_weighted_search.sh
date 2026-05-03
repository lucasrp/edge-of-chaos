#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-citations-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/blog/entries" "$TMP_STATE/reports" "$TMP_STATE/search" "$TMP_STATE/logs" "$TMP_STATE/threads" "$TMP_STATE/state"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"

cat >"$TMP_STATE/blog/entries/source.md" <<'MD'
---
title: Source artifact
corpus_references:
  - path: blog/entries/cited.md
    context: primary_reference
  - path: reports/support.html
    context: background
---
body
MD

touch "$TMP_STATE/blog/entries/cited.md" "$TMP_STATE/blog/entries/uncited.md" "$TMP_STATE/reports/support.html"

echo "=== citation-weighted search Test ==="
echo ""

echo "--- Test 1: curated references are recorded idempotently and boost hybrid ranking ---"
if python3 - <<'PY'
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

search_dir = Path(os.environ["EDGE_REPO_DIR"]) / "search"
sys.path.insert(0, str(search_dir))

from db import ensure_db
from citations import record_citations, references_from_artifacts
import search as edge_search

state = Path(os.environ["EDGE_STATE_DIR"])
conn = ensure_db()
now = datetime.now(timezone.utc).isoformat()

def add_doc(path, title):
    cur = conn.execute(
        """
        INSERT INTO documents (path, type, title, content, content_hash, created_at, updated_at)
        VALUES (?, 'blog', ?, ?, ?, ?, ?)
        """,
        (str(path.resolve()), title, title, title, now, now),
    )
    return cur.lastrowid

cited = add_doc(state / "blog" / "entries" / "cited.md", "Cited prior work")
uncited = add_doc(state / "blog" / "entries" / "uncited.md", "Uncited adjacent work")
support = add_doc(state / "reports" / "support.html", "Supporting report")
conn.commit()

refs = references_from_artifacts([state / "blog" / "entries" / "source.md"])
result = record_citations(str(state / "blog" / "entries" / "source.md"), refs, conn=conn)
assert result["inserted"] == 2, result
result_again = record_citations(str(state / "blog" / "entries" / "source.md"), refs, conn=conn)
assert result_again["inserted"] == 0, result_again

for idx in range(9):
    record_citations(
        str(state / "blog" / "entries" / f"source-{idx}.md"),
        [str(state / "blog" / "entries" / "cited.md")],
        conn=conn,
    )

edge_search.embed_text = lambda _query: [0.0]
edge_search.vec_search = lambda *_args, **_kwargs: []
edge_search.fts_search = lambda *_args, **_kwargs: [
    {"id": uncited, "path": str((state / "blog" / "entries" / "uncited.md").resolve()), "type": "blog", "title": "Uncited adjacent work", "score": 0.02, "snippet": None},
    {"id": cited, "path": str((state / "blog" / "entries" / "cited.md").resolve()), "type": "blog", "title": "Cited prior work", "score": 0.01, "snippet": None},
    {"id": support, "path": str((state / "reports" / "support.html").resolve()), "type": "report", "title": "Supporting report", "score": 0.005, "snippet": None},
]

hits = edge_search.hybrid_search("prior work", limit=3, conn=conn)
assert hits[0]["id"] == cited, hits
assert hits[0]["citation_count"] == 10, hits[0]
assert hits[0]["base_score"] < hits[0]["score"], hits[0]
assert hits[-1]["id"] == uncited, hits
conn.close()
PY
then
    pass "citation records are idempotent and boost cited documents"
else
    fail "citation records are idempotent and boost cited documents"
fi

echo "--- Test 2: observability rollup exposes citation stats ---"
if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" python3 "$EDGE_DIR/tools/rollup-observability.py" >/dev/null && \
   python3 - <<'PY' "$TMP_STATE/state/observability-rollup.json"
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
citations = data["citations"]
assert citations["available"] is True
assert citations["total"] == 11, citations
assert citations["top_cited"][0]["citations"] == 10, citations
assert citations["recently_cited_7d"] >= 2, citations
PY
then
    pass "observability rollup includes citation stats"
else
    fail "observability rollup includes citation stats"
fi

echo "--- Test 3: corpus curation preserves high-value cited docs ---"
if EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" python3 "$EDGE_DIR/tools/curadoria_compute.py" --mode lite >/dev/null && \
   python3 - <<'PY' "$TMP_STATE/state/curadoria-candidates.json"
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
top = data["high_value_cited"][0]
assert top["citation_count"] == 10, data
assert top["title"] == "Cited prior work", data
PY
then
    pass "curadoria surfaces high-value cited docs"
else
    fail "curadoria surfaces high-value cited docs"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
