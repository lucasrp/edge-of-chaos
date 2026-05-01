#!/bin/bash
# consolidate-state — Pipeline completo: entry + report + meta-report + state commit
#
# Uso:
#   consolidate-state <entry.md> <report.yaml>         # entry + content report + meta-report
#   consolidate-state <entry.md> <report.html>         # entry + content report pre-gerado + meta-report
#
# Enforcement #245: content report (YAML ou HTML pre-gerado) é MANDATÓRIO.
# Publicar sem content report viola o rito uniforme em
# skills/_shared/report-template.md. Se o provedor adversarial externo estiver
# indisponível, use o fallback Claude (#235) — não pule o rito.
#
# Pipeline (8 fases):
#   0.  Frontmatter injection (report: field)
#   0b. Note link injection (note: field, if matching note exists)
#   0.3 Adversarial review enforcement (edge-consult --gate; YAML or HTML)
#   0.45 Feynman judge (YAML or HTML)
#   0.5 Review gate (LLM-as-judge, content report only; YAML or HTML)
#   0.9 Content report materialization before publish (mandatory — #245)
#   1.  Blog entry (blog-publish.sh)
#   2.  Content report indexing/confirmation
#   3.  Verificação (API, frontmatter, files)
#   3.4 LLM cost injection
#   4.  Meta-report (state delta + scratchpad + adversarial → cognitive mirror)
#   5.  State commit (claims + threads + event + digest)
#   6.  Diffs + Git commit (audit trail)
#
# Exit codes: 0 = tudo OK, 1 = erro fatal, 2 = parcial, 3 = review gate falhou
#
# Flags:
#   --review-only      Rodar so o review gate, sem publicar
#   --recover          Detect and re-run pipeline for incomplete publications
#   --scratchpad PATH  Scratchpad para meta-report (default: /tmp/edge-scratch-active.md)
#   --reason TEXT      Custom commit message reason
#
# Enforcement #218: bypass flags (--skip-review, --no-adversarial, --no-meta)
# have been removed. All phases now run unconditionally. Recovery reruns the
# full pipeline. This file exports EDGE_CONSOLIDATE_ACTIVE=1 so the write-guard
# hook allows artifact writes only during consolidate-state execution.

set -uo pipefail

# --- Load shared paths (branding, memory, blog config) ---
REAL_SCRIPT="$(readlink -f "$0")"
# shellcheck source=../config/paths.sh
source "$(dirname "$REAL_SCRIPT")/../config/paths.sh"

# Enforcement #218: mark this process as the authoritative artifact-writing path.
# write-guard hook checks this to allow Write/Edit in artifact paths.
export EDGE_CONSOLIDATE_ACTIVE=1
# Unset on exit so subsequent processes lose authorization.
trap 'unset EDGE_CONSOLIDATE_ACTIVE' EXIT

set +e
PUBLISH_GUARD_OUTPUT="$("$TOOLS_DIR/edge-publish-guard" --operation consolidate-state --target "${1:-}" 2>&1)"
PUBLISH_GUARD_STATUS=$?
set -e
if [[ "$PUBLISH_GUARD_STATUS" -ne 0 ]]; then
    printf '%s\n' "$PUBLISH_GUARD_OUTPUT" >&2
    echo "ERROR: consolidate-state publication guard rejected this run." >&2
    exit 65
fi

# Peça 3: telemetry helper — record phase start/end in edge-ledger.
# Fails silently if edge-ledger is unavailable (telemetry is never blocking).
ledger_record() {
    local tool="$1" status="$2" duration="${3:-}"
    if command -v edge-ledger &>/dev/null; then
        local args=(record --skill consolidate-state --tool "$tool")
        if [[ "$status" == "ok" ]]; then args+=(--ok); else args+=(--fail --error-class "$status"); fi
        [[ -n "$duration" ]] && args+=(--duration-ms "$duration")
        edge-ledger "${args[@]}" 2>/dev/null || true
    fi
}

emit_run_step_event() {
    local phase="$1" status="$2" operation="${3:-}" error_text="${4:-}"
    python3 - "$phase" "$status" "$operation" "$error_text" <<'PYEOF' 2>/dev/null || true
import os, sys
from pathlib import Path

phase, status, operation, error_text = sys.argv[1:5]
tools_dir = Path(
    os.environ.get("TOOLS_DIR")
    or (
        Path(
            os.environ.get(
                "EDGE_REPO_DIR",
                os.environ.get("EDGE_DIR", str(Path.home() / "edge")),
            )
        ).expanduser()
        / "tools"
    )
)
sys.path.insert(0, str(tools_dir))
try:
    from _shared.telemetry import emit_shadow_event, log_run_step
except Exception:
    sys.exit(0)

fields = {
    "slug": os.environ.get("EDGE_PUBLISH_SLUG", "unknown"),
}
if operation:
    fields["operation"] = operation
if error_text:
    fields["error"] = error_text[:240]
log_run_step(
    "consolidate-state",
    phase,
    status,
    run_id=os.environ.get("EDGE_CONSOLIDATE_RUN_ID"),
    **fields,
)

if status in {"completed", "failed", "degraded"} and (phase == "pipeline" or phase.startswith("phase-")):
    slug = os.environ.get("EDGE_PUBLISH_SLUG", "").strip()
    if slug and slug != "unknown":
        normalized_phase = phase[6:] if phase.startswith("phase-") else phase
        payload = {
            "pipeline": "consolidate-state",
            "phase": normalized_phase,
            "status": status,
            "slug": slug,
        }
        if status == "completed":
            payload["ok"] = True
        elif status == "failed":
            payload["ok"] = False
        if operation:
            payload["operation"] = operation
        if error_text:
            payload["reason"] = error_text[:240]
        emit_shadow_event(
            "PhaseCompleted",
            actor="consolidate-state",
            artifact=f"blog/entries/{slug}.md",
            cycle_id=os.environ.get("EDGE_CYCLE_ID") or None,
            payload=payload,
        )
PYEOF
}

run_adversarial_gate_review() {
    local review_question="${1:-}"
    local review_output=""
    if command -v edge-consult &>/dev/null; then
        review_output=$(edge-consult "$review_question" --context "$ENTRY_PATH" "$REPORT_INPUT" --gate "$REPORT_INPUT" 2>&1)
    else
        review_output=$(python3 "$TOOLS_DIR/edge-consult.py" "$review_question" --context "$ENTRY_PATH" "$REPORT_INPUT" --gate "$REPORT_INPUT" 2>&1)
    fi
    local review_exit=$?
    if [[ $review_exit -ne 0 ]]; then
        echo "$review_output"
        return $review_exit
    fi
    echo "$review_output"
    return 0
}

artifact_stem_for() {
    local artifact="$1"
    case "$artifact" in
        *.yaml) echo "${artifact%.yaml}" ;;
        *.yml) echo "${artifact%.yml}" ;;
        *.html) echo "${artifact%.html}" ;;
        *) echo "${artifact%.*}" ;;
    esac
}

artifact_kind_for() {
    local artifact="$1"
    case "$artifact" in
        *.yaml|*.yml) echo "YAML" ;;
        *.html) echo "HTML" ;;
        *) echo "unknown" ;;
    esac
}

run_review_gate() {
    local artifact="$1"
    local skill_name="${2:-}"
    local review_cmd=()
    if command -v review-gate &>/dev/null; then
        review_cmd=(review-gate "$artifact" --json)
    elif [[ -x "$TOOLS_DIR/review-gate.py" ]]; then
        review_cmd=(python3 "$TOOLS_DIR/review-gate.py" "$artifact" --json)
    else
        return 127
    fi
    [[ -n "$skill_name" ]] && review_cmd+=(--skill "$skill_name")
    [[ -n "${ENTRY_PATH:-}" ]] && review_cmd+=(--entry "$ENTRY_PATH")
    "${review_cmd[@]}"
}

# Parse flags
REVIEW_ONLY=false
RECOVER=false
SCRATCHPAD=""
COMMIT_REASON=""
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "Usage: consolidate-state <entry.md> <report.yaml|report.html>"
            echo ""
            echo "Both arguments are MANDATORY (#245). Publishing an entry without"
            echo "a content report violates the uniform rite in"
            echo "skills/_shared/report-template.md."
            echo ""
            echo "Flags:"
            echo "  --review-only      Run only the review gate, without publishing"
            echo "  --recover          Detect and re-run pipeline for incomplete publications"
            echo "  --scratchpad PATH  Scratchpad for meta-report (default: /tmp/edge-scratch-active.md)"
            echo "  --reason TEXT      Custom commit message reason"
            echo "  --help, -h         Show this help"
            echo ""
            echo "Enforcement: --skip-review, --no-adversarial, --no-meta REMOVED (#218)."
            echo "All phases run unconditionally. To recover, run the full pipeline."
            exit 0
            ;;
        --review-only) REVIEW_ONLY=true; shift ;;
        --recover) RECOVER=true; shift ;;
        --scratchpad) SCRATCHPAD="$2"; shift 2 ;;
        --reason) COMMIT_REASON="$2"; shift 2 ;;
        --skip-review|--no-adversarial|--no-meta)
            echo "ERROR: $1 removed by #218 enforcement. All phases are mandatory." >&2
            exit 64
            ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done

ENTRY_PATH="${POSITIONAL[0]:-}"
REPORT_INPUT="${POSITIONAL[1]:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}OK${NC}: $1"; }
warn() { echo -e "  ${YELLOW}WARN${NC}: $1"; }
fail() { echo -e "  ${RED}FAIL${NC}: $1"; }

