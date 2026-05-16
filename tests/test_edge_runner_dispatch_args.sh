#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== edge-runner dispatch args contract ==="
echo ""

echo "--- Test 1: runner forwards request args when opening a dispatch cycle ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_runner", str(edge_dir / "tools" / "edge-runner"))
spec = importlib.util.spec_from_loader("edge_runner", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

parser = module.build_parser()
args = parser.parse_args(
    [
        "skill",
        "--skill",
        "/ed-planner",
        "--dispatch-trigger",
        "user",
        "--dispatch-policy",
        "operator",
        "--dispatch-routing-mode",
        "explicit",
        "--dispatch-preflight-profile",
        "operator_default",
        "--dispatch-postflight-profile",
        "standard",
        "--arg",
        "prompt=evoluir crm no front end",
        "--arg",
        "thread_id=planner-test",
        "--args-json",
        '{"focus":"crm"}',
        "--dispatch-force",
    ]
)
module.infer_dispatch_defaults(args)

captured = []

def fake_run_edge_tool(tool_name, tool_args, env, *, allow_nonzero=False):
    captured.append((tool_name, list(tool_args), dict(env), allow_nonzero))
    return 0, {}

module.run_edge_tool = fake_run_edge_tool
module.make_cycle_id = lambda: "cycle-args-test"
env = {}
cycle_id = module.maybe_open_cycle(args, env)

assert cycle_id == "cycle-args-test"
assert env["EDGE_CYCLE_ID"] == "cycle-args-test"
assert len(captured) == 1
tool_name, tool_args, captured_env, allow_nonzero = captured[0]
assert tool_name == "edge-dispatch"
assert allow_nonzero is False
assert captured_env["EDGE_CYCLE_ID"] == "cycle-args-test"
assert tool_args == [
    "open",
    "--trigger",
    "user",
    "--cycle-id",
    "cycle-args-test",
    "--skill",
    "ed-planner",
    "--policy",
    "operator",
    "--routing-mode",
    "explicit",
    "--preflight-profile",
    "operator_default",
    "--postflight-profile",
    "standard",
    "--arg",
    "prompt=evoluir crm no front end",
    "--arg",
    "thread_id=planner-test",
    "--args-json",
    '{"focus":"crm"}',
    "--force",
]
PY
then
    pass "runner forwards --arg and --args-json to edge-dispatch open"
else
    fail "runner forwards --arg and --args-json to edge-dispatch open"
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
