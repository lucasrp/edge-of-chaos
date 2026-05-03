#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$EDGE_DIR/blog/app.py"
ENTRY_CARD="$EDGE_DIR/blog/templates/partials/entry_card.html"
COMPACT_CARD="$EDGE_DIR/blog/templates/partials/compact_card.html"

echo "=== blog pending status semantics test ==="

python3 - <<'PY' "$APP"
import ast
import sys

path = sys.argv[1]
source = open(path, encoding="utf-8").read()
tree = ast.parse(source, filename=path)

selected = []
for node in tree.body:
    if isinstance(node, ast.Assign):
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if names & {"UNPUBLISHED_STATUSES", "UNPUBLISHED_TAGS"}:
            selected.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name in {"_normalized_token", "is_entry_published"}:
        selected.append(node)

namespace = {}
module = ast.Module(body=selected, type_ignores=[])
ast.fix_missing_locations(module)
exec(compile(module, path, "exec"), namespace)

is_entry_published = namespace["is_entry_published"]

assert is_entry_published({}, ["report"]) is True
assert is_entry_published({"status": "approved"}, ["operator-authored"]) is True
assert is_entry_published({"status": "draft"}, ["report"]) is False
assert is_entry_published({"status": "pending"}, ["report"]) is False
assert is_entry_published({"status": "pendente"}, ["report"]) is False
assert is_entry_published({}, ["draft"]) is False

assert "pipeline_complete = bool(report_name and (REPORTS_DIR / report_name).exists())" in source
assert '"pipeline_status": "complete" if pipeline_complete else "missing_report"' in source
assert "published = is_entry_published(fm, tags_list)" in source
PY

grep -q "entry.pipeline_complete" "$ENTRY_CARD"
grep -q "entry.pipeline_complete" "$COMPACT_CARD"
! grep -q "not entry.published.*SEM PIPELINE" "$ENTRY_CARD"
! grep -q "not entry.published.*SEM PIPELINE" "$COMPACT_CARD"

echo "ALL TESTS PASSED"
