#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILL="$EDGE_DIR/skills/report/SKILL.md"

echo "=== report skill contract ==="

python3 - <<'PY' "$SKILL"
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")

required = [
    "Bare Invocation / Missing Scope",
    "A bare `/ed-report` dispatch is already authorization to choose a useful",
    "Do not end the skill by asking the operator what topic to use",
    "If no explicit topic, question, or args are present:",
    "`delta_prerequisite`",
    "`beat_launch_context`",
    "`operator_pressure_digest`",
    "`health_snapshot`",
    "`claims_summary`",
    "`exploration_pack`",
    "Select the highest-leverage report target",
    "State the inferred target and why it was selected.",
    "Produce the report artifact.",
    "Ask the operator for a topic only when the runtime frame contains no reasonable",
]
for needle in required:
    assert needle in text, needle
PY

echo "PASS: bare /ed-report must infer scope before asking"
