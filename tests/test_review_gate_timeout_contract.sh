#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d /tmp/edge-review-gate-timeout-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat >"$TMP_DIR/spec.yaml" <<'YAML'
title: "Timeout contract"
date: "2026-05-01"
executive_summary: "Validate bounded review-gate router calls"
sections:
  - title: "linhagem"
    content: "test"
  - title: "O que Nao Sei"
    content: "test"
  - title: "glossario"
    content: "test"
YAML

python3 - <<'PY' "$EDGE_DIR" "$TMP_DIR/spec.yaml"
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

edge_dir = Path(sys.argv[1])
spec_path = Path(sys.argv[2])
module_path = edge_dir / "tools" / "review-gate.py"

spec = importlib.util.spec_from_file_location("review_gate_timeout_contract", module_path)
review_gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(review_gate)

calls = []


class FakeUsage:
    prompt_tokens = 7
    completion_tokens = 11
    total_tokens = 18


class FakeChatCompletions:
    def create(self, **kwargs):
        if kwargs.get("response_format") == {"type": "json_object"}:
            content = json.dumps(
                {
                    "dimensions": {
                        name: {"score": 4, "feedback": "ok"}
                        for name in review_gate.DIMENSIONS
                    },
                    "critical_issues": [],
                    "suggestions": [],
                }
            )
        elif kwargs.get("tools"):
            content = json.dumps({"enrichments": []})
        else:
            content = spec_path.read_text(encoding="utf-8")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
            usage=FakeUsage(),
        )


class FakeClient:
    chat = SimpleNamespace(completions=FakeChatCompletions())


def fake_make_client(**kwargs):
    calls.append(kwargs)
    return FakeClient(), "gpt-5.4"


review_gate.make_client = fake_make_client

review_gate.coauthor(str(spec_path))
review_gate.review(str(spec_path))
review_gate.refine(
    str(spec_path),
    {
        "overall": 4,
        "dimensions": {},
        "critical_issues": [],
        "suggestions": [],
    },
)

assert len(calls) == 3, calls
for call in calls:
    assert call["timeout"] == review_gate.REVIEW_GATE_LLM_TIMEOUT, call
    assert call["max_retries"] == 0, call

print("PASS: review-gate router calls are timeout-bounded and non-retrying")
PY
