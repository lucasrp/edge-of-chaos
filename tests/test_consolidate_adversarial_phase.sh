#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-consolidate-rite-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_BIN="$TMP_BASE/bin"
TMP_ENTRY="$TMP_STATE/blog/entries/test-entry.md"
TMP_REPORT="$TMP_STATE/reports/test-spec.yaml"
TEST_LOG="$TMP_BASE/test-consolidate-rite.log"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE"/{blog/entries,reports,logs,state/events,state/runtime,state/audits,health,db,threads,topics,notes,builds,search,config} "$TMP_BIN"

cat >"$TMP_ENTRY" <<'EOF'
---
title: "Test entry"
date: "2026-04-23"
tags: [test, crm]
open_gaps:
  - "Need to verify source consultation"
threads: [test-thread]
---

Test body.
EOF

cat >"$TMP_REPORT" <<'EOF'
title: "Test spec"
subtitle: "Advisory rite smoke"
date: "23/04/2026"
tags: [test, crm]
sections:
  - title: "1. Test"
    content: "Em termos simples, este relatorio testa consulta de fontes, adversarial, Feynman e review."
  - title: "O que Nao Sei"
    content: "Nao sabemos se as fontes externas estao disponiveis."
EOF

cat >"$TMP_BIN/review-gate" <<'EOF'
#!/usr/bin/env python3
import json
import pathlib
import sys

artifact = pathlib.Path(sys.argv[1])
payload = {
  "final_review": {
    "pass": False,
    "overall": 2.1,
    "critical_issues": ["low score should be advisory"],
    "suggestions": ["consult sources and revise"],
    "_meta": {"cost_estimate": "$0.0010"}
  },
  "coauthor": {
    "suggestions": [{"description": "add a gap"}],
    "_meta": {"cost_estimate": "$0.0010"}
  },
  "rounds": []
}
artifact.with_suffix(".feedback.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload))
EOF
chmod +x "$TMP_BIN/review-gate"

cat >"$TMP_BIN/edge-consult" <<'EOF'
#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
gate = None
for i, arg in enumerate(args):
    if arg == "--gate" and i + 1 < len(args):
        gate = pathlib.Path(args[i + 1])
        break
if gate is None:
    print("missing gate path", file=sys.stderr)
    raise SystemExit(2)
gate.with_suffix(".review.json").write_text(json.dumps({
    "timestamp": "2026-04-23T00:00:00+00:00",
    "spec": str(gate),
    "mode": "adversarial",
    "response": "stub adversarial review with source hints",
    "critical_issues": ["check internal continuity"],
    "suggestions": ["search external evidence"],
    "resolved": False
}, indent=2), encoding="utf-8")
print("stub adversarial review")
EOF
chmod +x "$TMP_BIN/edge-consult"

cat >"$TMP_BIN/edge-search" <<'EOF'
#!/usr/bin/env python3
import json
import sys

query = " ".join(arg for arg in sys.argv[1:] if not arg.startswith("-"))
print(json.dumps({
    "mode": "hybrid",
    "query": query,
    "results": [{"path": "memory/MEMORY.md", "type": "note", "title": "Memory", "snippet": "internal result"}],
    "workflows": [],
    "coverage": {}
}))
EOF
chmod +x "$TMP_BIN/edge-search"

cat >"$TMP_BIN/edge-sources" <<'EOF'
#!/usr/bin/env python3
import json

print(json.dumps({
    "exa": [{"title": "External result", "url": "https://example.com", "source": "Exa", "detail": "external", "score": 1}],
    "github": []
}))
EOF
chmod +x "$TMP_BIN/edge-sources"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="rite-test"
export PATH="$TMP_BIN:$PATH"

CONSOLIDATE="$EDGE_DIR/blog/consolidate-state.sh"

echo "=== consolidate-state advisory rite test ==="
echo "Temp state: $TMP_STATE"
echo ""

if "$CONSOLIDATE" "$TMP_ENTRY" "$TMP_REPORT" --review-only >"$TEST_LOG" 2>&1; then
    if python3 - <<'PY' "$TMP_STATE"
import json
import pathlib
import sys

state = pathlib.Path(sys.argv[1])
reports = state / "reports"
slug = "test-entry"
required_paths = [
    reports / f"{slug}.adversarial-r1.review.json",
    reports / f"{slug}.adversarial-r2.review.json",
    reports / f"{slug}.feynman-review.json",
    reports / f"{slug}.review-gate-r1.feedback.json",
    reports / f"{slug}.review-gate-r2.feedback.json",
    reports / f"{slug}.sources-pre_review.json",
    reports / f"{slug}.sources-between_adversarial_reviews.json",
    reports / f"{slug}.sources-between_review_gates.json",
    reports / f"{slug}.rite.json",
]
for path in required_paths:
    assert path.exists(), f"missing {path}"

rite = json.loads((reports / f"{slug}.rite.json").read_text(encoding="utf-8"))
assert rite["status"] == "passed", rite
assert not rite["missing"], rite["missing"]
events = [(e.get("type"), e.get("stage"), e.get("round")) for e in rite["events"]]
expected = [
    ("SourcesConsulted", "pre_review", None),
    ("AdversarialReviewed", "adversarial", 1),
    ("SourcesConsulted", "between_adversarial_reviews", None),
    ("AdversarialReviewed", "adversarial", 2),
    ("FeynmanReviewed", "feynman", None),
    ("ReviewGateCompleted", "review_gate", 1),
    ("SourcesConsulted", "between_review_gates", None),
    ("ReviewGateCompleted", "review_gate", 2),
    ("RiteVerified", "quality_rite", None),
]
cursor = -1
for item in expected:
    for idx in range(cursor + 1, len(events)):
        if events[idx] == item:
            cursor = idx
            break
    else:
        raise AssertionError(f"missing ordered event {item}; events={events}")

for stage in ["pre_review", "between_adversarial_reviews", "between_review_gates"]:
    manifest = json.loads((reports / f"{slug}.sources-{stage}.json").read_text(encoding="utf-8"))
    assert manifest["internal"]["attempted"] is True
    assert manifest["external"]["attempted"] is True
    assert manifest["internal"]["status"] == "completed"
    assert manifest["external"]["status"] == "completed"

round2 = json.loads((reports / f"{slug}.review-gate-r2.feedback.json").read_text(encoding="utf-8"))
assert round2["final_review"]["overall"] == 2.1
assert round2["final_review"]["pass"] is False
PY
    then
        pass "review-only completes full advisory rite despite low score"
    else
        cat "$TEST_LOG"
        fail "review-only completes full advisory rite despite low score"
    fi
else
    cat "$TEST_LOG"
    fail "review-only should not block on score or unresolved marker"
fi

if grep -q "Review-only mode. Nothing published." "$TEST_LOG" \
  && ! grep -q "Adversarial review pending" "$TEST_LOG" \
  && ! grep -q "Review gate failed" "$TEST_LOG"; then
    pass "old score and .resolved blockers are absent"
else
    cat "$TEST_LOG"
    fail "old score and .resolved blockers are absent"
fi

echo ""
echo "=== Results ==="
echo "PASS: $PASS  FAIL: $FAIL"
if [[ "$FAIL" -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
