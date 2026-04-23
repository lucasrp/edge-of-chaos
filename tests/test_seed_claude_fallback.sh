#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-seed-fallback-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_EDGE="$TMP_BASE/agent"
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

mkdir -p "$TMP_HOME" "$TMP_EDGE/secrets" "$TMP_STATE"

cat >"$TMP_CONFIG" <<YAML
name: Seed Fallback Test
codename: seed-fallback-test
skill_prefix: sft
mission: Validate Claude CLI seed fallback
voice: Direct and factual
domain: testing
short_term_goal: Validate install fallback path
edge_home: $TMP_EDGE
blog_port: 8766
onboarding_mode: true
interests:
  - area: Observability
    connection: Track what the system is really doing
YAML

cat >"$TMP_EDGE/secrets/openai.env" <<'ENV'
OPENAI_API_KEY=fake-openai-key
ENV

echo "=== seed Claude fallback Smoke Test ==="
echo "Temp base: $TMP_BASE"
echo ""

echo "--- Test 1: phase_seed falls back to local Claude CLI before deterministic seed ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG" "$TMP_HOME" "$TMP_EDGE" "$TMP_STATE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

edge_dir, config_path, home_dir, edge_home, state_dir = sys.argv[1:]
os.environ["HOME"] = home_dir
os.environ["EDGE_STATE_DIR"] = state_dir
os.environ["EDGE_CODENAME"] = "seed-fallback-test"
os.environ["EDGE_CYCLE_ID"] = "install:test-seed-claude-fallback"

loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

import urllib.request
sys.path.insert(0, f"{edge_dir}/tools")
import _shared.router_client as router_client

def fail_remote(*args, **kwargs):
    raise RuntimeError("429 insufficient_quota")

urllib.request.urlopen = fail_remote
router_client.call_claude_cli_text = lambda prompt, timeout=60: json.dumps(
    {
        "strategy": ["Use runtime facts before prose"],
        "autonomy": ["!Need GitHub access"],
        "friction": ["!Remote quota can fail during seed"],
        "serendipity": ["Claude fallback is available locally"],
        "reflection": ["Bootstrap can still progress with local CLI"],
        "threads": [
            {
                "id": "runtime-fallbacks",
                "title": "Runtime fallbacks",
                "description": "Keep local fallbacks alive when providers fail",
                "status": "active",
            }
        ],
        "briefing": "# Briefing\n\nFallback worked.\n\n<!-- SYNTHETIC — replace on first /ed-strategy run -->",
    }
)

cfg = mod.load_config(Path(config_path))
assert mod.phase_seed(cfg, dry_run=False) is True

strategy = (Path(edge_home) / "state" / "signals" / "strategy.md").read_text(encoding="utf-8")
briefing = (Path(edge_home) / "briefing.md").read_text(encoding="utf-8")
thread = (Path(edge_home) / "threads" / "runtime-fallbacks.md").read_text(encoding="utf-8")

assert "Use runtime facts before prose" in strategy
assert "Fallback worked." in briefing
assert "Runtime fallbacks" in thread
PY
then
    pass "phase_seed falls back to local Claude CLI before deterministic seed"
else
    fail "phase_seed falls back to local Claude CLI before deterministic seed"
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
