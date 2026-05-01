#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-runtime-routers-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_RUNTIME="$TMP_BASE/runtime"
TMP_STATE="$TMP_BASE/state"
TMP_CONFIG="$TMP_BASE/agent.yaml"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_HOME" "$TMP_RUNTIME" "$TMP_STATE"

cat >"$TMP_CONFIG" <<YAML
name: Router Runtime Test
codename: router-runtime-test
skill_prefix: rrt
mission: Validate runtime router materialization
voice: Direct and factual
domain: testing
edge_home: $TMP_STATE
blog_port: 8766
onboarding_mode: true
routers:
  chat:
    base_url: https://api.openai.com/v1
    secret_ref: openai.env:OPENAI_API_KEY
    model: gpt-5.4
  review:
    base_url: https://api.x.ai/v1
    secret_ref: xai.env:XAI_API_KEY
    model: grok-4.20-multi-agent-beta-0309
YAML

export HOME="$TMP_HOME"

echo "=== runtime router config Smoke Test ==="
echo "Temp base: $TMP_BASE"
echo ""

echo "--- Test 1: edge-render materializes runtime-routers.yaml ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG" "$TMP_BASE"
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

import yaml

edge_dir, config_path, tmp_base = sys.argv[1:]
repo = Path(tmp_base) / "render-repo"
(repo / "config").mkdir(parents=True, exist_ok=True)
(repo / "config" / "runtime-routers.yaml.tpl").write_text("{{ RUNTIME_ROUTERS_FILE }}\n", encoding="utf-8")
(repo / "config" / "postflight.yaml.tpl").write_text("{{ POSTFLIGHT_PROTOCOL_YAML }}\n", encoding="utf-8")

os.environ["EDGE_STATE_DIR"] = str(Path(tmp_base) / "render-state")
os.environ["EDGE_CYCLE_ID"] = "install:test-runtime-routers-render"
os.environ["EDGE_CODENAME"] = "router-runtime-test"

loader = importlib.machinery.SourceFileLoader("edge_render_mod", f"{edge_dir}/tools/edge-render")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

cfg = mod.load_agent_yaml(Path(config_path))
assert cfg["memory_project_dir"] == str(Path(cfg["edge_home_expanded"]).resolve()).rstrip("/").replace("/", "-")
assert cfg["memory_project_dir"].startswith("-"), cfg["memory_project_dir"]
placeholders = mod.build_placeholder_map(cfg)
mod.render_all(repo, placeholders, dry_run=False)

payload = yaml.safe_load((repo / "config" / "runtime-routers.yaml").read_text(encoding="utf-8"))
assert payload["routers"]["review"]["base_url"] == "https://api.x.ai/v1"
assert payload["routers"]["chat"]["model"] == "gpt-5.4"
postflight = yaml.safe_load((repo / "config" / "postflight.yaml").read_text(encoding="utf-8"))
assert any(item["kind"] == "source_affordance.digest" for item in postflight["procedures"])
assert any(item["kind"] == "pipeline_state.refresh" for item in postflight["procedures"])
PY
then
    pass "edge-render materializes runtime routers and projection postflight"
else
    fail "edge-render materializes runtime routers and projection postflight"
fi

echo "--- Test 2: router_client reads runtime routers without agent.yaml ---"
mkdir -p "$TMP_RUNTIME/config" "$TMP_RUNTIME/secrets" "$TMP_RUNTIME/blog" "$TMP_RUNTIME/tools"
cat >"$TMP_RUNTIME/config/branding.yaml" <<YAML
agent_name: "Router Runtime Test"
codename: "router-runtime-test"
skill_prefix: "rrt"
edge_state_dir: "$TMP_STATE"
blog:
  port: 8766
  host: "127.0.0.1"
YAML
cat >"$TMP_RUNTIME/config/runtime-routers.yaml" <<'YAML'
routers:
  chat:
    base_url: https://api.openai.com/v1
    secret_ref: openai.env:OPENAI_API_KEY
    model: gpt-5.4
  review:
    base_url: https://api.x.ai/v1
    secret_ref: xai.env:XAI_API_KEY
    model: grok-4.20-multi-agent-beta-0309