materialize_report_before_publish() {
    if [[ -z "$REPORT_INPUT" ]]; then
        REPORT_RESULT="skip"
        return 0
    fi
    if [[ ! -f "$REPORT_INPUT" ]]; then
        fail "Report not found: $REPORT_INPUT"
        REPORT_RESULT="fail"
        return 1
    fi
    if [[ -z "$REPORT_FILENAME" ]]; then
        fail "Unsupported report format: $REPORT_INPUT"
        REPORT_RESULT="fail"
        return 1
    fi

    REPORT_HTML="$REPORTS_DIR/$REPORT_FILENAME"
    mkdir -p "$REPORTS_DIR"

    if [[ "$REPORT_INPUT" == *.yaml || "$REPORT_INPUT" == *.yml ]]; then
        local render_output=""
        echo "  Generating HTML from $(basename "$REPORT_INPUT") before publishing entry..."
        if render_output=$(python3 "$TOOLS_DIR/generate_report.py" --yaml "$REPORT_INPUT" --output "$REPORT_HTML" 2>&1); then
            [[ -n "$render_output" ]] && echo "$render_output"
            ok "Report generated: $REPORT_FILENAME"
            REPORT_RESULT="ok"
            return 0
        fi
        [[ -n "$render_output" ]] && echo "$render_output"
        fail "generate_report.py failed"
        REPORT_RESULT="fail"
        return 1
    fi

    if [[ "$REPORT_INPUT" == *.html ]]; then
        if [[ "$(dirname "$REPORT_INPUT")" != "$REPORTS_DIR" ]]; then
            cp "$REPORT_INPUT" "$REPORT_HTML"
        fi
        if [[ -f "$REPORT_HTML" ]]; then
            ok "Report HTML: $REPORT_FILENAME"
            REPORT_RESULT="ok"
            return 0
        fi
        fail "Report HTML not found"
        REPORT_RESULT="fail"
        return 1
    fi

    fail "Unsupported report format: $REPORT_INPUT"
    REPORT_RESULT="fail"
    return 1
}

index_materialized_report() {
    if [[ "$REPORT_RESULT" != "ok" || -z "$REPORT_HTML" || ! -f "$REPORT_HTML" ]]; then
        fail "Report was not materialized before publish"
        REPORT_RESULT="fail"
        return 1
    fi

    ok "Report ready before publish: $REPORT_FILENAME"
    echo "  Indexing report..."
    if command -v edge-index &>/dev/null; then
        if edge-index "$REPORT_HTML" 2>/dev/null; then
            ok "Report indexed"
        else
            warn "edge-index returned error (non-fatal)"
        fi
    else
        warn "edge-index not found"
    fi
    return 0
}

# Log pipeline failure to JSONL (bash phases)
FAILURES_LOG="$LOGS_DIR/pipeline-failures.jsonl"
mkdir -p "$(dirname "$FAILURES_LOG")"
log_failure() {
    local phase="$1" operation="$2" error="$3"
    python3 -c "
import json, sys
from datetime import datetime, timezone
entry = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'slug': '${SLUG:-unknown}',
    'phase': sys.argv[1],
    'operation': sys.argv[2],
    'error': sys.argv[3],
}
with open('$FAILURES_LOG', 'a') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
" "$phase" "$operation" "$error" 2>/dev/null
    emit_run_step_event "phase-$phase" "failed" "$operation" "$error"
}

if [[ "$RECOVER" == "false" ]]; then
    if [[ -z "$ENTRY_PATH" ]]; then
        echo "Usage: consolidate-state <entry.md> <report.yaml|report.html>" >&2
        echo "  --recover          Detect and re-run pipeline for incomplete publications" >&2
        echo "  --scratchpad PATH  Scratchpad for meta-report" >&2
        echo "  --reason TEXT      Custom commit message reason" >&2
        echo "  (Enforcement #218: --skip-review / --no-adversarial / --no-meta removed.)" >&2
        exit 1
    fi
    # Enforcement #245: content report is MANDATORY. Publishing an entry-only
    # artifact violates the uniform rite (skills/_shared/report-template.md).
    # The old "entry-only" path silently produced no HTML — it was the
    # mechanical bypass the minimal-meta beats used. No more.
    if [[ -z "$REPORT_INPUT" ]]; then
        echo "ERROR: content report (report.yaml|report.html) is MANDATORY." >&2
        echo "" >&2
        echo "  Publishing without a content report violates the uniform rite" >&2
        echo "  defined in skills/_shared/report-template.md." >&2
        echo "" >&2
        echo "  If the external adversarial provider (edge-consult) is down," >&2
        echo "  use the local Claude fallback (#235) — it does NOT exempt you" >&2
        echo "  from producing the full-rite artifact." >&2
        echo "" >&2
        echo "  Usage: consolidate-state <entry.md> <report.yaml|report.html>" >&2
        exit 64
    fi
fi

