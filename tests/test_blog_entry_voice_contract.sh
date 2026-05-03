#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTOCOL="$EDGE_DIR/skills/_shared/state-protocol.md"
TEMPLATE="$EDGE_DIR/skills/_shared/report-template.md"

echo "=== blog entry voice contract test ==="

grep -q "Blog Entry Voice Contract" "$PROTOCOL"
grep -q "The blog entry body is the invitation, not the report" "$PROTOCOL"
grep -q "operator gain" "$PROTOCOL"
grep -q "Roberto-class reader" "$PROTOCOL"
grep -q "default to 2-4 paragraphs" "$PROTOCOL"
grep -q "Put technical depth in the report" "$PROTOCOL"
grep -q "Never publish raw report scaffolding" "$PROTOCOL"
grep -q "Write the blog entry as a light strategic invitation" "$TEMPLATE"
grep -q "Roberto-class external reader" "$TEMPLATE"
grep -q "operator gains" "$TEMPLATE"
grep -q "YAML/report structure" "$TEMPLATE"
grep -q "raw scope blocks" "$TEMPLATE"

python3 - <<'PY' "$EDGE_DIR"
import re
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "tools"))
from _shared import artifact_runtime as module

body = """# Substrate gap confirmed: gdrive primitive operations are list/tree/read/head

Substrate gap confirmed: gdrive primitive operations are list/tree/read/head. The Drive upload memory update presupposes a capability that the bound primitive does not expose.

---

**Map Mode:** coverage
**Scope:** four operator memory_updates from MEMORY.md on 2026-05-02.

## Evidence

- operation: list
- operation: tree
- operation: read
- operation: head

## Gap

There is no upload operation.

## Next

Open a genotype issue and add the missing primitive operation.
"""

entry = module._build_entry_body("Substrate gap confirmed: gdrive primitive operations are list/tree/read/head", body)
paragraphs = [item for item in re.split(r"\n\s*\n", entry.strip()) if item.strip()]
assert len(paragraphs) <= 4, entry
assert not entry.lstrip().startswith("# "), entry
assert "**Scope:**" not in entry
assert "- operation:" not in entry
assert "Writing the map" not in entry
assert "Abra o relatório" in entry
PY

echo "ALL TESTS PASSED"
