#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_SKILL="$EDGE_DIR/skills/report/SKILL.md"
TEMPLATE="$EDGE_DIR/skills/_shared/report-template.md"
WORKFLOWS="$EDGE_DIR/skills/_shared/workflow-conventions.md"
EDGE_APPLY="$EDGE_DIR/tools/edge-apply"

echo "=== report review ownership contract test ==="

grep -q "Do not call \`edge-consult\` or \`review-gate\` manually" "$REPORT_SKILL"
grep -q "Single review owner" "$TEMPLATE"
grep -q "consolidate-state.*single owner of publication review" "$TEMPLATE"
grep -q "Do not call \`edge-consult\` or \`review-gate\` manually before publishing" "$TEMPLATE"

if grep -q "BEFORE generating the report YAML, submit" "$TEMPLATE"; then
  echo "FAIL: report template still asks skills to run standalone edge-consult before YAML" >&2
  exit 1
fi

if grep -q "review-gate /tmp/spec" "$TEMPLATE"; then
  echo "FAIL: report template still asks skills to run standalone review-gate" >&2
  exit 1
fi

if grep -q "edge-consult.*adversarial review of draft" "$WORKFLOWS"; then
  echo "FAIL: workflow conventions still duplicate adversarial review before consolidate-state" >&2
  exit 1
fi

grep -q "consolidate-state.*adversarial/Feynman/review gates" "$WORKFLOWS"
grep -q "consolidate-state.*adversarial/Feynman/review gates" "$EDGE_APPLY"

echo "ALL TESTS PASSED"
