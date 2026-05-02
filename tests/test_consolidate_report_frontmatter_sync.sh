#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$EDGE_DIR/tools/sync-report-frontmatter.py"
SCRIPT="$EDGE_DIR/blog/consolidate-state.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ENTRY="$TMP_DIR/entry-research-contract.md"
OUT="$TMP_DIR/out.txt"

cat >"$ENTRY" <<'EOF'
---
title: "Research Contract"
date: 2026-05-02
tags: [research]
report: "research-contract.html"
open_gaps:
  - "Gap: quoted because YAML punctuation matters"
---

Body.
EOF

python3 "$TOOL" "$ENTRY" "entry-research-contract.html" >"$OUT"
grep -q "report=updated:research-contract.html->entry-research-contract.html" "$OUT"
grep -q "^report: entry-research-contract.html$" "$ENTRY"

python3 - "$ENTRY" <<'PY'
from pathlib import Path
import sys

import yaml

raw = Path(sys.argv[1]).read_text(encoding="utf-8")
fm = yaml.safe_load(raw.split("---", 2)[1]) or {}
assert fm["report"] == "entry-research-contract.html"
assert fm["open_gaps"] == ["Gap: quoted because YAML punctuation matters"]
PY

cat >"$ENTRY" <<'EOF'
---
title: "Research Contract"
date: 2026-05-02
tags: [research]
open_gaps:
  - "Still valid"
---

Body.
EOF

python3 "$TOOL" "$ENTRY" "entry-research-contract.html" >"$OUT"
grep -q "report=updated:<missing>->entry-research-contract.html" "$OUT"
grep -q "^report: entry-research-contract.html$" "$ENTRY"

cat >"$ENTRY" <<'EOF'
---
title: "Reflection R6 — Sinal Emergente de missing_artifact_published"
date: 2026-05-02
type: note
tags: [reflection, runtime, health, failure-analysis]
open_gaps:
  - id: gap-r6-missing-artifact
    text: "missing_artifact_published apareceu em 4/5 falhas"
    threads: [infrastructure-security]
  - id: gap-r6-work-stagnation
    text: "0/4 open work items avancaram em 5 dias"
    threads: [infrastructure-security, analise-processual]
---

Body.
EOF

python3 "$TOOL" "$ENTRY" "edge-reflection-R6-entry.html" >"$OUT"
grep -q "threads=derived:2" "$OUT"
grep -q "keywords=derived:" "$OUT"
grep -q "^threads: \\[infrastructure-security, analise-processual\\]$" "$ENTRY"
grep -q "^keywords: " "$ENTRY"

grep -q 'sync-report-frontmatter.py" "$ENTRY_PATH" "$REPORT_FILENAME"' "$SCRIPT"
grep -q 'VERIFY_ENTRY_PATH="$ENTRIES_DIR/$SLUG.md"' "$SCRIPT"

echo "PASS: consolidate-state synchronizes report frontmatter before and after publish"
