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
definition = first_index('proposal_path = audits_dir / f"{slug}.state-proposal.yaml"')
first_use = first_index('if proposal_path.exists():')
audit_definition = first_index('audit_path = audits_dir / f"{slug}.state-audit.yaml"')
audit_use = first_index('if audit_path.exists():')
non_git_diff_guard = first_index('skipping scoped diff')
non_git_commit_guard = first_index('skipping git commit')
partial_degraded = first_index('emit_run_step_event "pipeline" "degraded" "pipeline_end" "partial publication"')
complete_artifact_published = first_index('    emit_artifact_published_event')
complete_pipeline_end = first_index('emit_run_step_event "pipeline" "completed" "pipeline_end" ""')
report_materialization = first_index('emit_run_step_event "phase-0.9" "started" "report_materialization"')
blog_publish = first_index('emit_run_step_event "phase-1" "started" "blog_publish"')
report_confirmation = first_index('emit_run_step_event "phase-2" "started" "report_generation"')
render_error_count = first_index("RENDER_ERRORS=$(grep -c 'ERRO bloco' \"$REPORT_HTML\" 2>/dev/null || true)")
materialize_function = first_index('materialize_report_before_publish()')
index_function = first_index('index_materialized_report()')

retired_tool = "edge-" + "meta-" + "report"
retired_phase = "post_state_" + "meta_" + "report"
assert not any(retired_tool in line for line in lines), "consolidate-state must not call retired report-mirror tool"
assert not any(retired_phase in line for line in lines), "post-state report-mirror phase must be removed"
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
assert complete_artifact_published < complete_pipeline_end, (
    "complete consolidate-state publications must emit ArtifactPublished before terminal pipeline_end"
)
assert materialize_function < report_materialization < blog_publish, (
    "report materialization must happen before blog publish so entries cannot be published without reports"
)
assert index_function < report_confirmation and blog_publish < report_confirmation, (
    "phase-2 should confirm/index the already materialized report after blog publish"
)
assert report_confirmation < render_error_count, (
    "render-error counting must tolerate zero matches under set -e during phase-3 verification"
)
PY

echo "PASS: consolidate-state phase-6 paths are initialized before use"
