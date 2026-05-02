#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_SKILL="$EDGE_DIR/skills/report/SKILL.md"
TEMPLATE="$EDGE_DIR/skills/_shared/report-template.md"

echo "=== report publication completion contract ==="

grep -q "Publishing is not optional once \`/ed-report\` has chosen a topic" "$REPORT_SKILL"
grep -q "Files staged in" "$REPORT_SKILL"
grep -q "staging-only exit" "$REPORT_SKILL"
grep -q "concrete failing command and reason" "$REPORT_SKILL"
grep -q "validate the staging entry frontmatter" "$REPORT_SKILL"

grep -q "Staging is not completion" "$TEMPLATE"
grep -q "must not close with only" "$TEMPLATE"
grep -q "Run \`consolidate-state\` in this" "$TEMPLATE"
grep -q "concrete failing command and" "$TEMPLATE"
grep -q "Every gap must be valid YAML" "$TEMPLATE"
grep -q "Validate the staging entry frontmatter" "$TEMPLATE"

echo "PASS: ed-report cannot treat /tmp staging as a completed report"
