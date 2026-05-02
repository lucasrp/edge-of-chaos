#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-postflight-resilience-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/state/projections" "$TMP_EDGE/logs" "$TMP_EDGE/search"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="postflight-resilience-test"

echo "=== edge-postflight resilience Test ==="
echo ""

echo "--- Test 1: postflight step exception degrades to warning instead of aborting ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

original_protocol = module.ensure_compiled_protocol
original_execute = module._execute_postflight_step
original_before = module.before_snapshot
original_compute = module.compute_delta
try:
    module.ensure_compiled_protocol = lambda _stage: {
        "source_hash": "sha256:test",
        "compiled_hash": "sha256:test",
        "context_notes": [],
        "operator_notes": [],
        "procedures": [{"id": "boom", "kind": "validate.recent"}],
    }
    module._execute_postflight_step = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    module.before_snapshot = lambda _state: {
        "claims_open_total": 0,
        "orphans_total": 0,
        "primitive_broken_total": 0,
        "primitive_degraded_total": 0,
        "capability_broken_total": 0,
        "capability_degraded_total": 0,
        "workflow_broken_total": 0,
        "workflow_stale_total": 0,
    }
    module.compute_delta = lambda before, **_kwargs: {"claims_open_delta": 0}
    state = {"cycle_id": "cycle-postflight", "request": {"skill": "research"}, "state": {}}
    ok, postflight_status, reason, steps, delta = module.run_standard(state, "standard")
    assert ok is True
    assert postflight_status == "warning"
    assert reason == "postflight_step_warning"
    assert steps[0]["status"] == "warning"
    assert steps[0]["failure_mode"] == "exception"
    assert delta["claims_open_delta"] == 0
finally:
    module.ensure_compiled_protocol = original_protocol
    module._execute_postflight_step = original_execute
    module.before_snapshot = original_before
    module.compute_delta = original_compute
PY
then
    pass "postflight exceptions degrade to warning instead of aborting"
else
    fail "postflight exceptions degrade to warning instead of aborting"
fi

echo "--- Test 2: async inbox postflight responds before consuming captured chat ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "search"))
from dashboard_db import add_chat, get_chats

loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

captured_id = add_chat("user", "Please use the async dashboard input in this cycle.")
late_id = add_chat("user", "This arrived after dispatch and should stay pending.")
state = {
    "cycle_id": "cycle-postflight-inbox",
    "request": {
        "skill": "research",
        "async_inbox": {
            "skill": "research",
            "message_ids": [captured_id],
            "direct_messages": [{
                "chat_id": captured_id,
                "author": "user",
                "text": "Please use the async dashboard input in this cycle.",
                "preview": "Please use the async dashboard input in this cycle.",
            }],
            "task_intents": [],
            "steering_intents": [],
            "runtime_intents": [],
            "pinned_messages": [],
        },
    },
    "state": {},
}

result = module._execute_postflight_step(
    {"id": "async-inbox-response", "kind": "async_inbox.respond"},
    state,
)
messages = get_chats(limit=20)
by_id = {int(item["id"]): item for item in messages}
replies = [
    item for item in messages
    if item["author"] == "system" and "Processed async dashboard input" in item["text"]
]

assert result["status"] == "ok"
assert result["satisfied"] is True
assert by_id[captured_id]["processed"] == 1
assert by_id[late_id]["processed"] == 0
assert replies
assert "cycle-postflight-inbox" in replies[-1]["text"]
assert replies[-1]["processed"] == 1
assert state["request"]["async_inbox"]["response_chat_id"] == replies[-1]["id"]
assert state["request"]["async_inbox"]["response_processed"] is True
assert state["request"]["async_inbox"]["processed_message_ids"] == [captured_id]
PY
then
    pass "async inbox response is written before captured messages are consumed"
else
    fail "async inbox response is written before captured messages are consumed"
fi

echo "--- Test 3: async inbox response failure is a warning step ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

original_ack = module.acknowledge_captured_inbox
try:
    module.acknowledge_captured_inbox = lambda _state: {
        "ok": False,
        "detail": "dashboard unavailable",
        "reply_posted": False,
        "processed_count": 0,
        "captured_total": 1,
    }
    result = module._execute_postflight_step(
        {"id": "async-inbox-response", "kind": "async_inbox.respond"},
        {"request": {"skill": "research", "async_inbox": {"message_ids": [1]}}, "state": {}},
    )
    assert result["status"] == "warning"
    assert result["satisfied"] is False
    assert result["payload"]["processed_count"] == 0
finally:
    module.acknowledge_captured_inbox = original_ack
PY
then
    pass "async inbox response failures degrade to warning"
else
    fail "async inbox response failures degrade to warning"
fi

echo "--- Test 4: claims refresh uses cached projections without continuity rebuild ---"
if python3 - <<'PY' "$EDGE_DIR"
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
loader = importlib.machinery.SourceFileLoader("edge_postflight", str(edge_dir / "tools" / "edge-postflight"))
spec = importlib.util.spec_from_loader("edge_postflight", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

assert not hasattr(module, "refresh_continuity_projections")
module.CLAIMS_DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
module.CLAIMS_DIGEST_FILE.write_text(
    json.dumps({"open_total": 3, "verified_total": 7, "unthreaded_count": 1}),
    encoding="utf-8",
)
module.ORPHAN_CLAIMS_FILE.write_text(
    json.dumps({"orphan_total": 2, "open_orphan_total": 1}),
    encoding="utf-8",
)

result = module._execute_postflight_step(
    {"id": "claims", "kind": "claims.refresh"},
    {"cycle_id": "cycle-postflight-claims", "request": {}, "state": {}},
)

assert result["status"] == "ok", result
assert result["satisfied"] is True, result
assert result["payload"]["digest"]["open_total"] == 3
assert result["payload"]["orphans"]["orphan_total"] == 2
assert result["payload"]["cache"]["status"] == "cached"
PY
then
    pass "claims refresh reads cached projection files"
else
    fail "claims refresh reads cached projection files"
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
