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
    memory_path=state_dir / "missing-memory.md",
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
    memory_path=state_dir / "missing-memory.md",
    ledger_path=ledger_path,
    hot_digest_path=hot_path,
    redigest_dir=redigest_dir,
)
second = build_operator_pressure_layers(
    project_dir=Path(project_dir),
    memory_path=state_dir / "missing-memory.md",
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

echo "--- Test 2b: changed source hash refreshes redigest inside interval ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import json
import sys
from pathlib import Path

edge_dir, tmp_base = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared.operator_pressure import build_operator_pressure_layers

tmp_base = Path(tmp_base)
project = tmp_base / "redigest-project"
state = tmp_base / "redigest-state"
project.mkdir(parents=True, exist_ok=True)
state.mkdir(parents=True, exist_ok=True)
session = project / "session-redigest.jsonl"
session.write_text(
    '{"type":"user","timestamp":"2026-04-23T10:00:00Z","sessionId":"redigest","message":{"role":"user","content":"workflow automatico so com orientacao explicita do operador"}}\n',
    encoding="utf-8",
)

kwargs = {
    "project_dir": project,
    "memory_path": state / "missing-memory.md",
    "ledger_path": state / "operator-pressure" / "ledger.json",
    "hot_digest_path": state / "operator-pressure" / "hot-digest.json",
    "redigest_dir": state / "operator-pressure" / "redigests",
    "allow_llm": False,
}
first = build_operator_pressure_layers(**kwargs)
latest_path = state / "operator-pressure" / "redigests" / "latest.json"
first_latest = json.loads(latest_path.read_text(encoding="utf-8"))

with session.open("a", encoding="utf-8") as handle:
    handle.write(
        '{"type":"user","timestamp":"2026-04-23T10:01:00Z","sessionId":"redigest","message":{"role":"user","content":"corrija o install do edge e rode heartbeat depois"}}\n'
    )

second = build_operator_pressure_layers(**kwargs)
second_latest = json.loads(latest_path.read_text(encoding="utf-8"))

assert first["ledger"]["source_hash"] != second["ledger"]["source_hash"]
assert first_latest["source_hash"] == first["ledger"]["source_hash"]
assert second_latest["source_hash"] == second["ledger"]["source_hash"]
assert second_latest["snapshot_hash"] != first_latest["snapshot_hash"]
assert second_latest["item_total"] == second["ledger"]["item_total"]
assert len(second_latest["segments"]) == second["ledger"]["item_total"]
PY
then
    pass "changed source hash refreshes redigest inside interval"
else
    fail "changed source hash refreshes redigest inside interval"
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
    memory_path=state_dir / "missing-memory.md",
    projection_path=projection_path,
    write_layers=False,
    allow_llm=False,
)
assert preview["projection_kind"] == "operator_pressure"
assert preview["status"] == "ok"
assert not projection_path.exists()

payload = write_operator_pressure_projection(
    project_dir=Path(project_dir),
    memory_path=state_dir / "missing-memory.md",
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
            "content": "## System\n\nYou are a rigorous, intellectually honest critic. Your job is to find the flaws in the reasoning presented."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:08:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "## System\n\nYou validate claim extraction quality for a continuity graph. Return strict JSON only.\n\n## User\n\n{\"title\":\"demo\"}"
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:09:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "## System\n\nYou are a co-author helping an autonomous AI agent improve a YAML report specification before publication."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:10:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "<task-notification>\n<task-id>demo</task-id>\n<output-file>/tmp/demo.md</output-file>"
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:11:00Z",
        "sessionId": "noise",
        "message": {
            "role": "user",
            "content": "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion."
        },
    },
    {
        "type": "user",
        "timestamp": "2026-05-01T12:12:00Z",
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
    memory_path=state / "missing-memory.md",
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
    "memory_updates",
    "pre_skill_context",
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

echo "--- Test 5b: LLM renderer omits unsupported temperature override ---"
if python3 - <<'PY' "$EDGE_DIR"
import json
import sys
from types import SimpleNamespace

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared import operator_pressure as mod

class FakeCompletions:
    def create(self, **kwargs):
        assert "temperature" not in kwargs, kwargs
        payload = {
            "summary": "operator pressure rendered",
            "signal_from_operator_now": [
                {
                    "item_id": "pressure:demo",
                    "text": "corrija o install do edge",
                    "target": "workflow",
                    "kind": "directive",
                    "repeat_count": 1,
                    "status": "active",
                    "entities": ["workflow"],
                    "source_kinds": ["session"],
                    "last_seen_at": "2026-04-23T10:00:00+00:00",
                }
            ],
            "operator_pains_resolvable_now": [],
            "operator_toil_optimizable_now": [],
            "mistakes_to_avoid_now": [],
            "implicit_needs_hypotheses": [],
            "memory_updates": [],
            "pre_skill_context": [],
            "workflow_candidates": [],
            "capability_candidates": [],
            "substrate_gap_requests": [],
            "active_entities": ["workflow"],
        }
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
            ]
        )