YAML
cat >"$TMP_RUNTIME/secrets/openai.env" <<'ENV'
OPENAI_API_KEY=test-openai-key
ENV
cat >"$TMP_RUNTIME/secrets/xai.env" <<'ENV'
XAI_API_KEY=test-xai-key
ENV

if EDGE_REPO_DIR="$TMP_RUNTIME" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="router-runtime-test" python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.router_client import find_router_for_model, load_router_config

review = load_router_config("review")
assert review["base_url"] == "https://api.x.ai/v1"
assert review["model"] == "grok-4.20-multi-agent-beta-0309"
name, chat = find_router_for_model("gpt-5.4")
assert name == "chat"
assert chat["secret_ref"] == "openai.env:OPENAI_API_KEY"
PY
then
    pass "router_client reads runtime router config without agent.yaml"
else
    fail "router_client reads runtime router config without agent.yaml"
fi

echo "--- Test 3: edge-doctor uses runtime branding by default ---"
mkdir -p \
    "$TMP_RUNTIME/config" \
    "$TMP_RUNTIME/secrets" \
    "$TMP_RUNTIME/blog/.venv/bin" \
    "$TMP_RUNTIME/tools/.venv/bin" \
    "$TMP_STATE/blog/entries" \
    "$TMP_STATE/reports" \
    "$TMP_STATE/logs" \
    "$TMP_STATE/health/raw" \
    "$TMP_STATE/health/last_success" \
    "$TMP_HOME/.claude"
touch "$TMP_HOME/.claude/CLAUDE.md"
touch "$TMP_RUNTIME/config/preflight.yaml" "$TMP_RUNTIME/config/postflight.yaml" "$TMP_RUNTIME/config/strategy.md"
touch "$TMP_RUNTIME/blog/.venv/bin/python3" "$TMP_RUNTIME/tools/.venv/bin/python3"
cat >"$TMP_RUNTIME/secrets/keys.env" <<'ENV'
OPENAI_API_KEY=test-openai-key
ENV

set +e
EDGE_REPO_DIR="$TMP_RUNTIME" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="router-runtime-test" EDGE_CYCLE_ID="install:test-runtime-doctor" \
    python3 "$EDGE_DIR/tools/edge-doctor" >/dev/null
DOCTOR_STATUS=$?
set -e

if python3 - <<'PY' "$TMP_STATE/state/events/log.jsonl"
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
checks = [
    event for event in events
    if event.get("cycle_id") == "install:test-runtime-doctor" and event.get("type") == "InstallCheckObserved"
]
assert checks, "expected InstallCheckObserved events from edge-doctor"
check_ids = {event["payload"].get("check_id") for event in checks}
assert "file:runtime-routers-yaml" in check_ids
assert "config:agent-yaml" not in check_ids
PY
then
    pass "edge-doctor uses runtime branding by default (exit=$DOCTOR_STATUS)"
else
    fail "edge-doctor uses runtime branding by default"
fi

echo "--- Test 4: router_client falls back to local Claude CLI on remote failure ---"
if EDGE_REPO_DIR="$TMP_RUNTIME" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="router-runtime-test" python3 - <<'PY' "$EDGE_DIR"
import sys
from types import SimpleNamespace

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")
import _shared.router_client as rc

class FailingResource:
    def create(self, *args, **kwargs):
        raise RuntimeError("429 insufficient_quota")

class DummyClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FailingResource())
        self.responses = FailingResource()
        self.embeddings = FailingResource()

rc.claude_cli_available = lambda: True
rc.call_claude_cli_text = lambda prompt, timeout=60: "claude fallback ok"

client = rc._wrap_with_telemetry(DummyClient(), "review", "gpt-5.4", 30)
chat = client.chat.completions.create(
    model="gpt-5.4",
    messages=[
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
    ],
)
assert chat.choices[0].message.content == "claude fallback ok"
assert chat.usage.prompt_tokens == 0

resp = client.responses.create(
    model="gpt-5.4",
    input=[
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
    ],
    tools=[{"type": "web_search_preview"}],
)
assert resp.output_text == "claude fallback ok"
assert resp.usage.input_tokens == 0
assert resp.output[0].type == "message"
PY
then
    pass "router_client falls back to local Claude CLI on remote failure"
else
    fail "router_client falls back to local Claude CLI on remote failure"
