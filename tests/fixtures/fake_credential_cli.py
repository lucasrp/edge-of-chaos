#!/usr/bin/env python3
"""Fake auth-owning CLI for the hermetic prompt-gate experiment."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


parser = argparse.ArgumentParser()
parser.add_argument("--auth-path", required=True)
parser.add_argument("--tool-path", required=True)
parser.add_argument("--behavior", required=True)
args = parser.parse_args()
auth = Path(args.auth_path)

if args.behavior == "crash-before-ready":
    raise SystemExit(17)
if args.behavior == "malformed-ready":
    print("not-json", flush=True)
    time.sleep(1)
    raise SystemExit(18)
if args.behavior == "ready-before-read":
    print(json.dumps({"event": "ready", "credential_loaded": False}), flush=True)
    time.sleep(1)
    raise SystemExit(19)
if args.behavior == "delay-ready":
    time.sleep(1)

try:
    loaded = bool(auth.read_bytes())
except OSError:
    loaded = False
print(json.dumps({"event": "ready", "credential_loaded": loaded}), flush=True)

line = sys.stdin.readline()
try:
    prompt = json.loads(line)
    prompt_received = prompt == {"event": "prompt", "text": "EDGE_SYNTHETIC_PROMPT_GATE_OPEN"}
except (TypeError, ValueError):
    prompt_received = False

try:
    auth.read_bytes()
    cli_rereadable = True
except OSError:
    cli_rereadable = False

tool = subprocess.run(
    [sys.executable, args.tool_path, str(auth)], capture_output=True, text=True, check=False,
)
try:
    tool_result = json.loads(tool.stdout)
except (TypeError, ValueError):
    tool_result = {"tool_rereadable": True, "tool_process": False}
print(json.dumps({
    "event": "result",
    "prompt_received": prompt_received,
    "cli_rereadable": cli_rereadable,
    "tool_rereadable": tool_result.get("tool_rereadable") is True,
    "tool_process": tool.returncode == 0 and tool_result.get("tool_process") is True,
    "credential_value_returned": False,
}, sort_keys=True), flush=True)
