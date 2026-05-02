#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$EDGE_DIR/blog/consolidate-state.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ENTRY="$TMP_DIR/entry-invalid-frontmatter.md"
REPORT="$TMP_DIR/spec-invalid-frontmatter.yaml"
OUT="$TMP_DIR/out.txt"

cat >"$ENTRY" <<'EOF'
---
title: "Invalid frontmatter"
claims:
- This claim embeds `async_inbox.source: 'blog-chat'` without quotes
---

Body.
EOF

cat >"$REPORT" <<'EOF'
title: "Invalid Frontmatter Test"
subtitle: "Should never reach report rendering"
date: "02/05/2026"
executive_summary:
  - "This file only exists so consolidate-state has a report argument."
sections: []
EOF

if "$SCRIPT" "$ENTRY" "$REPORT" >"$OUT" 2>&1; then
    echo "FAIL: consolidate-state accepted invalid entry frontmatter" >&2
    cat "$OUT" >&2
    exit 1
fi

grep -q "Invalid entry frontmatter YAML" "$OUT"
grep -q "frontmatter_parse" "$EDGE_DIR/logs/pipeline-failures.jsonl"

echo "PASS: consolidate-state surfaces invalid frontmatter YAML"
