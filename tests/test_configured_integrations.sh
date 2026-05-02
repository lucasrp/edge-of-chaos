#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-configured-integrations-XXXXXX)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_BASE/secrets" "$TMP_BASE/state/events"
cat >"$TMP_BASE/secrets/exa.env" <<'EOF'
EXA_API_KEY=test
EOF
cat >"$TMP_BASE/secrets/keys.env" <<'EOF'
BLOG_AUTH_USER=test
BLOG_AUTH_PASS=test
EOF
cat >"$TMP_BASE/secrets/openai.env" <<'EOF'
OPENAI_API_KEY=test
EOF
cat >"$TMP_BASE/secrets/xai.env" <<'EOF'
XAI_API_KEY=test
EOF
cat >"$TMP_BASE/secrets/grafana-loki.env" <<'EOF'
LOKI_URL=http://example.invalid
LOKI_USER=test
LOKI_TOKEN=test
EOF
cat >"$TMP_BASE/secrets/meta.env" <<'EOF'
META_ACCESS_TOKEN=test
EOF
cat >"$TMP_BASE/state/primitives-status.json" <<'JSON'
{"summary": {}, "sources": []}
JSON
: >"$TMP_BASE/state/events/log.jsonl"

echo "=== configured integrations smoke test ==="
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import json
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
tmp_base = Path(sys.argv[2])
sys.path.insert(0, str(edge_dir / "tools"))

from _shared import capability_runtime as cr

cr.SECRETS_DIR = tmp_base / "secrets"
cr.CAPABILITIES_STATUS_FILE = tmp_base / "state" / "capabilities-status.json"
cr.PRIMITIVES_STATUS_FILE = tmp_base / "state" / "primitives-status.json"
cr.STATE_EVENTS_FILE = tmp_base / "state" / "events" / "log.jsonl"

payload = cr.build_configured_integrations(skill="autonomy")
rows = {item["name"]: item for item in payload["configured_integrations"]}
summary = payload["summary"]

assert rows["exa"]["capability_binding"] == "present", json.dumps(rows["exa"], indent=2)
assert rows["meta"]["capability_binding"] == "absent", json.dumps(rows["meta"], indent=2)
assert rows["legacy_keys_bundle"]["capability_binding"] == "not_applicable", json.dumps(rows["legacy_keys_bundle"], indent=2)
assert rows["openai"]["capability_binding"] == "not_applicable", json.dumps(rows["openai"], indent=2)
assert rows["xai"]["capability_binding"] == "not_applicable", json.dumps(rows["xai"], indent=2)
assert rows["grafana"]["capability_binding"] == "not_applicable", json.dumps(rows["grafana"], indent=2)

unbound_names = {item["name"] for item in payload["unbound_integrations"]}
assert unbound_names == {"meta"}, unbound_names
assert summary["integration_total"] == 6, summary
assert summary["bound_total"] == 1, summary
assert summary["unbound_total"] == 1, summary
assert summary["not_applicable_total"] == 4, summary
PY
then
  pass "non-capability integrations are not reported as unbound"
else
  fail "non-capability integrations leaked into unbound integrations"
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
