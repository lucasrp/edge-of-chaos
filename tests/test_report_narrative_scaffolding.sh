#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d /tmp/edge-report-narrative-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEMPLATE="$EDGE_DIR/skills/_shared/report-template.md"
REPORT_SKILL="$EDGE_DIR/skills/report/SKILL.md"
REVIEW_GATE="$EDGE_DIR/tools/review-gate.py"

echo "=== report narrative scaffolding contract ==="

grep -q "Golden Rule 1: Narrative Scaffolding" "$TEMPLATE"
grep -q "section has a \`lead\` with 2-4 concrete sentences" "$TEMPLATE"
grep -q "Do not compensate for narrative leads by deleting evidence" "$TEMPLATE"
grep -q "Each section should open with a short narrative lead" "$REPORT_SKILL"
grep -q "Do not pay for narrative scaffolding by deleting sources" "$REPORT_SKILL"
grep -q "Any non-reference section begins directly with a table" "$REVIEW_GATE"
grep -q "Do not make these additions by weakening analysis" "$REVIEW_GATE"

GOOD="$TMP_DIR/good.yaml"
cat >"$GOOD" <<'YAML'
title: "Runtime Dispatch Report"
subtitle: "Narrative lead smoke test"
date: "02/05/2026"
executive_summary:
  - "**Finding:** lead text frames the evidence before tables."
metrics:
  - value: "1"
    label: "Narrative lead rendered"
sections:
  - title: "1. Linhagem"
    lead: >
      This section explains why the report exists before showing prior work.
      The table is a compact evidence map rather than a substitute for the
      argument.
    blocks:
      - type: table
        headers: ["Previous Action", "What It Brought", "Connection to This Work"]
        rows:
          - ["Heartbeat validation", "Long-running cycles completed", "Report needs better reader guidance"]
      - type: paragraph
        text: >
          The practical reading is that the artifact should make dense evidence
          legible without removing the evidence itself.
  - title: "O que Nao Sei"
    lead: >
      This section keeps uncertainty visible. It distinguishes missing evidence
      from known defects so the report does not overclaim.
    blocks:
      - type: gap-table
        gaps:
          - id: "gap-1"
            description: "Whether every skill-specific prompt will honor the new lead rule"
            need: "Fleet validation over real reports"
            status: "open"
      - type: paragraph
        text: "The unresolved question is behavioral adoption, not renderer support."
  - title: "Contextualization and Glossary"
    lead: >
      This report is for operators reading autonomous runtime artifacts. It
      defines the terms needed to inspect a report without knowing the pipeline.
    blocks:
      - type: glossary
        context: "Runtime report vocabulary."
        terms:
          - term: "lead"
            definition: "Short narrative bridge between a section title and dense evidence."
bibliography:
  - text: "Local report template"
    source: "Repo"
YAML

python3 "$EDGE_DIR/tools/yaml_to_html.py" "$GOOD" --output "$TMP_DIR/good.html" >/dev/null
grep -q 'class="section-lead"' "$TMP_DIR/good.html"
grep -q "This section explains why the report exists" "$TMP_DIR/good.html"

BAD="$TMP_DIR/bad.yaml"
cat >"$BAD" <<'YAML'
title: "Runtime Dispatch Report"
subtitle: "Missing lead smoke test"
date: "02/05/2026"
executive_summary:
  - "**Finding:** this should fail."
metrics:
  - value: "0"
    label: "Narrative leads"
sections:
  - title: "1. Linhagem"
    blocks:
      - type: table
        headers: ["Previous Action", "What It Brought", "Connection to This Work"]
        rows:
          - ["Heartbeat validation", "Completed", "Needs narrative"]
bibliography:
  - text: "Local report template"
    source: "Repo"
YAML

if python3 "$EDGE_DIR/tools/yaml_to_html.py" "$BAD" --output "$TMP_DIR/bad.html" >"$TMP_DIR/bad.out" 2>"$TMP_DIR/bad.err"; then
  echo "FAIL: table-first section without lead should be blocked" >&2
  exit 1
fi
grep -q "sem lead narrativo" "$TMP_DIR/bad.err"

echo "PASS: report sections require narrative scaffolding before dense evidence"
