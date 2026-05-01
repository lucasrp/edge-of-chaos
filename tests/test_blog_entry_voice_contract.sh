#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTOCOL="$EDGE_DIR/skills/_shared/state-protocol.md"
TEMPLATE="$EDGE_DIR/skills/_shared/report-template.md"

echo "=== blog entry voice contract test ==="

grep -q "Blog Entry Voice Contract" "$PROTOCOL"
grep -q "The blog entry body is the invitation, not the report" "$PROTOCOL"
grep -q "operator gain" "$PROTOCOL"
grep -q "default to 2-4 paragraphs" "$PROTOCOL"
grep -q "Put technical depth in the report" "$PROTOCOL"
grep -q "Write the blog entry as a light strategic invitation" "$TEMPLATE"
grep -q "operator gains by opening the report" "$TEMPLATE"
grep -q "duplicate the YAML/report structure" "$TEMPLATE"

echo "ALL TESTS PASSED"
