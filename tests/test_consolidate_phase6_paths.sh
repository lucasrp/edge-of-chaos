#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$EDGE_DIR/blog/consolidate-state.sh"

python3 - "$SCRIPT" <<'PY'
import pathlib
import sys

script = pathlib.Path(sys.argv[1])
lines = script.read_text(encoding="utf-8").splitlines()

def first_index(needle: str) -> int:
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    raise AssertionError(f"missing {needle!r}")

phase6_start = first_index('emit_run_step_event "phase-6" "started"')
definition = first_index('proposal_path = meta_dir / f"{slug}.state-proposal.yaml"')
first_use = first_index('if proposal_path.exists():')
audit_definition = first_index('audit_path = meta_dir / f"{slug}.state-audit.yaml"')
audit_use = first_index('if audit_path.exists():')
non_git_diff_guard = first_index('skipping scoped diff')
non_git_commit_guard = first_index('skipping git commit')
partial_degraded = first_index('emit_run_step_event "pipeline" "degraded" "pipeline_end" "partial publication"')

assert phase6_start < definition < first_use, (
    f"proposal_path must be defined before phase-6 allowlist use "
    f"(phase6={phase6_start}, definition={definition}, use={first_use})"
)
assert phase6_start < audit_definition < audit_use, (
    f"audit_path must be defined before phase-6 allowlist use "
    f"(phase6={phase6_start}, definition={audit_definition}, use={audit_use})"
)
assert phase6_start < non_git_diff_guard, "non-git EDGE_REPO_DIR must skip scoped diff in phase 6"
assert phase6_start < non_git_commit_guard, "non-git EDGE_REPO_DIR must skip git commit in phase 6"
assert phase6_start < partial_degraded, "partial publication must be degraded, not a hard pipeline failure"
PY

echo "PASS: consolidate-state phase-6 paths are initialized before use"
