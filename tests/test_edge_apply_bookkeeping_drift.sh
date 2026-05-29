#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-apply-drift-XXXXXX)"
TMP_HOME="$TMP_BASE/home"
TMP_REPO="$TMP_BASE/repo"
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

mkdir -p "$TMP_HOME" "$TMP_REPO/config" "$TMP_REPO/templates" "$TMP_REPO/memory" "$TMP_REPO/secrets" "$TMP_STATE"

cat >"$TMP_CONFIG" <<YAML
name: Drift Test
codename: drift-test
skill_prefix: drift-test
mission: Validate install bookkeeping drift
voice: Direct and factual
domain: testing
edge_home: $TMP_REPO
blog_port: 8766
onboarding_mode: true
YAML

for file in branding.yaml capabilities.yaml features.yaml interests.md postflight.yaml preflight.yaml runtime-routers.yaml strategy.md; do
    printf 'rendered %s\n' "$file" >"$TMP_REPO/config/$file"
done
for file in paths.py paths.sh branding.py health-config.yaml; do
    printf 'static %s\n' "$file" >"$TMP_REPO/config/$file"
done
for file in CLAUDE.md onboarding.md onboarding_checklist.md quick_win_archetypes.md self_intro_template.md; do
    printf '# %s\n' "$file" >"$TMP_REPO/templates/$file"
done
for file in personality.md rules-core.md method.md knowledge-design.md; do
    printf '# %s\n' "$file" >"$TMP_REPO/memory/$file"
done
cat >"$TMP_REPO/secrets/openai.env" <<'ENV'
OPENAI_API_KEY=fake-test-key
ENV

echo "=== edge-apply bookkeeping drift Smoke Test ==="
echo "Temp repo: $TMP_REPO"
echo ""

echo "--- Test 1: phase_identity logs InstallApplied for rendered config in-place ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG" "$TMP_HOME" "$TMP_REPO" "$TMP_STATE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

edge_dir, config_path, home_dir, repo_dir, state_dir = sys.argv[1:]
os.environ["HOME"] = home_dir
os.environ["EDGE_STATE_DIR"] = state_dir
os.environ["EDGE_CODENAME"] = "drift-test"
os.environ["EDGE_CYCLE_ID"] = "install:test-identity-in-place"

loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
mod.REPO_ROOT = Path(repo_dir)

cfg = mod.load_config(Path(config_path))
assert mod.phase_identity(cfg, dry_run=False) is True

