#!/usr/bin/env bash
# web-search-policy-guard.sh — Claude Code PreToolUse hook for WebSearch/WebFetch
#
# Blocks builtin Claude web search unless runtime policy allows it. The normal
# path is: edge-search for corpus, edge-sources for external search, and only
# then a temporary builtin fallback window if the configured web provider fails.

set -euo pipefail

INPUT="$(cat)"
EDGE_ROOT="${EDGE_REPO_DIR:-${EDGE_DIR:-$HOME/edge}}"

python3 - <<'PY' "$INPUT" "$EDGE_ROOT"
import json
import sys
from pathlib import Path

raw_payload, edge_root = sys.argv[1], sys.argv[2]
try:
    payload = json.loads(raw_payload)
except Exception:
    raise SystemExit(0)

tool_name = str(payload.get("tool_name") or "").strip()
if tool_name not in {"WebSearch", "WebFetch"}:
    raise SystemExit(0)

repo_root = Path(edge_root)
sys.path.insert(0, str(repo_root / "tools"))

try:
    from _shared.search_runtime import load_search_policy, read_builtin_web_search_allowance
except Exception:
    raise SystemExit(0)

if str(payload.get("tool_input", {}).get("query") or "").strip():
    query_hint = str(payload.get("tool_input", {}).get("query") or "").strip()
else:
    query_hint = ""

policy = load_search_policy()
if bool(policy.get("builtin_web_search")):
    raise SystemExit(0)

allowance = read_builtin_web_search_allowance()
if allowance is not None:
    raise SystemExit(0)

provider = str(policy.get("web_provider") or "exa")
fallback = str(policy.get("web_fallback") or "claude_web")
sys.stderr.write(
    "[web-search-policy] BLOCKED: builtin Claude web search is disabled by runtime policy.\n"
    f"  tool: {tool_name}\n"
    f"  query: {query_hint[:160]}\n"
    "  use: edge-search freely for internal corpus recall\n"
    f"  use: edge-sources first for external search (primary provider: {provider})\n"
    f"  fallback: {fallback} unlocks only after provider failure or empty results\n"
)
raise SystemExit(2)
PY
