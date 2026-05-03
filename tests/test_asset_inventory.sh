#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-asset-inventory-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
TMP_STATE="$TMP_BASE/state"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_REPO/secrets" "$TMP_STATE/state/operator-pressure" "$TMP_HOME/.ssh" "$TMP_HOME/project" "$TMP_HOME/data"

cat >"$TMP_REPO/secrets/keys.env" <<'ENV'
WA_ACCESS_TOKEN=super-secret-wa-token
OPENAI_API_KEY=super-secret-openai-token
META_APP_ID=123
ENV

cat >"$TMP_HOME/.ssh/config" <<'SSH'
Host bobmarley
  HostName 203.0.113.10
  User edge

Host *
  ForwardAgent no
SSH

cat >"$TMP_STATE/state/operator-pressure/hot-digest.json" <<'JSON'
{
  "signal_from_operator_now": [
    {"text": "criei TELEGRAM_BOT_TOKEN no ssh gauss para o servico na porta 9000 usando leads.db"}
  ]
}
JSON

git -C "$TMP_HOME/project" init -q
git -C "$TMP_HOME/project" remote add origin git@github.com:lucasrp/example.git

python3 - <<'PY' "$TMP_HOME/data/leads.db"
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE leads(id INTEGER PRIMARY KEY, name TEXT)")
conn.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, body TEXT)")
conn.commit()
conn.close()
PY

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="asset-test"
export EDGE_ASSET_REPO_SCAN_ROOTS="$TMP_HOME/project"
export EDGE_ASSET_DB_SCAN_ROOTS="$TMP_HOME/data"

TOOL="$EDGE_DIR/tools/rollup-asset-inventory.sh"

echo "=== asset inventory Smoke Test ==="
echo "Temp state: $TMP_STATE"
echo ""

echo "--- Test 1: rollup discovers local repos, DB schemas, SSH hosts, and key names only ---"
if "$TOOL" --no-ssh --json >"$TMP_BASE/inventory.json" \
    && python3 - <<'PY' "$TMP_BASE/inventory.json" "$TMP_STATE/state/asset-inventory.json"
import json
import sys
from pathlib import Path

payload = json.load(open(sys.argv[1], encoding="utf-8"))
stored = json.load(open(sys.argv[2], encoding="utf-8"))
text = Path(sys.argv[2]).read_text(encoding="utf-8")

assert payload == stored
assert payload["schema_version"] == 1
assert payload["security"]["stores_secret_values"] is False
assert payload["security"]["keys_are_names_only"] is True
assert "super-secret" not in text
assert payload["keys"]["whatsapp"] == ["WA_ACCESS_TOKEN"]
assert payload["keys"]["openai"] == ["OPENAI_API_KEY"]
assert payload["keys"]["meta"] == ["META_APP_ID"]
assert payload["keys"]["telegram"] == ["TELEGRAM_BOT_TOKEN"]
assert "bobmarley" in payload["hosts"]
assert payload["hosts"]["bobmarley"]["ssh_status"] == "skipped"
assert payload["hosts"]["gauss"]["ssh_status"] == "skipped"
assert payload["operator_pressure_updates"]["ports"] == [9000]
assert payload["operator_pressure_updates"]["databases"] == ["leads.db"]
dbs = payload["hosts"]["localhost"]["databases"]
assert any(item["path"].endswith("leads.db") and item["tables"] == ["leads", "messages"] for item in dbs)
repos = payload["hosts"]["localhost"]["repos"]
assert any(item["remote"] == "git@github.com:lucasrp/example.git" for item in repos)
summary = payload["summary"]
assert summary["host_total"] == 3
assert summary["database_total"] >= 1
assert summary["repo_total"] >= 1
assert summary["key_total"] == 4
PY
then
    pass "rollup discovers assets without storing secret values"
else
    fail "rollup discovers assets without storing secret values"
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
