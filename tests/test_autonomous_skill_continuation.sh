#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTOCOL="$EDGE_DIR/skills/_shared/state-protocol.md"
RESEARCH="$EDGE_DIR/skills/research/SKILL.md"

echo "=== autonomous skill continuation test ==="

grep -q "Autonomous Continuation After Explicit Dispatch" "$PROTOCOL"
grep -q "Do not stop mid-skill to ask whether to continue" "$PROTOCOL"
grep -q "bounded internal loops" "$PROTOCOL"
grep -q "Feynman gap-resolution loops are part of the" "$PROTOCOL"

grep -q "Do not pause after the first gap pass" "$RESEARCH"
grep -q "/ed-research.*already authorizes" "$RESEARCH"
grep -q "infer a reasonable scope" "$RESEARCH"

echo "ALL TESTS PASSED"