events = [
    json.loads(line)
    for line in (Path(state_dir) / "state" / "events" / "log.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
matches = [
    event for event in events
    if event.get("type") == "InstallApplied"
    and event.get("cycle_id") == "install:test-identity-in-place"
    and (event.get("payload") or {}).get("action") == "in-place"
]
expected = {
    "branding.yaml",
    "capabilities.yaml",
    "features.yaml",
    "interests.md",
    "postflight.yaml",
    "preflight.yaml",
    "runtime-routers.yaml",
    "strategy.md",
}
seen = {Path(event["artifact"]).name for event in matches}
assert seen == expected, seen
assert all((event.get("payload") or {}).get("in_place") is True for event in matches)
PY
then
    pass "phase_identity logs in-place config installs"
else
    fail "phase_identity logs in-place config installs"
fi

echo "--- Test 2: phase_avatar emits InstallRemoved for temp files ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG" "$TMP_HOME" "$TMP_REPO" "$TMP_STATE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

edge_dir, config_path, home_dir, repo_dir, state_dir = sys.argv[1:]
os.environ["HOME"] = home_dir
os.environ["EDGE_STATE_DIR"] = state_dir
os.environ["EDGE_CODENAME"] = "drift-test"
os.environ["EDGE_CYCLE_ID"] = "install:test-avatar-cleanup"

loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
mod.REPO_ROOT = Path(repo_dir)
mod.run = lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="forced test failure")

cfg = mod.load_config(Path(config_path))
assert mod.phase_avatar(cfg, dry_run=False) is True

events = [
    json.loads(line)
    for line in (Path(state_dir) / "state" / "events" / "log.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
matches = [
    event for event in events
    if event.get("type") == "InstallRemoved"
    and event.get("cycle_id") == "install:test-avatar-cleanup"
]
artifacts = {Path(event["artifact"]).name for event in matches}
assert {".avatar-prompt.txt", ".avatar-gen.py"} <= artifacts, artifacts
assert not (Path(repo_dir) / ".avatar-prompt.txt").exists()
assert not (Path(repo_dir) / ".avatar-gen.py").exists()
PY
then
    pass "phase_avatar emits InstallRemoved for temp files"
else
    fail "phase_avatar emits InstallRemoved for temp files"
fi

echo "--- Test 3: phase_identity migrates legacy topics into state topics dir ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_CONFIG" "$TMP_HOME" "$TMP_REPO" "$TMP_STATE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

edge_dir, config_path, home_dir, repo_dir, state_dir = sys.argv[1:]
os.environ["HOME"] = home_dir
os.environ["EDGE_STATE_DIR"] = state_dir
os.environ["EDGE_CODENAME"] = "drift-test"
os.environ["EDGE_CYCLE_ID"] = "install:test-topic-migration"

loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
mod.REPO_ROOT = Path(repo_dir)

cfg = mod.load_config(Path(config_path))
legacy_topics_dir = Path(home_dir) / ".claude" / "projects" / cfg["memory_project_dir"] / "memory" / "topics"
legacy_topics_dir.mkdir(parents=True, exist_ok=True)
(legacy_topics_dir / "dispatch.md").write_text("# Dispatch transparency\n", encoding="utf-8")
(legacy_topics_dir / "lineage.md").write_text("# Knowledge lineage\n", encoding="utf-8")

assert mod.phase_identity(cfg, dry_run=False) is True

topics_dir = Path(state_dir) / "topics"
assert (topics_dir / "dispatch.md").exists()
assert (topics_dir / "lineage.md").exists()

events = [
    json.loads(line)
    for line in (Path(state_dir) / "state" / "events" / "log.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
matches = [
    event for event in events
    if event.get("type") == "InstallApplied"
    and event.get("cycle_id") == "install:test-topic-migration"
    and Path(event.get("artifact") or "").parent == topics_dir
]
seen = {Path(event["artifact"]).name for event in matches}
assert {"dispatch.md", "lineage.md"} <= seen, seen
PY
then
    pass "phase_identity migrates legacy topics into state topics dir"
else
    fail "phase_identity migrates legacy topics into state topics dir"
fi

echo "--- Test 4: _copy_file logs content hash when destination is symlink ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_HOME" "$TMP_REPO" "$TMP_STATE"
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

edge_dir, home_dir, repo_dir, state_dir = sys.argv[1:]
os.environ["HOME"] = home_dir
os.environ["EDGE_STATE_DIR"] = state_dir
os.environ["EDGE_CODENAME"] = "drift-test"
os.environ["EDGE_CYCLE_ID"] = "install:test-copy-symlink-hash"

loader = importlib.machinery.SourceFileLoader("edge_apply_mod", f"{edge_dir}/tools/edge-apply")
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
mod.REPO_ROOT = Path(repo_dir)

src = Path(repo_dir) / "config" / "heartbeat.sh"
src.write_text("#!/bin/sh\necho rendered-heartbeat\n", encoding="utf-8")
target = Path(home_dir) / "actual-heartbeat.sh"
target.write_text("stale\n", encoding="utf-8")
dst = Path(home_dir) / ".local" / "bin" / "heartbeat.sh"
dst.parent.mkdir(parents=True, exist_ok=True)
dst.symlink_to(target)

mod._copy_file(src, dst, phase="systemd", dry_run=False, chmod=0o755)

expected_hash = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()
symlink_target_hash = "sha256:" + hashlib.sha256(os.readlink(dst).encode("utf-8")).hexdigest()
events = [
    json.loads(line)
    for line in (Path(state_dir) / "state" / "events" / "log.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
match = next(
    event for event in reversed(events)
    if event.get("type") == "InstallApplied"
    and event.get("cycle_id") == "install:test-copy-symlink-hash"
    and event.get("artifact") == str(dst)
)
payload_hash = (match.get("payload") or {}).get("hash")
assert payload_hash == expected_hash, payload_hash
assert payload_hash != symlink_target_hash
assert target.read_bytes() == src.read_bytes()
PY
then
    pass "_copy_file logs content hash through symlink destinations"
else
    fail "_copy_file logs content hash through symlink destinations"
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