fi

echo "--- Test 5: router_client falls back when external client cannot be configured ---"
if EDGE_REPO_DIR="$TMP_RUNTIME" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="router-runtime-test" python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE/logs/events.jsonl"
import json
import sys
from pathlib import Path

edge_dir = sys.argv[1]
events_path = Path(sys.argv[2])
sys.path.insert(0, f"{edge_dir}/tools")
import _shared.router_client as rc

rc.claude_cli_available = lambda: True
rc.call_claude_cli_text = lambda prompt, timeout=60: "configured fallback ok"

def missing_secret(_secret_ref):
    raise RuntimeError("Secret OPENAI_API_KEY not found")

rc.load_secret = missing_secret

client, model = rc.make_client("chat", timeout=30)
assert model in {"gpt-5.4", "claude-cli"}
chat = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
    ],
)
assert chat.choices[0].message.content == "configured fallback ok"
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
degraded = [event for event in events if event.get("type") == "llm_provider_degraded"]
assert any(event.get("fallback") == "claude-cli" for event in degraded)

try:
    rc.make_client("embedding", timeout=30)
except RuntimeError as exc:
    assert "Secret OPENAI_API_KEY not found" in str(exc) or "openai package is required" in str(exc)
else:
    raise AssertionError("embedding client should not fall back to Claude CLI")
PY
then
    pass "router_client falls back when external client cannot be configured"
else
    fail "router_client falls back when external client cannot be configured"
fi

echo "--- Test 6: review-gate uses Claude fallback when API secrets are absent ---"
rm -f "$TMP_RUNTIME/secrets/openai.env" "$TMP_RUNTIME/secrets/xai.env"
mkdir -p "$TMP_HOME/.local/bin" "$TMP_STATE/reports"
cat >"$TMP_HOME/.local/bin/claude" <<'SH'
#!/usr/bin/env bash
cat <<'JSON'
{
  "pass": true,
  "overall": 4.0,
  "dimensions": {
    "structural_completeness": {"score": 4, "feedback": "fallback ok"},
    "content_depth": {"score": 4, "feedback": "fallback ok"},
    "storytelling": {"score": 4, "feedback": "fallback ok"},
    "feynman_method": {"score": 4, "feedback": "fallback ok"},
    "writing_quality": {"score": 4, "feedback": "fallback ok"},
    "visualization": {"score": 4, "feedback": "fallback ok"},
    "intellectual_honesty": {"score": 4, "feedback": "fallback ok"},
    "internal_consistency": {"score": 4, "feedback": "fallback ok"},
    "didactic_clarity": {"score": 4, "feedback": "fallback ok"}
  },
  "critical_issues": [],
  "suggestions": []
}
JSON
SH
chmod +x "$TMP_HOME/.local/bin/claude"
cat >"$TMP_STATE/reports/fallback-spec.yaml" <<'YAML'
title: "Fallback spec"
date: "25/04/2026"
executive_summary: "Validate fallback"
metrics: []
sections:
  - title: "linhagem"
    content: "test"
  - title: "O que Nao Sei"
    content: "test"
  - title: "glossario"
    content: "test"
bibliography: []
YAML
if EDGE_REPO_DIR="$TMP_RUNTIME" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="router-runtime-test" EDGE_CLAUDE_BIN="$TMP_HOME/.local/bin/claude" \
    python3 "$EDGE_DIR/tools/review-gate.py" "$TMP_STATE/reports/fallback-spec.yaml" --review-only --json >/tmp/test-review-gate-fallback.json 2>/tmp/test-review-gate-fallback.err
then
    if python3 - <<'PY' /tmp/test-review-gate-fallback.json
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
review = payload["final_review"]
assert review["_meta"]["model"] in {"gpt-5.4", "claude-cli"}
assert review["_meta"]["tokens"]["total"] == 0
assert review["overall"] >= 3.5
PY
    then
        pass "review-gate uses Claude fallback when API secrets are absent"
    else
        cat /tmp/test-review-gate-fallback.err
        fail "review-gate uses Claude fallback when API secrets are absent"
    fi
else
    cat /tmp/test-review-gate-fallback.err
    fail "review-gate uses Claude fallback when API secrets are absent"
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
