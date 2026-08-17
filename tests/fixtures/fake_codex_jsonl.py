#!/usr/bin/env python3
"""Repository-owned fake for codex_jsonl_gate tests; no network or model."""
import json
import os
import sys
import time


behavior = sys.argv[1]
canary = "EDGE_SYNTHETIC_JSONL_SECRET_CANARY"
prompt = sys.stdin.readline().strip()
if prompt != "EDGE_SYNTHETIC_SUPERVISED_PROMPT":
    raise SystemExit(9)


def emit(value):
    print(json.dumps(value), flush=True)


if behavior == "hang":
    time.sleep(10)
    raise SystemExit(0)
if behavior == "overflow":
    print("x" * (70 * 1024), flush=True)
    raise SystemExit(0)
if behavior == "stderr-overflow":
    print("e" * (70 * 1024), file=sys.stderr, flush=True)
    raise SystemExit(0)
if behavior == "malformed":
    print("{bad-json", flush=True)
    raise SystemExit(0)

emit({"type": "thread.started", "thread_id": "synthetic-thread"})
emit({"type": "turn.started"})
emit({"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "hidden"}})
if behavior == "tool":
    emit({"type": "item.completed", "item": {"id": "t", "type": "command_execution"}})
elif behavior == "unknown-item":
    emit({"type": "item.completed", "item": {"id": "u", "type": "future_item"}})
elif behavior == "unknown-event":
    emit({"type": "future.event"})
elif behavior == "secret":
    emit({"type": "item.completed", "item": {"id": "a", "type": "agent_message", "text": canary}})
else:
    emit({"type": "item.completed", "item": {"id": "a", "type": "agent_message", "text": "ok"}})

if behavior != "missing-terminal":
    emit({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
if behavior == "nonzero":
    print("synthetic failure", file=sys.stderr)
    raise SystemExit(7)
