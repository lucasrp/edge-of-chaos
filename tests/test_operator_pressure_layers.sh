#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-pressure-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_STATE="$TMP_BASE/state"
TMP_PROJECT="$TMP_HOME/.claude/projects/test-project"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_PROJECT" "$TMP_STATE"

cat >"$TMP_PROJECT/session-a.jsonl" <<'JSONL'
{"type":"user","timestamp":"2026-04-23T10:00:00Z","sessionId":"session-a","message":{"role":"user","content":"topics deve ser consultado no edge search em todo beat"}}
{"type":"user","timestamp":"2026-04-23T10:05:00Z","sessionId":"session-a","message":{"role":"user","content":"workflow automatico so com orientacao explicita do operador"}}
{"type":"user","timestamp":"2026-04-23T10:10:00Z","sessionId":"session-a","message":{"role":"user","content":"a primitive do exa no ed deveria mencionar deep research"}}
{"type":"user","timestamp":"2026-04-23T10:15:00Z","sessionId":"session-a","message":{"role":"user","content":"eu nao deveria ter que repetir esse passo; isso deveria vir no install"}}
JSONL

cat >"$TMP_PROJECT/session-b.jsonl" <<'JSONL'
{"type":"user","timestamp":"2026-04-23T11:00:00Z","sessionId":"session-b","message":{"role":"user","content":"topics deve ser consultado no edge search em todo beat"}}
{"type":"user","timestamp":"2026-04-23T11:05:00Z","sessionId":"session-b","message":{"role":"user","content":"na verdade workflow automatico sem direcao explicita deve ficar dormente"}}
{"type":"user","timestamp":"2026-04-23T11:10:00Z","sessionId":"session-b","message":{"role":"user","content":"eu fico tendo que pedir para voce usar essa API toda vez"}}
JSONL

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_OPERATOR_PRESSURE_DISABLE_LLM=1

echo "=== operator pressure layers Test ==="
echo ""

echo "--- Test 1: build layers writes ledger, hot digest, and periodic redigest ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_PROJECT" "$TMP_STATE"
import json
import sys
from pathlib import Path

edge_dir, project_dir, state_dir = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared.operator_pressure import build_operator_pressure_layers

state_dir = Path(state_dir)
ledger_path = state_dir / "operator-pressure" / "ledger.json"
atoms_path = state_dir / "operator-pressure" / "pressure-ledger.jsonl"
hot_path = state_dir / "operator-pressure" / "hot-digest.json"
redigest_dir = state_dir / "operator-pressure" / "redigests"

payload = build_operator_pressure_layers(
    project_dir=Path(project_dir),
    ledger_path=ledger_path,
    hot_digest_path=hot_path,
    redigest_dir=redigest_dir,
)

ledger = payload["ledger"]
hot = payload["hot_digest"]
summary = payload["summary"]
latest = json.loads((redigest_dir / "latest.json").read_text(encoding="utf-8"))

assert ledger_path.exists()
assert atoms_path.exists()
assert hot_path.exists()
assert (redigest_dir / "latest.json").exists()
assert ledger["store_kind"] == "operator_pressure_atom_store"
assert ledger["atom_total"] == ledger["item_total"]
assert summary["item_total"] >= 3
assert summary["signal_from_operator_now"] >= 1
assert summary["operator_toil_optimizable_now"] >= 1
assert summary["workflow_candidates"] >= 1
assert summary["capability_candidates"] >= 1
assert summary["substrate_gap_requests"] >= 1
assert summary["atom_entries_appended"] >= 1
assert hot["render_mode"] == "deterministic"
assert hot["signal_from_operator_now"]
assert hot["operator_pains_resolvable_now"]
assert hot["operator_toil_optimizable_now"]
assert hot["mistakes_to_avoid_now"]
assert hot["substrate_gap_requests"]
assert any(item["target"] == "workflow" for item in hot["workflow_candidates"])
assert any(item["target"] == "capability" for item in hot["capability_candidates"])
assert any(item.get("substrate_gap_signal") for item in ledger["atoms"])
assert all(isinstance(entity, dict) for item in ledger["atoms"] for entity in item["entities"])
atom_entries = [json.loads(line) for line in atoms_path.read_text(encoding="utf-8").splitlines() if line.strip()]
assert atom_entries
assert any(entry["substrate_gap_signal"] for entry in atom_entries)
assert "topic" in hot["active_entities"]
assert latest["segments"]
assert latest["source_hash"] == ledger["source_hash"]
assert any(segment["segment_type"] == "operator_pressure_atom" for segment in latest["segments"])
assert any(segment["substrate_gap_signal"] for segment in latest["segments"])
assert all("derived_from_atom_ids" in segment for segment in latest["segments"])
PY
then
    pass "layers write canonical ledger, hot digest, and redigest snapshot"
else
    fail "layers write canonical ledger, hot digest, and redigest snapshot"
fi

echo "--- Test 2: unchanged source hash reuses the hot digest ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_PROJECT" "$TMP_STATE"
import json
import sys
from pathlib import Path

edge_dir, project_dir, state_dir = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared.operator_pressure import build_operator_pressure_layers

state_dir = Path(state_dir)
ledger_path = state_dir / "operator-pressure" / "ledger.json"
hot_path = state_dir / "operator-pressure" / "hot-digest.json"
redigest_dir = state_dir / "operator-pressure" / "redigests"

first = build_operator_pressure_layers(
    project_dir=Path(project_dir),
    ledger_path=ledger_path,
    hot_digest_path=hot_path,
    redigest_dir=redigest_dir,
)
second = build_operator_pressure_layers(
    project_dir=Path(project_dir),
    ledger_path=ledger_path,
    hot_digest_path=hot_path,
    redigest_dir=redigest_dir,
)

assert first["hot_digest"]["digest_hash"] == second["hot_digest"]["digest_hash"]
assert first["summary"]["source_hash"] == second["summary"]["source_hash"]
assert second["summary"]["atom_entries_appended"] == 0
PY
then
    pass "unchanged ledger reuses the cached hot digest"
else
    fail "unchanged ledger reuses the cached hot digest"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
