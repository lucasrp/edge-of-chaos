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
    "`open_gaps_summary`",
    "`exploration_pack`",
    "Select the highest-leverage report target",
    "State the inferred target and why it was selected.",
    "Produce the report artifact.",
    "Ask the operator for a topic only when the runtime frame contains no reasonable",
    "If the runtime frame yields one or more candidates, choose the strongest one",
    "must not finish with candidate options instead of an",
    "What topic do you want",
    "A few candidates",
    "must name the published blog entry and HTML report paths",
]
for needle in required:
    assert needle in text, needle
PY

echo "PASS: bare /ed-report must infer scope before asking"