class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()

class FakeClient:
    def __init__(self):
        self.chat = FakeChat()

def fake_client(*_args, **_kwargs):
    return FakeClient(), "gpt-5.4"

mod.LLM_DISABLED = False
mod.make_client = fake_client

ledger = {
    "source_hash": "sha256:demo",
    "item_total": 1,
    "session_total": 1,
    "items": [
        {
            "id": "pressure:demo",
            "content": "corrija o install do edge",
            "target": "workflow",
            "kind": "directive",
            "status": "active",
            "repeat_count": 1,
            "last_seen_at": "2026-04-23T10:00:00+00:00",
            "entities": [{"name": "workflow", "type": "workflow"}],
            "source_kinds": ["session"],
            "explicit_operator_direction": True,
            "scope": "global",
            "substrate_gap_signal": False,
            "substrate_gap_reasons": [],
        }
    ],
}

digest = mod._render_hot_digest_with_llm(ledger, previous_digest=None, delta_items=[])
assert digest["render_mode"] == "gpt-5"
assert digest["model"] == "gpt-5.4"
assert digest["summary"] == "operator pressure rendered"
assert digest["signal_from_operator_now"]
PY
then
    pass "LLM renderer omits unsupported temperature override"
else
    fail "LLM renderer omits unsupported temperature override"
fi

echo "--- Test 6: memory.md updates enter pressure digest as state signals ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import json
import sys
from pathlib import Path

edge_dir, tmp_base = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")

from _shared.operator_pressure import build_operator_pressure_layers, build_operator_pressure_projection

tmp_base = Path(tmp_base)
project = tmp_base / "memory-project"
state = tmp_base / "memory-state"
memory = tmp_base / "memory" / "MEMORY.md"
project.mkdir(parents=True, exist_ok=True)
state.mkdir(parents=True, exist_ok=True)
memory.parent.mkdir(parents=True, exist_ok=True)
(project / "session-empty.jsonl").write_text("", encoding="utf-8")
memory.write_text(
    "- [Report narrative workflow](report-narrative.md) - report sections must introduce dense tables before rendering them\n"
    "- [Pre-skill memory context](pre-skill-memory.md) - memory updates should appear in pre-skill context before execution\n",
    encoding="utf-8",
)

payload = build_operator_pressure_layers(
    project_dir=project,
    memory_path=memory,
    ledger_path=state / "operator-pressure" / "ledger.json",
    hot_digest_path=state / "operator-pressure" / "hot-digest.json",
    redigest_dir=state / "operator-pressure" / "redigests",
    allow_llm=False,
)
ledger = payload["ledger"]
hot = payload["hot_digest"]
summary = payload["summary"]
atoms_path = state / "operator-pressure" / "pressure-ledger.jsonl"
atom_entries = [json.loads(line) for line in atoms_path.read_text(encoding="utf-8").splitlines() if line.strip()]

assert ledger["memory"]["available"] is True
assert ledger["memory"]["item_total"] == 2
assert ledger["source_counts"]["memory"] == 2
assert summary["memory_updates"] >= 1
assert summary["pre_skill_context"] >= 1
assert summary["memory_item_total"] == 2
assert hot["memory_updates"]
assert hot["pre_skill_context"]
assert any("memory" in item.get("source_kinds", []) for item in hot["memory_updates"])
assert any("pre-skill" in item.get("text", "").lower() for item in hot["pre_skill_context"])
assert any("memory" in item.get("source_kinds", []) for item in ledger["items"])
assert any((entry.get("source_kinds") or []) == ["memory"] for entry in atom_entries)
assert any((prov.get("source_kind") == "memory") for item in ledger["items"] for prov in item["provenance"])

projection = build_operator_pressure_projection(
    project_dir=project,
    memory_path=memory,
    projection_path=state / "projections" / "operator-pressure.json",
    write_layers=False,
    allow_llm=False,
)
assert projection["memory"]["available"] is True
assert projection["source_paths"]["memory"] == str(memory)
assert projection["hot_digest"]["memory_updates"]
assert projection["hot_digest"]["pre_skill_context"]
PY
then
    pass "memory.md updates become pressure digest state signals"
else
    fail "memory.md updates become pressure digest state signals"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
