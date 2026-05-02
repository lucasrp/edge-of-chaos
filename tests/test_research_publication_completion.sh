#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESEARCH_SKILL="$EDGE_DIR/skills/research/SKILL.md"

echo "=== research publication completion contract ==="

grep -q "stdout-only research answer is not a completed" "$RESEARCH_SKILL"
grep -q "read \`skills/_shared/report-template.md\`" "$RESEARCH_SKILL"
grep -q "run \`consolidate-state\`" "$RESEARCH_SKILL"
grep -q "validate both files" "$RESEARCH_SKILL"
grep -q "Do not close by asking the operator" "$RESEARCH_SKILL"
grep -q "generated HTML report, blog entry, and meta-report have been verified" "$RESEARCH_SKILL"
grep -q "only place where the research exists" "$RESEARCH_SKILL"

echo "PASS: ed-research cannot treat stdout prose as a completed artifact"
