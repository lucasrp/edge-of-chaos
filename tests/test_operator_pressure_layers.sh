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
export EDGE_OPERATOR_PRESSURE_WINDOW_DAYS=30

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

echo "--- Test 3: CQRS projection wraps the pressure layers ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_PROJECT" "$TMP_STATE"
import json
import sys
from pathlib import Path

edge_dir, project_dir, state_dir = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared.operator_pressure import (
    build_operator_pressure_projection,
    read_operator_pressure_projection,
    write_operator_pressure_projection,
)

state_dir = Path(state_dir)
projection_path = state_dir / "projections" / "operator-pressure.json"

preview = build_operator_pressure_projection(
    project_dir=Path(project_dir),
    projection_path=projection_path,
    write_layers=False,
    allow_llm=False,
)
assert preview["projection_kind"] == "operator_pressure"
assert preview["status"] == "ok"
assert not projection_path.exists()

payload = write_operator_pressure_projection(
    project_dir=Path(project_dir),
    projection_path=projection_path,
    allow_llm=False,
)
stored = read_operator_pressure_projection(projection_path)
assert projection_path.exists()
assert stored["projection_kind"] == "operator_pressure"
assert payload["summary"]["item_total"] >= 3
assert stored["hot_digest"]["signal_from_operator_now"]
assert stored["raw_chat"]["available"] is True
assert stored["source_paths"]["projection"] == str(projection_path)
PY
then
    pass "operator pressure projection supports no-write preview and materialized read model"
else
    fail "operator pressure projection supports no-write preview and materialized read model"
fi

echo "--- Test 4: runtime-injected user messages are excluded from pressure atoms ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import json
import sys
from pathlib import Path

edge_dir, tmp_base = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared.operator_pressure import build_operator_pressure_layers

tmp_base = Path(tmp_base)
project = tmp_base / "noise-project"
state = tmp_base / "noise-state"
project.mkdir(parents=True, exist_ok=True)
state.mkdir(parents=True, exist_ok=True)
session = project / "session-noise.jsonl"
rows = [
    {
        "type": "user",
        "timestamp": "2026-05-01T12:00:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "-\n/ed-research\n\nDispatch runtime context below is authoritative for cross-cutting checks already handled by CLI."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:01:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "Base directory for this skill: /home/vboxuser/.claude/skills/ed-report"
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:02:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "## System\n\nYou are a quality reviewer for report artifacts in this repository."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:03:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "## System\n\nYou compress operator pressure into compact structured JSON for runtime use.\n\n## User\n\nYou are rendering an operator-pressure digest for runtime preflight."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:04:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "You are converting an operator's free-form description of a research or work routine into a structured workflow entry. The operator's prose is verbatim text."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:05:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "You are bootstrapping an autonomous AI agent. Generate seed content for its operational memory.\n\nAgent: roberto"
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:06:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "You are implementing a source primitive for an autonomous agent.\n\nSource: test"
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:07:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "corrija o install do edge e rode heartbeat depois"
        },
    },
]
session.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

payload = build_operator_pressure_layers(
    project_dir=project,
    ledger_path=state / "operator-pressure" / "ledger.json",
    hot_digest_path=state / "operator-pressure" / "hot-digest.json",
    redigest_dir=state / "operator-pressure" / "redigests",
    allow_llm=False,
)
ledger = payload["ledger"]
assert ledger["message_total"] == 1, ledger["message_total"]
assert ledger["item_total"] == 1, ledger["item_total"]
content = ledger["items"][0]["content"]
assert content == "corrija o install do edge e rode heartbeat depois", content
assert "Dispatch runtime context below" not in content
PY
then
    pass "runtime-injected user messages are excluded from pressure atoms"
else
    fail "runtime-injected user messages are excluded from pressure atoms"
fi

echo "--- Test 5: empty ledger skips LLM renderer even with sticky previous digest ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared import operator_pressure as mod

def fail_client(*_args, **_kwargs):
    raise AssertionError("LLM should not be called for empty pressure input")

mod.LLM_DISABLED = False
mod.make_client = fail_client

previous = {
    "schema_version": mod.SCHEMA_VERSION,
    "digest_hash": "sha256:previous",
    "signal_from_operator_now": [
        {"item_id": "pressure:sticky", "text": "sticky directive", "target": "workflow", "kind": "directive"}
    ],
    "operator_pains_resolvable_now": [
        {"item_id": "pressure:pain", "text": "sticky pain", "target": "workflow", "kind": "failure"}
    ],
}
ledger = {
    "source_hash": "sha256:empty",
    "item_total": 0,
    "session_total": 0,
    "items": [],
}
digest = mod._render_hot_digest_with_llm(
    ledger,
    previous_digest=previous,
    delta_items=[
        {"item_id": "pressure:sticky", "text": "sticky directive", "target": "workflow", "kind": "directive"}
    ],
)

assert digest["render_mode"] == "deterministic", digest
assert digest["summary"] == "no strong recent operator pressure detected", digest["summary"]
for key in (
    "signal_from_operator_now",
    "operator_pains_resolvable_now",
    "operator_toil_optimizable_now",
    "mistakes_to_avoid_now",
    "implicit_needs_hypotheses",
    "workflow_candidates",
    "capability_candidates",
    "substrate_gap_requests",
    "active_entities",
    "item_ids",
):
    assert digest[key] == [], (key, digest[key])
assert "render_warning" not in digest
PY
then
    pass "empty ledger skips LLM renderer even with sticky previous digest"
else
    fail "empty ledger skips LLM renderer even with sticky previous digest"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
