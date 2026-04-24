#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-render-drift-XXXXXX)"
TMP_EDGE="$TMP_BASE/agent"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/state/events" "$TMP_EDGE/install"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="telemetry-test"

TOOL="$EDGE_DIR/tools/rollup-render-install-drift.py"
OUT="$TMP_EDGE/state/render-install-drift.json"

echo "=== render-install-drift Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

python3 - <<'PY' "$TMP_EDGE"
import json
import sys
from pathlib import Path

edge = Path(sys.argv[1])
good = edge / "install" / "claude.md"
good.write_text("same", encoding="utf-8")
mismatch = edge / "install" / "paths.py"
mismatch.write_text("installed", encoding="utf-8")
in_place = edge / "install" / "in-place.md"
in_place.write_text("same", encoding="utf-8")
superseded = edge / "install" / "seeded.md"
superseded.write_text("seeded", encoding="utf-8")
events = [
    {
        "ts": "2026-04-20T20:00:00+00:00",
        "type": "RenderProduced",
        "artifact": "/repo/config/CLAUDE.md",
        "payload": {
            "source_template": "config/CLAUDE.md.tpl",
            "output_path": "config/CLAUDE.md",
            "hash": "sha256:same",
            "residual_count": 0,
        },
    },
    {
        "ts": "2026-04-20T20:01:00+00:00",
        "type": "InstallApplied",
        "artifact": str(good),
        "payload": {
            "source_template": "config/CLAUDE.md",
            "hash": "sha256:same",
            "kind": "file",
            "action": "copy",
        },
    },
    {
        "ts": "2026-04-20T20:02:00+00:00",
        "type": "RenderProduced",
        "artifact": "/repo/config/branding.yaml",
        "payload": {
            "source_template": "config/branding.yaml.tpl",
            "output_path": "config/branding.yaml",
            "hash": "sha256:branding",
            "residual_count": 0,
        },
    },
    {
        "ts": "2026-04-20T20:03:00+00:00",
        "type": "RenderProduced",
        "artifact": "/repo/config/paths.py",
        "payload": {
            "source_template": "config/paths.py.tpl",
            "output_path": "config/paths.py",
            "hash": "sha256:rendered-paths",
            "residual_count": 0,
        },
    },
    {
        "ts": "2026-04-20T20:04:00+00:00",
        "type": "InstallApplied",
        "artifact": str(mismatch),
        "payload": {
            "source_template": "config/paths.py",
            "hash": "sha256:installed-paths",
            "kind": "file",
            "action": "copy",
        },
    },
    {
        "ts": "2026-04-20T20:05:00+00:00",
        "type": "InstallApplied",
        "artifact": str(edge / "install" / "missing.md"),
        "payload": {
            "source_template": "config/missing.md",
            "hash": "sha256:missing",
            "kind": "file",
            "action": "copy",
        },
    },
    {
        "ts": "2026-04-20T20:06:00+00:00",
        "type": "InstallApplied",
        "artifact": str(edge / ".avatar-gen.py"),
        "payload": {
            "source_template": "generated:avatar-openai-script",
            "hash": "sha256:temp",
            "kind": "file",
            "action": "write",
        },
    },
    {
        "ts": "2026-04-20T20:06:30+00:00",
        "type": "InstallRemoved",
        "artifact": str(edge / ".avatar-gen.py"),
        "payload": {
            "source_template": "generated:avatar-openai-script",
            "kind": "file",
            "reason": "temporary-avatar-cleanup",
        },
    },
    {
        "ts": "2026-04-20T20:07:00+00:00",
        "type": "InstallCheckObserved",
        "artifact": str(edge / "install" / "missing.md"),
        "payload": {
            "check_id": "file:missing-md",
            "status": "fail",
            "severity": "fail",
            "detail": "missing.md: not found",
        },
    },
    {
        "ts": "2026-04-20T20:08:00+00:00",
        "type": "RenderProduced",
        "artifact": str(edge / "install" / "obsolete.md"),
        "payload": {
            "source_template": "config/obsolete.md.tpl",
            "output_path": "config/obsolete.md",
            "hash": "sha256:obsolete-render",
            "residual_count": 1,
        },
    },
    {
        "ts": "2026-04-20T20:10:00+00:00",
        "type": "RenderProduced",
        "artifact": str(in_place),
        "payload": {
            "source_template": "config/in-place.md.tpl",
            "output_path": "config/in-place.md",
            "hash": "sha256:0967115f2813a3541eaef77de9d9d5773f1c0c04314b0bbfe4ff3b3b1c55b5d5",
            "residual_count": 0,
        },
    },
    {
        "ts": "2026-04-20T20:11:00+00:00",
        "type": "RenderProduced",
        "artifact": str(superseded),
        "payload": {
            "source_template": "config/seeded.md.tpl",
            "output_path": "config/seeded.md",
            "hash": "sha256:rendered-seed",
            "residual_count": 0,
        },
    },
    {
        "ts": "2026-04-20T20:12:00+00:00",
        "type": "InstallApplied",
        "artifact": str(superseded),
        "payload": {
            "source_template": "generated:seed:seeded",
            "hash": "sha256:seeded",
            "kind": "file",
            "action": "write",
        },
    },
    {
        "ts": "2026-04-20T20:13:00+00:00",
        "type": "InstallCheckObserved",
        "artifact": str(edge / "state" / "render-install-drift.json"),
        "payload": {
            "check_id": "projection:render-install-drift",
            "status": "fail",
            "severity": "fail",
            "detail": "self-referential prior failure",
        },
    },
]
log_path = edge / "state" / "events" / "log.jsonl"
with open(log_path, "w", encoding="utf-8") as f:
    for event in events:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
PY

echo "--- Test 1: rollup writes expected summary ---"
if python3 "$TOOL" --json >/dev/null && python3 - <<'PY' "$OUT"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = payload["summary"]
assert summary["rendered_outputs"] == 5
assert summary["installed_artifacts"] == 4
assert summary["render_linked_installs"] == 3
assert summary["rendered_without_install"] == 1
assert summary["install_without_render"] == 1
assert summary["hash_mismatches"] == 1
assert summary["missing_on_disk"] == 1
assert summary["doctor_fail"] == 1
PY
then
    pass "rollup writes expected summary"
else
    fail "rollup writes expected summary"
fi

echo "--- Test 2: rollup captures representative examples ---"
if python3 - <<'PY' "$OUT"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["rendered_without_install"][0]["output_path"] == "config/branding.yaml"
assert payload["hash_mismatches"][0]["output_path"] == "config/paths.py"
assert payload["missing_on_disk"][0]["artifact"].endswith("missing.md")
assert all(not item["artifact"].endswith(".avatar-gen.py") for item in payload["missing_on_disk"])
assert all(item["output_path"] != "config/obsolete.md" for item in payload["hash_mismatches"])
assert all(item["output_path"] != "config/in-place.md" for item in payload["rendered_without_install"])
assert all(item["output_path"] != "config/seeded.md" for item in payload["rendered_without_install"])
assert payload["doctor_failures"][0]["check_id"] == "file:missing-md"
assert all(item["check_id"] != "projection:render-install-drift" for item in payload["doctor_failures"])
PY
then
    pass "rollup captures representative examples"
else
    fail "rollup captures representative examples"
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