# ─── RECOVER MODE: re-run Phase 5/6 for entries that have no git commit ───
if [[ "$RECOVER" == "true" ]]; then
    echo "========================================="
    echo " consolidate-state --recover"
    echo "========================================="
    echo ""

    FAILURES_LOG="$LOGS_DIR/pipeline-failures.jsonl"
    RECOVERED=0

    # Find entries published today that may be missing state commit
    for entry_file in "$ENTRIES_DIR/"*.md; do
        [[ -f "$entry_file" ]] || continue
        entry_slug=$(basename "$entry_file" .md)

        # Check if entry has a git commit in ~/edge/
        if ! git -C "$EDGE_DIR" log --oneline --all --grep="publish: $entry_slug" 2>/dev/null | head -1 | grep -q .; then
            echo "  Incomplete: $entry_slug (no git commit)"

            # Check if entry is in blog API
            VISIBLE=$(curl -s -m 3 $CURL_AUTH "${BLOG_URL}/blog/entries/" 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    found = any(e.get('slug') == '$entry_slug' for e in data)
    print('visible' if found else 'missing')
except: print('error')
" 2>&1)

            if [[ "$VISIBLE" == "visible" ]]; then
                echo "    Entry visible in API — re-running Phase 5/6..."
                # Extract report from frontmatter
                REPORT_FN=$(python3 -c "
import yaml
raw = open('$entry_file').read()
parts = raw.split('---', 2)
fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
print(fm.get('report', '') if fm else '')
" 2>/dev/null)

                # Run full pipeline (no bypass flags — all phases run)
                bash "$0" --reason "recover: full re-run" "$entry_file" ${REPORT_FN:+"$REPORT_FN"} 2>&1 | tail -5
                RECOVERED=$((RECOVERED + 1))
            else
                echo "    Entry NOT visible — needs full republish (run without --recover)"
            fi
        fi
    done

    if [[ $RECOVERED -eq 0 ]]; then
        echo "  All entries have commits. Nothing to recover."
    else
        echo ""
        echo "  Recovered: $RECOVERED entries"
    fi
    exit 0
fi

# Resolve to absolute
[[ "$ENTRY_PATH" = /* ]] || ENTRY_PATH="$(pwd)/$ENTRY_PATH"
[[ -n "$REPORT_INPUT" && ! "$REPORT_INPUT" = /* ]] && REPORT_INPUT="$(pwd)/$REPORT_INPUT"

SLUG=$(basename "$ENTRY_PATH" .md)
export EDGE_PUBLISH_SLUG="$SLUG"
export EDGE_CONSOLIDATE_RUN_ID="${EDGE_CONSOLIDATE_RUN_ID:-consolidate:${SLUG}:$(date -u +%Y%m%dT%H%M%SZ)}"
REPORT_HTML=""
REPORT_FILENAME=""
REPORT_RESULT="skip"
TOTAL_LLM_COST="0"
META_REPORT_PATH=""

ledger_record "pipeline-start" "ok"

# Enforcement #245: content report (YAML/HTML) is MANDATORY — validated
# at the top of the script before RECOVER mode branch. By the time we reach
# here (non-recover path), both ENTRY_PATH and REPORT_INPUT are set.

STATE_AUDIT_EXIT=0

emit_run_step_event "pipeline" "started" "pipeline_start" ""

echo "========================================="
echo " consolidate-state: $SLUG"
echo "========================================="
echo ""

# ─── PHASE 0a: State snapshot (PRE — capture protected files before anything changes) ───
# If agent already took snapshot (before making state changes), skip.
echo "── Phase 0a: State Snapshot ──"
ledger_record "phase-0a" "ok"
emit_run_step_event "phase-0a" "started" "state_snapshot" ""
if command -v edge-state-audit &>/dev/null; then
    PRE_SNAPSHOT="$SNAPSHOT_DIR/${SLUG}.pre.yaml"
    if [[ -f "$PRE_SNAPSHOT" ]]; then
        ok "PRE snapshot already exists (agent captured before changes)"
    else
        if edge-state-audit snapshot --slug "$SLUG" 2>/dev/null; then
            ok "PRE snapshot captured"
        else
            warn "edge-state-audit snapshot failed"
            log_failure "0a" "state_snapshot" "edge-state-audit snapshot returned non-zero"
        fi
    fi
else
    warn "edge-state-audit not found — skipping state audit"
fi
emit_run_step_event "phase-0a" "completed" "state_snapshot" ""
echo ""

# ─── PHASE 0: Inject report: in frontmatter if needed ───
if [[ -n "$REPORT_INPUT" ]]; then
    # Determine report filename
    if [[ "$REPORT_INPUT" == *.yaml || "$REPORT_INPUT" == *.yml ]]; then
        REPORT_FILENAME="${SLUG}.html"
    elif [[ "$REPORT_INPUT" == *.html ]]; then
        REPORT_FILENAME="$(basename "$REPORT_INPUT")"
    fi

    if [[ -n "$REPORT_FILENAME" ]]; then
        # Check if frontmatter already has report: field
        HAS_REPORT=$(python3 -c "
import yaml
raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
if len(parts) >= 3:
    fm = yaml.safe_load(parts[1]) or {}
    print('yes' if fm.get('report') else 'no')
else:
    print('no')
" 2>/dev/null)

        if [[ "$HAS_REPORT" == "no" ]]; then
            echo "── Phase 0: Frontmatter ──"
            emit_run_step_event "phase-0" "started" "frontmatter_injection" ""
            # Inject report: field after the last frontmatter field (before closing ---)
            if python3 -c "
try:
    raw = open('$ENTRY_PATH').read()
    parts = raw.split('---', 2)
    if len(parts) >= 3:
        fm_text = parts[1].rstrip()
        fm_text += '\nreport: $REPORT_FILENAME\n'
        result = '---' + fm_text + '---' + parts[2]
        open('$ENTRY_PATH', 'w').write(result)
        print('  OK: report: $REPORT_FILENAME injected into frontmatter')
    else:
        print('  WARN: frontmatter not found (no --- delimiters)')
        exit(1)
except Exception as e:
    print(f'  FAIL: frontmatter injection: {e}')
    exit(1)
" 2>&1; then
                :
            else
                log_failure "0" "frontmatter_injection" "Failed to inject report: field"
            fi
            emit_run_step_event "phase-0" "completed" "frontmatter_injection" ""
            echo ""
        fi
    fi
fi

# ─── PHASE 0b: Note Link (inject note: in frontmatter if matching note exists) ───
NOTE_SLUG=$(echo "$SLUG" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//')
NOTE_FILE="$NOTES_DIR/${NOTE_SLUG}.md"
if [[ -f "$NOTE_FILE" ]]; then
    HAS_NOTE=$(python3 -c "
import yaml
raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
if len(parts) >= 3:
    fm = yaml.safe_load(parts[1]) or {}
    print('yes' if fm.get('note') else 'no')
else:
    print('no')
" 2>/dev/null)

    if [[ "$HAS_NOTE" == "no" ]]; then
        echo "── Phase 0b: Note Link ──"
        emit_run_step_event "phase-0b" "started" "note_link_injection" ""
        NOTE_BASENAME="${NOTE_SLUG}.md"
        if python3 -c "
try:
    raw = open('$ENTRY_PATH').read()
    parts = raw.split('---', 2)
    if len(parts) >= 3:
        fm_text = parts[1].rstrip()
        fm_text += '\nnote: $NOTE_BASENAME\n'
        result = '---' + fm_text + '---' + parts[2]
        open('$ENTRY_PATH', 'w').write(result)
        print('  OK: note: $NOTE_BASENAME injected into frontmatter')
    else:
        print('  WARN: frontmatter not found (no --- delimiters)')
        exit(1)
except Exception as e:
    print(f'  FAIL: note link injection: {e}')
    exit(1)
" 2>&1; then
            :
        else
            log_failure "0b" "note_link_injection" "Failed to inject note: field"
        fi
        emit_run_step_event "phase-0b" "completed" "note_link_injection" ""
        echo ""
    else
        echo "── Phase 0b: Note Link ──"
        ok "note: already present in frontmatter"
        echo ""
    fi
else
    :  # No matching note — skip silently
fi

# ─── PHASE 0.3: Adversarial Review Enforcement ───
# Every content artifact path must pass the same pre-publication gates. YAML
# specs and pre-rendered HTML both become reader-visible reports, so neither
# may bypass adversarial review, Feynman review, or the review gate.
if [[ -n "$REPORT_INPUT" ]]; then
    if [[ ! -f "$REPORT_INPUT" ]]; then
        fail "Report not found before quality gates: $REPORT_INPUT"
        emit_run_step_event "phase-0.3" "failed" "adversarial_review" "report artifact missing before gates"
        exit 1
    fi

    REPORT_KIND="$(artifact_kind_for "$REPORT_INPUT")"
    if [[ "$REPORT_KIND" == "unknown" ]]; then
        fail "Unsupported report format before publish: $REPORT_INPUT"
        emit_run_step_event "phase-0.3" "failed" "adversarial_review" "unsupported report artifact format"
        exit 1
    fi

    REPORT_ARTIFACT_STEM="$(artifact_stem_for "$REPORT_INPUT")"
    REVIEW_JSON_FILE="${REPORT_ARTIFACT_STEM}.review.json"
    RESOLVED_FILE="${REPORT_ARTIFACT_STEM}.resolved"
    REVIEW_QUESTION="Adversarially review this publication artifact before publish. It may be a YAML report spec or pre-rendered HTML. Identify the weakest reasoning, unsupported assumptions, missing evidence, protocol violations, missing visual/explanatory structure, and what is most likely to break. If it is HTML, review the final reader-visible artifact."

    echo "── Phase 0.3: Adversarial Review ($REPORT_KIND) ──"
    emit_run_step_event "phase-0.3" "started" "adversarial_review" ""

    if [[ ! -f "$REVIEW_JSON_FILE" ]]; then
        ok "No adversarial review found — generating gate review now"
        if run_adversarial_gate_review "$REVIEW_QUESTION"; then
            if [[ ! -f "$REVIEW_JSON_FILE" ]]; then
                fail "Adversarial review generation succeeded but no $(basename "$REVIEW_JSON_FILE") was written"
                emit_run_step_event "phase-0.3" "failed" "adversarial_review" "missing review artifact after generation"
                exit 3
            fi
            ok "Adversarial review generated ($(basename "$REVIEW_JSON_FILE"))"
            fail "Adversarial review pending: address feedback before continuing"
            echo ""
            echo "  Review: $REVIEW_JSON_FILE"
            echo "  Address the feedback in the artifact and create the marker to proceed:"
            echo "    touch $RESOLVED_FILE"
            echo ""
            emit_run_step_event "phase-0.3" "failed" "adversarial_review_pending" "review generated; pending resolution"
            exit 3
        else
            fail "Adversarial review generation failed"
            emit_run_step_event "phase-0.3" "failed" "adversarial_review" "gate generation failed"
            exit 3
        fi
    elif [[ ! -f "$RESOLVED_FILE" ]]; then
        fail "Adversarial review pending: $(basename "$REVIEW_JSON_FILE")"
        echo ""
        echo "  edge-consult generated feedback that has not been addressed."
        echo "  Address the feedback in the artifact and create the marker to proceed:"
        echo "    touch $RESOLVED_FILE"
        echo ""
        echo "  (Enforcement #218: bypass flags removed — adversarial review is mandatory.)"
        echo ""
        python3 -c "
import json, sys
try:
    d = json.load(open('$REVIEW_JSON_FILE'))
    resp = d.get('response', '')
    print('  Review (summary):')
    for line in resp.split('\n')[:8]:
        print(f'    {line}')
    if len(resp.split('\n')) > 8:
        print('    ...')
except Exception:
    pass
" 2>/dev/null
        echo ""
        emit_run_step_event "phase-0.3" "failed" "adversarial_review" "pending unresolved review"
        exit 3
    else
        ok "Adversarial review resolved ($(basename "$RESOLVED_FILE") present)"
        emit_run_step_event "phase-0.3" "completed" "adversarial_review" ""
        echo ""
    fi

    echo "── Phase 0.45: Feynman Judge ($REPORT_KIND) ──"
    emit_run_step_event "phase-0.45" "started" "feynman_judge" ""
    FEYNMAN_REVIEW_FILE="${REPORT_ARTIFACT_STEM}.feynman-review.json"
    if [[ -x "$TOOLS_DIR/feynman-judge" ]]; then
        FEYNMAN_JSON=$("$TOOLS_DIR/feynman-judge" "$REPORT_INPUT" --json --output "$FEYNMAN_REVIEW_FILE" 2>/dev/null)
        FEYNMAN_EXIT=$?
    elif command -v feynman-judge &>/dev/null; then
        FEYNMAN_JSON=$(feynman-judge "$REPORT_INPUT" --json --output "$FEYNMAN_REVIEW_FILE" 2>/dev/null)
        FEYNMAN_EXIT=$?
    else
        FEYNMAN_JSON=""
        FEYNMAN_EXIT=127
    fi
    if [[ $FEYNMAN_EXIT -eq 0 ]]; then
        FEYNMAN_SCORE=$(echo "$FEYNMAN_JSON" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('overall', 0))
except Exception:
    print(0)
" 2>/dev/null)
        ok "Feynman judge: score ${FEYNMAN_SCORE}/5.0"
        echo "  Review: $FEYNMAN_REVIEW_FILE"
        emit_run_step_event "phase-0.45" "completed" "feynman_judge" ""
    else
        fail "Feynman judge unavailable or failed"
        emit_run_step_event "phase-0.45" "failed" "feynman_judge" "judge unavailable or failed"
        exit 3
    fi
    echo ""

    echo "── Phase 0.5: Review Gate ($REPORT_KIND) ──"
    emit_run_step_event "phase-0.5" "started" "review_gate" ""
    REPORT_BASENAME=$(basename "$REPORT_INPUT")
    SKILL_NAME=""
    if [[ "$REPORT_BASENAME" =~ ^spec-([a-z]+)- ]]; then
        SKILL_NAME="${BASH_REMATCH[1]}"
    fi

    REVIEW_JSON=$(run_review_gate "$REPORT_INPUT" "$SKILL_NAME" 2>/dev/null)
    REVIEW_EXIT=$?
    if [[ $REVIEW_EXIT -ne 0 ]]; then
        fail "review-gate unavailable or failed (exit $REVIEW_EXIT)"
        emit_run_step_event "phase-0.5" "failed" "review_gate" "review-gate unavailable or failed"
        exit 3
    fi

    REVIEW_SCORE=$(echo "$REVIEW_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    fr = d.get('final_review', d)
    print(fr.get('overall', 0))
except Exception:
    print(0)
" 2>/dev/null)
    REVIEW_COST=$(echo "$REVIEW_JSON" | python3 -c "
import json, sys, re
try:
    d = json.load(sys.stdin)
    total = 0.0
    for key in ['coauthor']:
        meta = d.get(key, {}).get('_meta', {})
        c = meta.get('cost_estimate', '')
        total += float(re.sub(r'[^\d.]', '', c) or 0)
    for rd in d.get('rounds', []):
        for phase in ['review', 'refine']:
            meta = rd.get(phase, {}).get('_meta', {})
            c = meta.get('cost_estimate', '')
            total += float(re.sub(r'[^\d.]', '', c) or 0)
    if total == 0:
        meta = d.get('final_review', d).get('_meta', {})
        c = meta.get('cost_estimate', '')
        total = float(re.sub(r'[^\d.]', '', c) or 0)
    print(f'{total:.4f}')
except Exception:
    print('0')
" 2>/dev/null)
    TOTAL_LLM_COST="$REVIEW_COST"

    ok "Review gate: score ${REVIEW_SCORE}/5.0, cost \$${REVIEW_COST}"
    FEEDBACK_FILE="${REPORT_ARTIFACT_STEM}.feedback.json"
    if [[ -f "$FEEDBACK_FILE" ]]; then
        echo "$REVIEW_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('final_review', d)
issues = r.get('critical_issues', [])
suggestions = r.get('suggestions', [])
ca = d.get('coauthor', {})
ca_suggestions = ca.get('suggestions', [])
if issues:
    print('  Critical issues:')
    for i in issues[:3]:
        print(f'    - {i}')
if ca_suggestions:
    print(f'  Co-author suggestions: {len(ca_suggestions)}')
    for s in ca_suggestions[:3]:
        desc = s.get('description', s) if isinstance(s, dict) else str(s)
        print(f'    - {str(desc)[:120]}')
if suggestions:
    print(f'  Reviewer suggestions: {len(suggestions)}')
    for s in suggestions[:3]:
        print(f'    - {str(s)[:120]}')
" 2>/dev/null
        echo "  Feedback: $FEEDBACK_FILE"
    fi

    if [[ "$REVIEW_ONLY" == "true" ]]; then
        emit_run_step_event "phase-0.5" "completed" "review_gate" ""
        echo ""
        echo "Review-only mode. Nothing published."
        exit 0
    fi
    emit_run_step_event "phase-0.5" "completed" "review_gate" ""
    echo ""
fi

# ─── PHASE 0.9: Report materialization before publishing entry ───
if [[ -n "$REPORT_INPUT" ]]; then
    echo "── Phase 0.9: Report Materialization ──"
    ledger_record "phase-0.9" "ok"
    emit_run_step_event "phase-0.9" "started" "report_materialization" ""
    if materialize_report_before_publish; then
        emit_run_step_event "phase-0.9" "completed" "report_materialization" ""
    else
        log_failure "0.9" "report_materialization" "report materialization failed before blog publish"
        emit_run_step_event "phase-0.9" "failed" "report_materialization" "report materialization failed before blog publish"
        exit 1
    fi
    echo ""
fi

# ─── PHASE 1: Blog entry ───
echo "── Phase 1: Blog Entry ──"
ledger_record "phase-1" "ok"
emit_run_step_event "phase-1" "started" "blog_publish" ""
if CALLED_FROM_CONSOLIDAR_ESTADO=1 bash "$BLOG_DIR/blog-publish.sh" "$ENTRY_PATH"; then
    ok "Entry published"
    emit_run_step_event "phase-1" "completed" "blog_publish" ""
else
    fail "blog-publish.sh failed"
    log_failure "1" "blog_publish" "blog-publish.sh returned non-zero"
    exit 1
fi
echo ""

# ─── PHASE 2: Report (opcional) ───
if [[ -n "$REPORT_INPUT" ]]; then
    echo "── Phase 2: Report ──"
    emit_run_step_event "phase-2" "started" "report_generation" ""

    if ! index_materialized_report; then
        log_failure "2" "report_generation" "report was not materialized before publish"
    fi
    if [[ "$REPORT_RESULT" == "ok" ]]; then
        emit_run_step_event "phase-2" "completed" "report_generation" ""
    else
        emit_run_step_event "phase-2" "failed" "report_generation" "report phase ended in fail"
    fi
    echo ""
fi

# ─── PHASE 3: Verificacao final ───
echo "── Phase 3: Verification ──"
ledger_record "phase-3" "ok"
emit_run_step_event "phase-3" "started" "verification" ""
ALL_OK=true

# Entry visible?
VISIBLE=$(curl -s -m 5 $CURL_AUTH "${BLOG_URL}/blog/entries/" 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    found = any(e.get('slug') == '$SLUG' for e in data)
    print('OK' if found else 'NOT_FOUND')
except:
    print('ERROR')
" 2>&1)
if [[ "$VISIBLE" == "OK" ]]; then
    ok "Entry visible in API"
else
    warn "Entry NOT visible in API ($VISIBLE)"
    ALL_OK=false
fi

# Report linked in frontmatter?
if [[ -n "$REPORT_FILENAME" ]]; then
    HAS_REPORT=$(python3 -c "
import yaml
raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
fm = yaml.safe_load(parts[1]) or {}
r = fm.get('report', '')
print('OK' if r == '$REPORT_FILENAME' else f'MISMATCH: {r}')
" 2>/dev/null)
    if [[ "$HAS_REPORT" == "OK" ]]; then
        ok "Frontmatter report: $REPORT_FILENAME"
    else
        warn "Frontmatter report: $HAS_REPORT"
        # Auto-fix: update frontmatter report field to match actual generated filename
        sed -i "s|^report: .*|report: $REPORT_FILENAME|" "$ENTRY_PATH"
        ok "FIXED: report: $REPORT_FILENAME"
    fi
fi

# Report file exists and clean?
if [[ -n "$REPORT_HTML" && "$REPORT_RESULT" == "ok" ]]; then
    if [[ -f "$REPORT_HTML" ]]; then
        SIZE=$(du -h "$REPORT_HTML" | cut -f1)
        RENDER_ERRORS=$(grep -c 'ERRO bloco' "$REPORT_HTML" 2>/dev/null || true)
        RENDER_ERRORS=${RENDER_ERRORS:-0}
        if [[ "$RENDER_ERRORS" -gt 0 ]]; then
            fail "Report has $RENDER_ERRORS render error(s). Fix the YAML and regenerate."
            ALL_OK=false
            REPORT_RESULT="fail"
        else
            ok "Report file: $REPORT_FILENAME ($SIZE, 0 errors)"
        fi
    else
        fail "Report disappeared: $REPORT_HTML"
        ALL_OK=false
    fi
fi

# ─── PHASE 3.3: Workflow citation check ───
python3 -c "
import yaml, sys
try:
    raw = open('$ENTRY_PATH').read()
    parts = raw.split('---', 2)
    if len(parts) >= 3:
        fm = yaml.safe_load(parts[1]) or {}
        has_procedure = bool(fm.get('procedure'))
        has_wf_used = 'workflows_used' in fm
        has_wf_broken = 'workflows_broken' in fm
        if has_procedure and not has_wf_used and not has_wf_broken:
            print('MISSING_CITATIONS')
        else:
            print('OK')
    else:
        print('OK')
except:
    print('OK')
" 2>/dev/null | {
    read WF_CHECK
    if [[ "$WF_CHECK" == "MISSING_CITATIONS" ]]; then
        warn "Entry has procedure: but no workflows_used:/workflows_broken: — check /tmp/edge-recalled-workflows.txt and add citations"
        # Record as friction signal so reflection catches it across sessions
        if command -v edge-signal &>/dev/null; then
            edge-signal friction "Entry $SLUG: procedure without workflows_used/broken citations" --source consolidate-state 2>/dev/null || true
        fi
    fi
}

# ─── PHASE 3.35: Crystallization gate (curation entries only) ───
CRYST_CHECK=$(python3 -c "
import yaml, json, os, glob, sys
try:
    raw = open('$ENTRY_PATH').read()
    parts = raw.split('---', 2)
    fm = yaml.safe_load(parts[1]) or {}
    tags = fm.get('tags', [])
    if not ('curation' in tags or 'procedures' in tags):
        print('SKIP')
        sys.exit(0)
    pc = os.environ.get('PROCEDURE_CURATION_FILE', os.path.expanduser('~/edge/state/procedure-curation.json'))
    if not os.path.exists(pc):
        print('SKIP')
        sys.exit(0)
    data = json.load(open(pc))
    candidates = [c for c in data.get('crystallization_candidates', []) if c.get('claim_count', len(c.get('claims', []))) >= 3]
    if not candidates:
        print('SKIP')
        sys.exit(0)
    entries = glob.glob(os.path.join(os.environ.get('ENTRIES_DIR', os.path.expanduser('~/edge/blog/entries')), '*workflow*.md'))
    drafts = 0
    for e in entries:
        head = open(e).read()[:500]
        if 'workflow-draft' in head or 'workflow' in head.split('tags:')[1].split(chr(10))[0] if 'tags:' in head else False:
            drafts += 1
    if drafts < len(candidates):
        print(f'MISSING:{len(candidates) - drafts}')
    else:
        print('OK')
except Exception as e:
    print('SKIP')
" 2>/dev/null)
case "$CRYST_CHECK" in
    MISSING:*)
        N="${CRYST_CHECK#MISSING:}"
        warn "Curation has $N uncrystallized candidates — run 'edge-crystallize' to create workflow-draft entries"
        ;;
    OK) ;;
    *) ;;
esac

# ─── PHASE 3.4: Inject llm_cost into frontmatter ───
if [[ "$TOTAL_LLM_COST" != "0" && "$TOTAL_LLM_COST" != "" ]]; then
    if python3 -c "
import yaml, sys
try:
    raw = open('$ENTRY_PATH').read()
    parts = raw.split('---', 2)
    if len(parts) >= 3:
        fm = yaml.safe_load(parts[1]) or {}
        fm['llm_cost'] = '\$$TOTAL_LLM_COST'
        fm_text = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        result = '---\n' + fm_text + '---' + parts[2]
        open('$ENTRY_PATH', 'w').write(result)
    else:
        print('WARN: no frontmatter delimiters', file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
        ok "llm_cost: \$$TOTAL_LLM_COST injected into frontmatter"
    else
        warn "llm_cost injection failed"
        log_failure "3.4" "llm_cost_injection" "Failed to inject llm_cost into frontmatter"
    fi
fi
if $ALL_OK && [[ "$REPORT_RESULT" != "fail" ]]; then
    emit_run_step_event "phase-3" "completed" "verification" ""
else
    emit_run_step_event "phase-3" "failed" "verification" "verification ended with warnings or failures"
    fail "Verification failed before state commit; publication will not be recorded as Published"
    ledger_record "pipeline-end" "fail"
    emit_run_step_event "pipeline" "failed" "pipeline_end" "verification failed before state commit"
    exit 2
fi

# ─── PHASE 4: Meta-report (cognitive mirror) ───
# Captures state delta + scratchpad + adversarial BEFORE state commit.
# Agent reads this before making manual state changes (MEMORY.md, debugging.md, etc.)
# Enforcement #218: always runs (bypass flag --no-meta removed).
echo ""
echo "── Phase 4: Meta-report ──"
ledger_record "phase-4" "ok"
emit_run_step_event "phase-4" "started" "meta_report" ""
PHASE4_OK=true
if command -v edge-meta-report &>/dev/null || [[ -x "$TOOLS_DIR/edge-meta-report" ]]; then
    META_CMD="edge-meta-report --slug $SLUG --entry $ENTRY_PATH"
    # Use tools dir if not in PATH
    command -v edge-meta-report &>/dev/null || META_CMD="$TOOLS_DIR/edge-meta-report --slug $SLUG --entry $ENTRY_PATH"

    [[ -n "$SCRATCHPAD" ]] && META_CMD="$META_CMD --scratchpad $SCRATCHPAD"

    META_OUTPUT=$($META_CMD 2>&1)
    META_EXIT=$?

    if [[ $META_EXIT -eq 0 ]]; then
        META_REPORT_PATH=$(echo "$META_OUTPUT" | head -1 | sed 's/^OK: //')
        META_BASENAME=$(basename "$META_REPORT_PATH")
        ok "Meta-report: $META_BASENAME"
        # Inject meta_report field into entry frontmatter
        if ! grep -q "^meta_report:" "$ENTRY_PATH" 2>/dev/null; then
            if python3 -c "
import sys
try:
    path, meta = sys.argv[1], sys.argv[2]
    text = open(path).read()
    parts = text.split('---', 2)
    if len(parts) >= 3 and 'meta_report:' not in parts[1]:
        parts[1] = parts[1].rstrip() + '\nmeta_report: ' + meta + '\n'
        open(path, 'w').write('---'.join(parts))
        print('ADDED')
    else:
        print('SKIP')
except Exception as e:
    print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)
" "$ENTRY_PATH" "$META_BASENAME" 2>/dev/null; then
                ok "Added meta_report: $META_BASENAME to entry frontmatter"
            else
                warn "meta_report injection failed"
                log_failure "4" "meta_report_injection" "Failed to inject meta_report into frontmatter"
            fi
        fi
        if echo "$META_OUTPUT" | grep -q "Scratchpad:"; then
            ARCHIVED=$(echo "$META_OUTPUT" | grep "Scratchpad:" | sed 's/.*Scratchpad: //')
            ok "Scratchpad archived: $(basename "$ARCHIVED")"
        fi
        # Inject review-gate results into meta-report (so check-quality can find them)
        if [[ -n "${REVIEW_SCORE:-}" && -f "$META_REPORT_PATH" ]]; then
            cat >> "$META_REPORT_PATH" <<REVIEW_EOF

## Review Gate

- overall review score: ${REVIEW_SCORE}/5.0
- review cost: \$${REVIEW_COST}
REVIEW_EOF
            ok "Review gate results injected into meta-report"
        fi
        if [[ -n "${FEYNMAN_SCORE:-}" && -f "$META_REPORT_PATH" ]]; then
            cat >> "$META_REPORT_PATH" <<FEYNMAN_EOF

## Feynman Judge

- feynman score: ${FEYNMAN_SCORE}/5.0
- review file: $(basename "${FEYNMAN_REVIEW_FILE:-}")
FEYNMAN_EOF
            ok "Feynman judge results injected into meta-report"
        fi
    else
        warn "edge-meta-report failed (exit $META_EXIT)"
        log_failure "4" "meta_report_generation" "edge-meta-report exit $META_EXIT"
        PHASE4_OK=false
    fi
else
    warn "edge-meta-report not found — skipping"
    log_failure "4" "meta_report_missing" "edge-meta-report tool not available"
    PHASE4_OK=false
fi
if $PHASE4_OK; then
    emit_run_step_event "phase-4" "completed" "meta_report" ""
fi
echo ""

# ─── PHASE 5: State commit (claims + threads + event + digest) ───
# Tudo acontece aqui. Zero LLM. Um script, uma leitura do frontmatter.
echo "── Phase 5: State Commit ──"
ledger_record "phase-5" "ok"
emit_run_step_event "phase-5" "started" "state_commit" ""
REPORT_FOR_COMMIT="${REPORT_FILENAME:-}"
python3 - "$ENTRY_PATH" "$SLUG" "$REPORT_FOR_COMMIT" <<'PYEOF'
import sys, json, yaml, re, os, traceback, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

entry_path = sys.argv[1]
slug = sys.argv[2]
report_filename = sys.argv[3] if len(sys.argv) > 3 else ""

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"
def ok(msg): print(f"  {GREEN}OK{NC}: {msg}")
def warn(msg): print(f"  {YELLOW}WARN{NC}: {msg}")
def fail(msg): print(f"  {RED}FAIL{NC}: {msg}")

FAILURES_FILE = Path(os.environ.get("PIPELINE_FAILURES_FILE", os.path.expanduser("~/edge/logs/pipeline-failures.jsonl")))
FAILURES_FILE.parent.mkdir(parents=True, exist_ok=True)

tools_dir = Path(os.environ.get("TOOLS_DIR", str(Path.home() / "edge" / "tools")))
if str(tools_dir) not in sys.path:
    sys.path.insert(0, str(tools_dir))
try:
    from _shared.telemetry import log_workflow_observed  # type: ignore
except Exception:
    log_workflow_observed = None

def log_failure(phase, operation, error, tb=None):
    """Log pipeline failure to persistent JSONL for post-mortem analysis."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "phase": phase,
        "operation": operation,
        "error": str(error),
    }
    if tb:
        entry["traceback"] = tb
    try:
        with open(FAILURES_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Last resort — can't log the logger

# ── Ler frontmatter (uma vez) ──
try:
    raw = Path(entry_path).read_text()
    parts = raw.split("---", 2)
    fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
    fm = fm or {}
except Exception as e:
    fm = {}
    log_failure("5", "read_frontmatter", e, traceback.format_exc())
    warn(f"Frontmatter not read: {e}")

claims = fm.get("claims", [])
threads = fm.get("threads", [])
procedures = fm.get("procedure", [])
workflows_used = fm.get("workflows_used", [])
workflows_broken = fm.get("workflows_broken", [])
title = fm.get("title", slug)
today = datetime.now().strftime("%Y-%m-%d")

def _is_open(c):
    if isinstance(c, dict):
        return c.get("status", "").lower() in ("unverified", "open", "disputed")
    return isinstance(c, str) and c.startswith("!")

# ── 1. Claims check ──
try:
    if claims:
        open_count = sum(1 for c in claims if _is_open(c))
        ok(f"Claims: {len(claims)} ({open_count} open), {len(threads)} threads")
    else:
        warn("No claims. Add claims: and threads: to compact knowledge.")
except Exception as e:
    log_failure("5", "claims_check", e, traceback.format_exc())
    warn(f"Claims check failed: {e}")

# ── 2. Thread update ──
try:
    threads_dir = Path(os.environ.get("THREADS_DIR", os.path.expanduser("~/edge/threads")))
    updated_threads = []
    for tid in threads:
        tfile = threads_dir / f"{tid}.md"
        if not tfile.exists():
            continue
        content = tfile.read_text()
        content = re.sub(r"^updated:.*$", f"updated: {today}", content, flags=re.MULTILINE)
        tfile.write_text(content)
        updated_threads.append(tid)

    if updated_threads:
        ok(f"Threads updated: {', '.join(updated_threads)}")
except Exception as e:
    log_failure("5", "thread_update", e, traceback.format_exc())
    warn(f"Thread update failed: {e}")

# ── 2b. Procedure & workflow signals ──
try:
    state_dir = Path(os.environ.get("STATE_DIR", os.path.expanduser("~/edge/state")))
    state_dir.mkdir(parents=True, exist_ok=True)
    health_file = state_dir / "workflow-health.json"

    # Load existing health data
    health = {}
    if health_file.exists():
        try:
            health = json.loads(health_file.read_text())
        except Exception:
            health = {}

    citations = health.get("citations", {})
    updated = False

    # Process workflows_used (reinforcement)
    for wslug in workflows_used:
        if wslug not in citations:
            citations[wslug] = {"used": 0, "broken": 0, "last_cited": ""}
        citations[wslug]["used"] += 1
        citations[wslug]["last_cited"] = today
        updated = True
        if log_workflow_observed is not None:
            log_workflow_observed(
                wslug,
                mode="used",
                artifact=f"blog/entries/{slug}.md",
                cycle_id=os.environ.get("EDGE_CYCLE_ID"),
                title=title,
            )

    # Process workflows_broken (healing signal)
    for wslug in workflows_broken:
        if wslug not in citations:
            citations[wslug] = {"used": 0, "broken": 0, "last_cited": ""}
        citations[wslug]["broken"] += 1
        citations[wslug]["last_cited"] = today
        updated = True
        if log_workflow_observed is not None:
            log_workflow_observed(
                wslug,
                mode="broken",
                artifact=f"blog/entries/{slug}.md",
                cycle_id=os.environ.get("EDGE_CYCLE_ID"),
                title=title,
            )

    if updated:
        health["citations"] = citations
        health["updated_at"] = datetime.now(timezone.utc).isoformat()
        health_file.write_text(json.dumps(health, indent=2, ensure_ascii=False))

    # Report
    proc_anti = sum(1 for p in procedures if isinstance(p, str) and p.startswith("!"))
    parts = []
    if procedures:
        parts.append(f"Procedures: {len(procedures)} ({proc_anti} anti-patterns)")
    if workflows_used:
        parts.append(f"Workflows used: {', '.join(workflows_used)}")
    if workflows_broken:
        parts.append(f"Workflows broken: {', '.join(workflows_broken)}")
    if parts:
        ok("; ".join(parts))
    # No warning if empty — procedures are delta-only, not mandatory every time

except Exception as e:
    log_failure("5", "procedure_workflow", e, traceback.format_exc())
    warn(f"Procedure/workflow processing failed: {e}")

# ── 2c. Typed signals (edge-signal) ──
try:
    signal_types = ["autonomy", "strategy", "reflection", "friction", "decision", "serendipity"]
    signal_count = 0
    for stype in signal_types:
        items = fm.get(stype, [])
        if not items:
            continue
        for item in items:
            if isinstance(item, str) and item.strip():
                subprocess.run(
                    ["edge-signal", stype, item.strip(), "--source", slug],
                    capture_output=True, timeout=5
                )
                signal_count += 1
    if signal_count > 0:
        ok(f"Signals: {signal_count} emitted to state/signals/")
except Exception as e:
    log_failure("5", "typed_signals", e, traceback.format_exc())
    warn(f"Typed signals failed: {e}")

# ── 3. Event log (idempotent) ──
try:
    events_file = Path(os.environ.get("EVENTS_FILE", os.path.expanduser("~/edge/logs/events.jsonl")))
    artifacts = [f"blog/entries/{slug}.md"]
    if report_filename:
        artifacts.append(f"reports/{report_filename}")

    # Idempotency: skip if event for this slug already exists
    slug_artifact = f"blog/entries/{slug}.md"
    already_logged = False
    if events_file.exists():
        for line in events_file.read_text().splitlines():
            try:
                e = json.loads(line)
                if slug_artifact in e.get("artifacts", []):
                    already_logged = True
                    break
            except:
                pass

    if already_logged:
        ok(f"Event already exists for {slug} — skip (idempotent)")
    else:
        event = {
            "event_id": f"EVT-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "artifact_created",
            "summary": f"Published: {title}",
            "artifacts": artifacts,
        }
        if threads:
            event["thread_id"] = threads[0]
        if len(claims) > 0:
            event["claims_count"] = len(claims)
            event["open_claims"] = sum(1 for c in claims if _is_open(c))
        if procedures:
            event["procedures_count"] = len(procedures)
        if workflows_used:
            event["workflows_used"] = workflows_used
        if workflows_broken:
            event["workflows_broken"] = workflows_broken

        events_file.parent.mkdir(parents=True, exist_ok=True)
        with open(events_file, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        ok(f"Event: {event['event_id']}")
except Exception as e:
    log_failure("5", "event_log", e, traceback.format_exc())
    fail(f"Event log failed: {e}")

# ── 4. Digest (gera briefing.md) ──
try:
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from _shared.continuity import process_publication_continuity  # type: ignore

    current_dispatch_file = Path(os.environ.get("CURRENT_DISPATCH_FILE", os.path.expanduser("~/edge/state/current-dispatch.json")))
    primary_thread_id = None
    if current_dispatch_file.exists():
        try:
            dispatch_state = json.loads(current_dispatch_file.read_text())
            request_block = dispatch_state.get("request", {}) or {}
            primary_thread_id = (
                str(request_block.get("primary_thread_id") or "").strip()
                or str((request_block.get("args") or {}).get("thread_id") or "").strip()
                or None
            )
        except Exception:
            primary_thread_id = None

    continuity = process_publication_continuity(
        Path(entry_path),
        primary_thread_id=primary_thread_id,
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
    )
    delta = continuity.get("delta", {}) or {}
    validation = continuity.get("validation", {}) or {}
    judge = validation.get("judge", {}) or {}
    ok(
        "continuity: "
        f"{continuity.get('facts', {}).get('claims_count', 0)} claims, "
        f"{len(continuity.get('facts', {}).get('threads', []))} threads, "
        f"judge={judge.get('status', 'unknown')}, "
        f"primary_thread={delta.get('primary_thread') or 'none'}"
    )

    import subprocess
    result = subprocess.run(["edge-digest"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        ok("briefing.md updated")
    else:
        warn(f"edge-digest failed (exit {result.returncode})")
        log_failure("5", "digest", f"exit {result.returncode}: {result.stderr[:200]}")
except FileNotFoundError:
    warn("edge-digest not found")
except Exception as e:
    log_failure("5", "digest", e, traceback.format_exc())
    warn(f"edge-digest error: {e}")
PYEOF
emit_run_step_event "phase-5" "completed" "state_commit" ""

# ─── PHASE 5b: State audit (compare PRE vs POST, validate proposal) ───
echo "── Phase 5b: State Audit ──"
ledger_record "phase-5b" "ok"
emit_run_step_event "phase-5b" "started" "state_audit" ""
if command -v edge-state-audit &>/dev/null; then
    # Check if proposal exists (agent should have written it during the session)
    PROPOSAL_FILE="$META_DIR/${SLUG}.state-proposal.yaml"
    if [[ -f "$PROPOSAL_FILE" ]]; then
        ok "Proposal found: $(basename "$PROPOSAL_FILE")"
    else
        warn "No change proposal (state-proposal.yaml). Any change to protected files will be a violation."
    fi
    edge-state-audit audit --slug "$SLUG"
    STATE_AUDIT_EXIT=$?
    if [[ $STATE_AUDIT_EXIT -ge 4 ]]; then
        fail "State audit FAILED (exit $STATE_AUDIT_EXIT) — unproposed or divergent change"
        fail "Pipeline ABORTED. Fix the proposal or revert the changes."
        echo ""
        echo "========================================="
        echo -e " ${RED}ABORTED${NC}: State audit detected violation"
        echo "  Proposal: $PROPOSAL_FILE"
        echo "  Audit: $META_DIR/${SLUG}.state-audit.yaml"
        echo "========================================="
        emit_run_step_event "phase-5b" "failed" "state_audit" "state audit violation or divergence"
        exit 5
    fi
fi
if [[ $STATE_AUDIT_EXIT -eq 2 ]]; then
    emit_run_step_event "phase-5b" "failed" "state_audit" "state audit partial"
else
    emit_run_step_event "phase-5b" "completed" "state_audit" ""
fi
echo ""

# ─── PHASE 5c: Post-state meta-report (what actually changed) ───
echo "── Phase 5c: Post-state meta-report ──"
ledger_record "phase-5c" "ok"
emit_run_step_event "phase-5c" "started" "post_state_meta_report" ""
PHASE5C_OK=true
if command -v edge-meta-report &>/dev/null || [[ -x "$TOOLS_DIR/edge-meta-report" ]]; then
    POST_CMD="edge-meta-report --slug $SLUG --post-state"
    command -v edge-meta-report &>/dev/null || POST_CMD="$TOOLS_DIR/edge-meta-report --slug $SLUG --post-state"
    [[ -n "$ENTRY_PATH" ]] && POST_CMD="$POST_CMD --entry $ENTRY_PATH"

    POST_OUTPUT=$($POST_CMD 2>&1)
    POST_EXIT=$?
    if [[ $POST_EXIT -eq 0 ]]; then
        ok "$(echo "$POST_OUTPUT" | head -1)"
    else
        warn "post-state meta-report failed (exit $POST_EXIT)"
        PHASE5C_OK=false
    fi
else
    warn "edge-meta-report not found -- skipping post-state"
    PHASE5C_OK=false
fi
if $PHASE5C_OK; then
    emit_run_step_event "phase-5c" "completed" "post_state_meta_report" ""
else
    emit_run_step_event "phase-5c" "failed" "post_state_meta_report" "post-state meta-report unavailable or failed"
fi
echo ""

# ─── PHASE 6: Diffs + Git commit (audit trail) ───
echo "── Phase 6: Diffs + Git Commit ──"
ledger_record "phase-6" "ok"
emit_run_step_event "phase-6" "started" "diffs_and_git_commit" ""

# Note: BLOG_PORT, BLOG_AUTH_USER, BLOG_AUTH_PASS already exported by paths.sh

if python3 - "$ENTRY_PATH" "$SLUG" "$REPORT_FOR_COMMIT" "$COMMIT_REASON" "$STATE_AUDIT_EXIT" "$REPORT_RESULT" "$REPORT_HTML" "$META_REPORT_PATH" <<'PYPHASE5'
import sys, yaml, json, os, subprocess, urllib.request, traceback
from pathlib import Path
from datetime import datetime, timezone

entry_path, slug, report, reason = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
state_audit_exit = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].isdigit() else -1
report_result = sys.argv[6] if len(sys.argv) > 6 else "skip"
report_html = sys.argv[7] if len(sys.argv) > 7 else ""
meta_report_path = sys.argv[8] if len(sys.argv) > 8 else ""

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"
def ok(msg): print(f"  {GREEN}OK{NC}: {msg}")
def warn(msg): print(f"  {YELLOW}WARN{NC}: {msg}")
def fail(msg): print(f"  {RED}FAIL{NC}: {msg}")

FAILURES_FILE = Path(os.environ.get("PIPELINE_FAILURES_FILE", os.path.expanduser("~/edge/logs/pipeline-failures.jsonl")))
FAILURES_FILE.parent.mkdir(parents=True, exist_ok=True)

def log_failure(phase, operation, error, tb=None):
    """Log pipeline failure to persistent JSONL for post-mortem analysis."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "phase": phase,
        "operation": operation,
        "error": str(error),
    }
    if tb:
        entry["traceback"] = tb
    try:
        with open(FAILURES_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

def emit_scope_violation(payload):
    try:
        tools_dir = Path(
            os.environ.get("TOOLS_DIR")
            or (Path(os.environ.get("EDGE_REPO_DIR", os.environ.get("EDGE_DIR", str(Path.home() / "edge")))).expanduser() / "tools")
        )
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        from _shared.telemetry import emit_shadow_event  # type: ignore

        emit_shadow_event(
            "PublishCommitScopeViolation",
            actor="consolidate-state",
            cycle_id=os.environ.get("EDGE_CYCLE_ID") or None,
            payload=payload,
        )
    except Exception:
        pass

# ── Ler frontmatter ──
try:
    raw = Path(entry_path).read_text()
    parts = raw.split("---", 2)
    fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
    fm = fm or {}
except Exception as e:
    fm = {}
    log_failure("6", "read_frontmatter", e, traceback.format_exc())
    warn(f"Frontmatter not read in Phase 6: {e}")

title = fm.get("title", slug)
raw_claims = fm.get("claims", [])
threads = fm.get("threads", [])
tags = fm.get("tags", [])
meta_dir = Path(os.environ.get("META_DIR", os.path.expanduser("~/edge/meta-reports")))
proposal_path = meta_dir / f"{slug}.state-proposal.yaml"
audit_path = meta_dir / f"{slug}.state-audit.yaml"

# Normalize claims: accept both str ("!claim") and dict ({claim, status})
def _is_open(c):
    if isinstance(c, dict):
        return c.get("status", "").lower() in ("unverified", "open", "disputed")
    return isinstance(c, str) and c.startswith("!")

claims = raw_claims
verified = [c for c in claims if not _is_open(c)]
open_claims = [c for c in claims if _is_open(c)]

def _claim_text(c):
    """Extract claim text from str or dict format."""
    if isinstance(c, dict):
        return c.get("claim", c.get("text", str(c)))
    return str(c).lstrip("! ")

# ── 1. Captura diffs dos mini-repos (memory, skills, notes) ──
_edge_repo_dir = os.environ.get("EDGE_REPO_DIR", os.environ.get("EDGE_DIR", os.path.expanduser("~/edge")))
_notes_dir = os.environ.get("NOTES_DIR", os.path.join(os.environ.get("EDGE_STATE_DIR", os.path.expanduser("~/edge")), "notes"))
_memory_base = os.environ.get("MEMORY_BASE", os.path.expanduser("~/.claude/projects/memory"))
TRACKED = {
    _memory_base: "memory",
    os.path.expanduser("~/.claude/skills"): "skills",
    _notes_dir: "notes",
}

all_diffs = []
mini_repos_with_changes = []

for dirpath, prefix in TRACKED.items():
    try:
        git_dir = os.path.join(dirpath, ".git")
        if not os.path.isdir(git_dir):
            continue

        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=dirpath, capture_output=True, timeout=30)

        # Get staged diff
        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=3"],
            cwd=dirpath, capture_output=True, text=True, errors="replace", timeout=30
        )
        diff_output = result.stdout.strip()
        if not diff_output:
            continue

        mini_repos_with_changes.append((dirpath, prefix))

        # Split by file
        current_file = None
        current_lines = []

        for line in diff_output.split("\n"):
            if line.startswith("diff --git a/"):
                if current_file and current_lines:
                    all_diffs.append({
                        "path": f"{prefix}/{current_file}",
                        "diff": "\n".join(current_lines)
                    })
                file_parts = line.split(" b/", 1)
                current_file = file_parts[1] if len(file_parts) > 1 else line.split("a/", 1)[-1].split(" ")[0]
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_file and current_lines:
            all_diffs.append({
                "path": f"{prefix}/{current_file}",
                "diff": "\n".join(current_lines)
            })
    except Exception as e:
        log_failure("6", f"diff_mini_repo_{prefix}", e, traceback.format_exc())
        warn(f"Diff {prefix} failed: {e}")

# ── 2. Captura diffs do ~/edge/ (repo principal) ──
try:
    edge_dir = os.environ.get("EDGE_REPO_DIR", os.environ.get("EDGE_DIR", os.path.expanduser("~/edge")))
    edge_git_dir = Path(edge_dir) / ".git"
    if not edge_git_dir.exists():
        warn(f"EDGE_REPO_DIR is not a git repository; skipping scoped diff: {edge_dir}")
    else:
        tool_path = Path(edge_dir) / "tools" / "edge-publish-scope"
        changelog_path = Path(os.environ.get("BLOG_CHANGELOG_FILE", "")).expanduser()
        allowed_paths = [entry_path]
        if report_html:
            allowed_paths.append(report_html)
        if meta_report_path:
            allowed_paths.append(meta_report_path)
        if proposal_path.exists():
            allowed_paths.append(str(proposal_path))
        if audit_path.exists():
            allowed_paths.append(str(audit_path))
        if changelog_path and changelog_path.exists():
            allowed_paths.append(str(changelog_path))

        scope_cmd = [str(tool_path), "stage", "--slug", slug, "--json"]
        for allowed_path in allowed_paths:
            if allowed_path:
                scope_cmd.extend(["--allow", allowed_path])
        scope_result = subprocess.run(
            scope_cmd,
            cwd=edge_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        scope_payload = {}
        if scope_result.stdout.strip():
            try:
                scope_payload = json.loads(scope_result.stdout)
            except Exception:
                scope_payload = {"raw": scope_result.stdout.strip()}
        if scope_result.returncode == 2:
            emit_scope_violation({
                "slug": slug,
                "allowed_paths": scope_payload.get("allowed_paths", []),
                "illegal_files": scope_payload.get("illegal_files", []),
            })
            illegal = scope_payload.get("illegal_files", []) or []
            if illegal:
                warn(f"SCOPE GUARD: {len(illegal)} file(s) outside publish allowlist in staging:")
                for item in illegal:
                    warn(f"  ↳ {item}")
            raise SystemExit(2)
        if scope_result.returncode != 0:
            raise RuntimeError(scope_result.stderr.strip() or scope_result.stdout.strip() or "edge-publish-scope failed")

        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=3", "--", ".", ":(exclude)*.venv*", ":(exclude)*.b64", ":(exclude)*.png", ":(exclude)*.jpg", ":(exclude)*.pdf", ":(exclude)*.db"],
            cwd=edge_dir, capture_output=True, text=True, errors="replace", timeout=30
        )
        edge_diff = result.stdout.strip()
        if edge_diff:
            current_file = None
            current_lines = []
            for line in edge_diff.split("\n"):
                if line.startswith("diff --git a/"):
                    if current_file and current_lines:
                        all_diffs.append({
                            "path": f"edge/{current_file}",
                            "diff": "\n".join(current_lines)
                        })
                    file_parts = line.split(" b/", 1)
                    current_file = file_parts[1] if len(file_parts) > 1 else line.split("a/", 1)[-1].split(" ")[0]
                    current_lines = [line]
                else:
                    current_lines.append(line)
            if current_file and current_lines:
                all_diffs.append({
                    "path": f"edge/{current_file}",
                    "diff": "\n".join(current_lines)
                })
except Exception as e:
    log_failure("6", "diff_edge_repo", e, traceback.format_exc())
    warn(f"Diff edge repo failed: {e}")

# ── 3. Posta diffs no blog API ──
if all_diffs:
    payload = json.dumps({"slug": slug, "files": all_diffs}).encode("utf-8")
    blog_url = os.environ.get("BLOG_URL", f"http://localhost:{os.environ.get('BLOG_PORT', '8766')}")
    auth_user = os.environ.get("BLOG_AUTH_USER", "")
    auth_pass = os.environ.get("BLOG_AUTH_PASS", "")
    diffs_headers = {"Content-Type": "application/json"}
    if auth_user and auth_pass:
        import base64
        cred = base64.b64encode(f"{auth_user}:{auth_pass}".encode()).decode()
        diffs_headers["Authorization"] = f"Basic {cred}"
    try:
        req = urllib.request.Request(
            f"{blog_url}/api/diffs",
            data=payload,
            headers=diffs_headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        adds = sum(sum(1 for l in d["diff"].split("\n") if l.startswith("+") and not l.startswith("+++")) for d in all_diffs)
        dels = sum(sum(1 for l in d["diff"].split("\n") if l.startswith("-") and not l.startswith("---")) for d in all_diffs)
        ok(f"Diffs: {len(all_diffs)} files (+{adds} -{dels})")
    except Exception as e:
        log_failure("6", "blog_api_diffs", e, traceback.format_exc())
        warn(f"Blog API diffs: {e}")
else:
    ok("No state diffs")

# ── 4. Gerar commit message estruturada ──
# State audit status
state_label = {0: "ok", 2: "partial", 4: "divergence", 5: "violation"}.get(state_audit_exit, "skip" if state_audit_exit < 0 else "unknown")

lines = [f"publish: {slug} [state:{state_label}]", ""]

if reason:
    lines.append(f"reason: {reason}")
else:
    lines.append(f"reason: publication via consolidate-state")
lines.append("")

# Pipeline status
pipeline_phases = ["phase0", "phase0.5", "phase1"]
if report_result != "skip":
    pipeline_phases.append("phase2")
pipeline_phases.extend(["phase3", "phase4", "phase5", "phase5b", "phase6"])
pipeline_status = "ok"
failures = []
if report_result == "fail":
    failures.append("phase2: report generation failed")
    pipeline_status = "partial"
if state_audit_exit == 2:
    failures.append("phase5b: state audit partial (proposed changes not executed)")
    pipeline_status = "partial"

lines.append(f"pipeline: {','.join(pipeline_phases)}")
lines.append(f"pipeline-status: {pipeline_status}")
lines.append(f"state-status: {state_label}")
if failures:
    lines.append(f"failures:")
    for f in failures:
        lines.append(f"  - {f}")
lines.append("")

# State audit summary (if audit ran)
if audit_path.exists():
    try:
        audit_data = yaml.safe_load(audit_path.read_text())
        results = audit_data.get("results", [])
        ok_count = sum(1 for r in results if r.get("result") == "ok")
        warn_count = sum(1 for r in results if r.get("result") == "omitted")
        fail_count = sum(1 for r in results if r.get("result") in ("violation", "divergence"))
        lines.append(f"state-changes: {ok_count} ok, {warn_count} omitted, {fail_count} violations")
        for r in results:
            if r.get("result") != "ok":
                lines.append(f"  - {r['path']}: {r.get('proposed_action','?')}->{r.get('executed_action','?')} [{r['result']}]")
        lines.append("")
    except Exception as e:
        log_failure("6", "audit_summary", e, traceback.format_exc())
        warn(f"Audit summary failed: {e}")

if verified:
    lines.append(f"learned ({len(verified)}):")
    for c in verified:
        lines.append(f"  - {_claim_text(c)}")
    lines.append("")

if open_claims:
    lines.append(f"gaps ({len(open_claims)}):")
    for c in open_claims:
        lines.append(f"  - {_claim_text(c)}")
    lines.append("")

procedures = fm.get("procedure", [])
wf_used = fm.get("workflows_used", [])
wf_broken = fm.get("workflows_broken", [])

if procedures:
    proc_new = [p for p in procedures if isinstance(p, str) and not p.startswith("!")]
    proc_anti = [p for p in procedures if isinstance(p, str) and p.startswith("!")]
    if proc_new:
        lines.append(f"procedures ({len(proc_new)}):")
        for p in proc_new:
            lines.append(f"  - {p}")
        lines.append("")
    if proc_anti:
        lines.append(f"anti-patterns ({len(proc_anti)}):")
        for p in proc_anti:
            lines.append(f"  - {p.lstrip('! ')}")
        lines.append("")

if wf_used:
    lines.append(f"workflows-used: {', '.join(wf_used)}")
if wf_broken:
    lines.append(f"workflows-broken: {', '.join(wf_broken)}")

if threads:
    lines.append(f"threads: {', '.join(threads)}")
if tags:
    lines.append(f"tags: {', '.join(tags)}")
if report:
    lines.append(f"report: {report}")
if proposal_path.exists():
    lines.append(f"proposal: {proposal_path.name}")
if audit_path.exists():
    lines.append(f"audit: {audit_path.name}")

# ── Execution summary from ops-hotspots.json ──
try:
    hotspots_path = Path(os.environ.get("OPS_HOTSPOTS", os.path.expanduser("~/edge/state/ops-hotspots.json")))
    if hotspots_path.exists():
        hotspots = json.loads(hotspots_path.read_text())
        incidents = hotspots.get("incidents", [])
        # Filter to failure incidents (signature contains non-success error_class)
        fail_incidents = [i for i in incidents if ":success:" not in i.get("signature", "")]
        if fail_incidents:
            total_retries = sum(i.get("count", 0) for i in fail_incidents)
            total_wasted = sum(i.get("total_wasted_ms", 0) for i in fail_incidents)
            # Extract tool names with counts from signatures (tool:error_class:phase)
            tool_counts = {}
            for i in fail_incidents:
                tool_name = i.get("signature", "").split(":")[0]
                if tool_name:
                    tool_counts[tool_name] = tool_counts.get(tool_name, 0) + i.get("count", 0)
            tools_str = ",".join(f"{t}({c})" for t, c in sorted(tool_counts.items(), key=lambda x: -x[1]))
            lines.append(f"execution-summary: retries={total_retries} tools_failed={tools_str} wasted_ms={total_wasted}")
except Exception:
    pass  # Backwards compatible — omit on any error

lines.append("")
meta = {
    "title": title,
    "claims": len(claims),
    "open": len(open_claims),
    "procedures": len(procedures),
    "workflows_used": wf_used,
    "workflows_broken": wf_broken,
    "threads": threads,
    "tags": tags,
    "state": state_label,
    "pipeline": pipeline_status,
}
lines.append(json.dumps(meta, ensure_ascii=False))
commit_msg = "\n".join(lines)

# ── 5. Commit mini-repos com mensagem estruturada ──
for dirpath, prefix in mini_repos_with_changes:
    try:
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=dirpath, capture_output=True, timeout=30
        )
    except Exception as e:
        log_failure("6", f"commit_mini_repo_{prefix}", e, traceback.format_exc())
        warn(f"Commit {prefix} failed: {e}")

# ── 6. Commit ~/edge/ ──
try:
    if not (Path(edge_dir) / ".git").exists():
        warn(f"EDGE_REPO_DIR is not a git repository; skipping git commit: {edge_dir}")
    else:
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=edge_dir, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=edge_dir, capture_output=True, text=True, timeout=10
            )
            ok(f"Commit: {hash_result.stdout.strip()}")
        else:
            warn("Nothing to commit or git failed")
except Exception as e:
    log_failure("6", "commit_edge", e, traceback.format_exc())
    fail(f"Git commit failed: {e}")
PYPHASE5
then
    emit_run_step_event "phase-6" "completed" "diffs_and_git_commit" ""
else
    emit_run_step_event "phase-6" "failed" "diffs_and_git_commit" "phase 6 failed"
    ALL_OK=false
fi

echo ""
echo "========================================="
if $ALL_OK && [[ "$REPORT_RESULT" != "fail" ]]; then
    echo -e " ${GREEN}PUBLISHED COMPLETE${NC}: $SLUG"
    [[ -n "$REPORT_FILENAME" ]] && echo " Content report: $REPORT_FILENAME"
    [[ -n "$META_REPORT_PATH" ]] && echo " Meta-report: $META_REPORT_PATH"
    [[ -n "$META_REPORT_PATH" ]] && echo ""
    [[ -n "$META_REPORT_PATH" ]] && echo -e " ${YELLOW}→ Read meta-report BEFORE editing state${NC}"
    echo "========================================="
    # Survival instinct: write success marker
    HEALTH_OK="$HEALTH_DIR/last_success"
    mkdir -p "$HEALTH_OK"
    printf '{"ts":"%s","slug":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SLUG" > "$HEALTH_OK/consolidate.ok"
    ledger_record "pipeline-end" "ok"
    emit_run_step_event "pipeline" "completed" "pipeline_end" ""
    exit 0
elif $ALL_OK; then
    echo -e " ${YELLOW}PARTIAL${NC}: Entry OK, report with issues"
    [[ -n "$META_REPORT_PATH" ]] && echo " Meta-report: $META_REPORT_PATH"
    echo "========================================="
    ledger_record "pipeline-end" "partial"
    emit_run_step_event "pipeline" "degraded" "pipeline_end" "partial publication"
    exit 0
else
    echo -e " ${RED}ISSUES${NC}: verify manually"
    echo "========================================="
    ledger_record "pipeline-end" "fail"
    emit_run_step_event "pipeline" "failed" "pipeline_end" "verification issues"
    exit 2
fi
