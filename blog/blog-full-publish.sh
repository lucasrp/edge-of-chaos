#!/bin/bash
# blog-full-publish — Pipeline completo: entry + report + meta-report + state commit
#
# Uso:
#   blog-full-publish <entry.md>                       # entry + meta-report (content report opcional)
#   blog-full-publish <entry.md> <report.yaml>         # entry + content report + meta-report
#   blog-full-publish <entry.md> <report.html>         # entry + content report pre-gerado + meta-report
#
# Pipeline (7 fases):
#   0.  Frontmatter injection (report: field)
#   0.5 Review gate (LLM-as-judge, content report only)
#   1.  Blog entry (blog-publish.sh)
#   2.  Content report (generate_report.py, optional)
#   3.  Verificação (API, frontmatter, files)
#   3.4 LLM cost injection
#   4.  Meta-report (state delta + scratchpad + adversarial → cognitive mirror)
#   5.  State commit (claims + threads + event + digest)
#   6.  Diffs + Git commit (audit trail)
#
# Exit codes: 0 = tudo OK, 1 = erro fatal, 2 = parcial, 3 = review gate falhou
#
# Flags:
#   --skip-review      Pular o review gate (LLM-as-judge)
#   --review-only      Rodar so o review gate, sem publicar
#   --scratchpad PATH  Scratchpad para meta-report (default: /tmp/edge-scratch-active.md)
#   --no-adversarial   Pular edge-consult no meta-report
#   --no-meta          Pular meta-report (Phase 4)

set -uo pipefail

# --- Load shared paths (branding, memory, blog config) ---
# shellcheck source=../config/paths.sh
source "$(dirname "$0")/../config/paths.sh"

# Parse flags
SKIP_REVIEW=false
REVIEW_ONLY=false
RECOVER=false
NO_META=false
NO_ADVERSARIAL=false
SCRATCHPAD=""
COMMIT_REASON=""
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-review) SKIP_REVIEW=true; shift ;;
        --review-only) REVIEW_ONLY=true; shift ;;
        --recover) RECOVER=true; shift ;;
        --no-meta) NO_META=true; shift ;;
        --no-adversarial) NO_ADVERSARIAL=true; shift ;;
        --scratchpad) SCRATCHPAD="$2"; shift 2 ;;
        --reason) COMMIT_REASON="$2"; shift 2 ;;
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

if [[ -z "$ENTRY_PATH" && "$RECOVER" == "false" ]]; then
    echo "Uso: blog-full-publish <entry.md> [report.yaml|report.html]"
    echo "  --skip-review      Pular review gate"
    echo "  --recover          Detectar e re-executar Phase 5/6 de publicações incompletas"
    echo "  --scratchpad PATH  Scratchpad para meta-report"
    echo "  --no-adversarial   Pular edge-consult no meta-report"
    echo "  --no-meta          Pular meta-report (Phase 4)"
    exit 1
fi

# ─── RECOVER MODE: re-run Phase 5/6 for entries that have no git commit ───
if [[ "$RECOVER" == "true" ]]; then
    echo "========================================="
    echo " blog-full-publish --recover"
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
            VISIBLE=$(curl -s -m 3 "$BLOG_URL/blog/entries/" 2>/dev/null | python3 -c "
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

                # Run Phase 5+6 only (reuse this script with --no-meta --skip-review)
                bash "$0" --skip-review --no-meta --reason "recover: Phase 5/6 re-run" "$entry_file" ${REPORT_FN:+} 2>&1 | tail -5
                RECOVERED=$((RECOVERED + 1))
            else
                echo "    Entry NOT visible — needs full republish (run without --recover)"
            fi
        fi
    done

    if [[ $RECOVERED -eq 0 ]]; then
        echo "  Todas as entries têm commit. Nada para recuperar."
    else
        echo ""
        echo "  Recuperadas: $RECOVERED entries"
    fi
    exit 0
fi

# Resolve to absolute
[[ "$ENTRY_PATH" = /* ]] || ENTRY_PATH="$(pwd)/$ENTRY_PATH"
[[ -n "$REPORT_INPUT" && ! "$REPORT_INPUT" = /* ]] && REPORT_INPUT="$(pwd)/$REPORT_INPUT"

SLUG=$(basename "$ENTRY_PATH" .md)
REPORT_HTML=""
REPORT_FILENAME=""
REPORT_RESULT="skip"
TOTAL_LLM_COST="0"
META_REPORT_PATH=""

# ─── GUARDRAIL: Regra #0 — toda publicação gera meta-report ───
# Content report (YAML/HTML) é opcional. Meta-report é sempre gerado (Phase 4).
if [[ -z "$REPORT_INPUT" ]]; then
    echo -e "  ${YELLOW}INFO${NC}: Sem content report. Meta-report será gerado (Phase 4)."
fi

STATE_AUDIT_EXIT=0

echo "========================================="
echo " blog-full-publish: $SLUG"
echo "========================================="
echo ""

# ─── PHASE 0a: State snapshot (PRE — capture protected files before anything changes) ───
# If agent already took snapshot (before making state changes), skip.
echo "── Phase 0a: State Snapshot ──"
if command -v edge-state-audit &>/dev/null; then
    PRE_SNAPSHOT="$EDGE_DIR/state-snapshots/${SLUG}.pre.yaml"
    if [[ -f "$PRE_SNAPSHOT" ]]; then
        ok "Snapshot PRE já existe (agente capturou antes das mudanças)"
    else
        edge-state-audit snapshot --slug "$SLUG"
    fi
else
    warn "edge-state-audit não encontrado — skipping state audit"
fi
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
            # Inject report: field after the last frontmatter field (before closing ---)
            python3 -c "
raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
if len(parts) >= 3:
    fm_text = parts[1].rstrip()
    fm_text += '\nreport: $REPORT_FILENAME\n'
    result = '---' + fm_text + '---' + parts[2]
    open('$ENTRY_PATH', 'w').write(result)
    print('  OK: report: $REPORT_FILENAME injetado no frontmatter')
"
            echo ""
        fi
    fi
fi

# ─── PHASE 0.5: Review Gate (LLM-as-judge) ───
if [[ -n "$REPORT_INPUT" && ("$REPORT_INPUT" == *.yaml || "$REPORT_INPUT" == *.yml) && "$SKIP_REVIEW" == "false" ]]; then
    if command -v review-gate &>/dev/null; then
        echo "── Phase 0.5: Review Gate ──"
        # Detect skill from YAML filename (spec-SKILL-slug.yaml)
        YAML_BASENAME=$(basename "$REPORT_INPUT")
        SKILL_NAME=""
        if [[ "$YAML_BASENAME" =~ ^spec-([a-z]+)- ]]; then
            SKILL_NAME="${BASH_REMATCH[1]}"
        fi

        REVIEW_CMD="review-gate $REPORT_INPUT --json"
        [[ -n "$SKILL_NAME" ]] && REVIEW_CMD="$REVIEW_CMD --skill $SKILL_NAME"

        REVIEW_JSON=$($REVIEW_CMD 2>/dev/null)
        REVIEW_EXIT=$?

        # Extract overall score and total cost from full --json output
        REVIEW_SCORE=$(echo "$REVIEW_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    fr = d.get('final_review', d)
    print(fr.get('overall', 0))
except:
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
except:
    print('0')
" 2>/dev/null)
        TOTAL_LLM_COST="$REVIEW_COST"

        if [[ $REVIEW_EXIT -eq 0 ]]; then
            ok "Review gate PASS (overall: ${REVIEW_SCORE}/5.0, cost: \$${REVIEW_COST})"
        elif [[ $REVIEW_EXIT -eq 1 ]]; then
            fail "Review gate FAIL (overall: ${REVIEW_SCORE}/5.0, cost: \$${REVIEW_COST})"
            # Show suggestions
            echo "$REVIEW_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('final_review', d)
issues = r.get('critical_issues', [])
if issues:
    print('  Critical:')
    for i in issues: print(f'    - {i}')
for s in r.get('suggestions', [])[:5]:
    print(f'  - {s}')
" 2>/dev/null
            if [[ "$REVIEW_ONLY" == "true" ]]; then
                echo ""
                echo "Review-only mode. Ajuste o YAML e tente novamente."
                exit 3
            fi
            echo ""
            echo "  Publicação bloqueada. Use --skip-review para forçar."
            exit 3
        else
            warn "Review gate erro (API/config) — continuando sem review"
        fi

        if [[ "$REVIEW_ONLY" == "true" ]]; then
            echo ""
            echo "Review-only mode. Nada publicado."
            exit 0
        fi
        echo ""
    fi
fi

# ─── PHASE 1: Blog entry ───
echo "── Phase 1: Blog Entry ──"
if CALLED_FROM_FULL_PUBLISH=1 bash "$BLOG_DIR/blog-publish.sh" "$ENTRY_PATH"; then
    ok "Entry publicada"
else
    fail "blog-publish.sh falhou"
    exit 1
fi
echo ""

# ─── PHASE 2: Report (opcional) ───
if [[ -n "$REPORT_INPUT" ]]; then
    echo "── Phase 2: Report ──"

    if [[ ! -f "$REPORT_INPUT" ]]; then
        fail "Report não encontrado: $REPORT_INPUT"
        REPORT_RESULT="fail"
    elif [[ "$REPORT_INPUT" == *.yaml || "$REPORT_INPUT" == *.yml ]]; then
        # Generate HTML from YAML
        REPORT_HTML="$REPORTS_DIR/$REPORT_FILENAME"
        echo "  Gerando HTML de $(basename "$REPORT_INPUT")..."
        if python3 "$TOOLS_DIR/generate_report.py" --yaml "$REPORT_INPUT" --output "$REPORT_HTML" 2>&1; then
            ok "Report gerado: $REPORT_FILENAME"
            REPORT_RESULT="ok"
        else
            fail "generate_report.py falhou"
            REPORT_RESULT="fail"
        fi
    elif [[ "$REPORT_INPUT" == *.html ]]; then
        # Pre-generated HTML — copy to reports dir if not already there
        if [[ "$(dirname "$REPORT_INPUT")" != "$REPORTS_DIR" ]]; then
            cp "$REPORT_INPUT" "$REPORTS_DIR/$REPORT_FILENAME"
        fi
        REPORT_HTML="$REPORTS_DIR/$REPORT_FILENAME"
        if [[ -f "$REPORT_HTML" ]]; then
            ok "Report HTML: $REPORT_FILENAME"
            REPORT_RESULT="ok"
        else
            fail "Report HTML não encontrado"
            REPORT_RESULT="fail"
        fi
    else
        warn "Formato de report não reconhecido: $REPORT_INPUT"
        REPORT_RESULT="fail"
    fi

    # Index report
    if [[ "$REPORT_RESULT" == "ok" && -n "$REPORT_HTML" ]]; then
        echo "  Indexando report..."
        if command -v edge-index &>/dev/null; then
            if edge-index "$REPORT_HTML" 2>/dev/null; then
                ok "Report indexado"
            else
                warn "edge-index retornou erro (não-fatal)"
            fi
        else
            warn "edge-index não encontrado"
        fi
    fi
    echo ""
fi

# ─── PHASE 3: Verificacao final ───
echo "── Phase 3: Verificação ──"
ALL_OK=true

# Entry visible?
VISIBLE=$(curl -s -m 5 "$BLOG_URL/blog/entries/" 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    found = any(e.get('slug') == '$SLUG' for e in data)
    print('OK' if found else 'NOT_FOUND')
except:
    print('ERROR')
" 2>&1)
if [[ "$VISIBLE" == "OK" ]]; then
    ok "Entry visível na API"
else
    warn "Entry NÃO visível na API ($VISIBLE)"
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
        ALL_OK=false
    fi
fi

# Report file exists?
if [[ -n "$REPORT_HTML" && "$REPORT_RESULT" == "ok" ]]; then
    if [[ -f "$REPORT_HTML" ]]; then
        SIZE=$(du -h "$REPORT_HTML" | cut -f1)
        ok "Report file: $REPORT_FILENAME ($SIZE)"
    else
        fail "Report desapareceu: $REPORT_HTML"
        ALL_OK=false
    fi
fi

# ─── PHASE 3.4: Inject llm_cost into frontmatter ───
if [[ "$TOTAL_LLM_COST" != "0" && "$TOTAL_LLM_COST" != "" ]]; then
    python3 -c "
import yaml

raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
if len(parts) >= 3:
    fm = yaml.safe_load(parts[1]) or {}
    fm['llm_cost'] = '\$$TOTAL_LLM_COST'
    fm_text = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    result = '---\n' + fm_text + '---' + parts[2]
    open('$ENTRY_PATH', 'w').write(result)
" 2>/dev/null
    ok "llm_cost: \$$TOTAL_LLM_COST injetado no frontmatter"
fi

# ─── PHASE 4: Meta-report (cognitive mirror) ───
# Captures state delta + scratchpad + adversarial BEFORE state commit.
# Agent reads this before making manual state changes (MEMORY.md, debugging.md, etc.)
if [[ "$NO_META" == "false" ]]; then
    echo ""
    echo "── Phase 4: Meta-report ──"
    if command -v edge-meta-report &>/dev/null || [[ -x "$TOOLS_DIR/edge-meta-report" ]]; then
        META_CMD="edge-meta-report --slug $SLUG --entry $ENTRY_PATH"
        # Use tools dir if not in PATH
        command -v edge-meta-report &>/dev/null || META_CMD="$TOOLS_DIR/edge-meta-report --slug $SLUG --entry $ENTRY_PATH"

        [[ -n "$SCRATCHPAD" ]] && META_CMD="$META_CMD --scratchpad $SCRATCHPAD"
        [[ "$NO_ADVERSARIAL" == "true" ]] && META_CMD="$META_CMD --no-adversarial"

        META_OUTPUT=$($META_CMD 2>&1)
        META_EXIT=$?

        if [[ $META_EXIT -eq 0 ]]; then
            META_REPORT_PATH=$(echo "$META_OUTPUT" | head -1 | sed 's/^OK: //')
            ok "Meta-report: $(basename "$META_REPORT_PATH")"
            if echo "$META_OUTPUT" | grep -q "Scratchpad:"; then
                ARCHIVED=$(echo "$META_OUTPUT" | grep "Scratchpad:" | sed 's/.*Scratchpad: //')
                ok "Scratchpad arquivado: $(basename "$ARCHIVED")"
            fi
        else
            warn "edge-meta-report falhou (exit $META_EXIT)"
        fi
    else
        warn "edge-meta-report não encontrado — skipping"
    fi
fi
echo ""

# ─── PHASE 5: State commit (claims + threads + event + digest) ───
# Tudo acontece aqui. Zero LLM. Um script, uma leitura do frontmatter.
echo "── Phase 5: State Commit ──"
REPORT_FOR_COMMIT="${REPORT_FILENAME:-}"
python3 - "$ENTRY_PATH" "$SLUG" "$REPORT_FOR_COMMIT" <<'PYEOF'
import sys, json, yaml, re, os, traceback
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

FAILURES_FILE = Path.home() / "edge" / "logs" / "pipeline-failures.jsonl"
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
    warn(f"Frontmatter não lido: {e}")

claims = fm.get("claims", [])
threads = fm.get("threads", [])
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
        ok(f"Claims: {len(claims)} ({open_count} abertas), {len(threads)} fios")
    else:
        warn("Sem claims. Adicione claims: e threads: para compactar conhecimento.")
except Exception as e:
    log_failure("5", "claims_check", e, traceback.format_exc())
    warn(f"Claims check falhou: {e}")

# ── 2. Thread update ──
try:
    threads_dir = Path.home() / "edge" / "threads"
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
        ok(f"Threads atualizados: {', '.join(updated_threads)}")
except Exception as e:
    log_failure("5", "thread_update", e, traceback.format_exc())
    warn(f"Thread update falhou: {e}")

# ── 3. Event log ──
try:
    events_file = Path.home() / "edge" / "logs" / "events.jsonl"
    artifacts = [f"blog/entries/{slug}.md"]
    if report_filename:
        artifacts.append(f"reports/{report_filename}")

    event = {
        "event_id": f"EVT-{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "artifact_created",
        "summary": f"Publicado: {title}",
        "artifacts": artifacts,
    }
    if threads:
        event["thread_id"] = threads[0]
    if len(claims) > 0:
        event["claims_count"] = len(claims)
        event["open_claims"] = sum(1 for c in claims if _is_open(c))

    events_file.parent.mkdir(parents=True, exist_ok=True)
    with open(events_file, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    ok(f"Evento: {event['event_id']}")
except Exception as e:
    log_failure("5", "event_log", e, traceback.format_exc())
    fail(f"Event log falhou: {e}")

# ── 4. Digest (gera briefing.md) ──
try:
    import subprocess
    result = subprocess.run(["edge-digest"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        ok("briefing.md atualizado")
    else:
        warn(f"edge-digest falhou (exit {result.returncode})")
        log_failure("5", "digest", f"exit {result.returncode}: {result.stderr[:200]}")
except FileNotFoundError:
    warn("edge-digest não encontrado")
except Exception as e:
    log_failure("5", "digest", e, traceback.format_exc())
    warn(f"edge-digest erro: {e}")
PYEOF

# ─── PHASE 5b: State audit (compare PRE vs POST, validate proposal) ───
echo "── Phase 5b: State Audit ──"
if command -v edge-state-audit &>/dev/null; then
    # Check if proposal exists (agent should have written it during the session)
    PROPOSAL_FILE="$EDGE_DIR/meta-reports/${SLUG}.state-proposal.yaml"
    if [[ -f "$PROPOSAL_FILE" ]]; then
        ok "Proposta encontrada: $(basename "$PROPOSAL_FILE")"
    else
        warn "Sem proposta de mudanças (state-proposal.yaml). Qualquer mudança em arquivo protegido será violação."
    fi
    edge-state-audit audit --slug "$SLUG"
    STATE_AUDIT_EXIT=$?
    if [[ $STATE_AUDIT_EXIT -ge 4 ]]; then
        fail "State audit FALHOU (exit $STATE_AUDIT_EXIT) — mudança não proposta ou divergente"
        fail "Pipeline ABORTADO. Corrija a proposta ou reverta as mudanças."
        echo ""
        echo "========================================="
        echo -e " ${RED}ABORTADO${NC}: State audit detectou violação"
        echo "  Proposal: $PROPOSAL_FILE"
        echo "  Audit: $EDGE_DIR/meta-reports/${SLUG}.state-audit.yaml"
        echo "========================================="
        exit 5
    fi
fi
echo ""

# ─── PHASE 6: Diffs + Git commit (audit trail) ───
echo "── Phase 6: Diffs + Git Commit ──"

python3 - "$ENTRY_PATH" "$SLUG" "$REPORT_FOR_COMMIT" "$COMMIT_REASON" "$STATE_AUDIT_EXIT" "$REPORT_RESULT" <<'PYPHASE5'
import sys, yaml, json, os, subprocess, urllib.request, traceback
from pathlib import Path
from datetime import datetime, timezone

entry_path, slug, report, reason = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
state_audit_exit = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].isdigit() else -1
report_result = sys.argv[6] if len(sys.argv) > 6 else "skip"

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"
def ok(msg): print(f"  {GREEN}OK{NC}: {msg}")
def warn(msg): print(f"  {YELLOW}WARN{NC}: {msg}")
def fail(msg): print(f"  {RED}FAIL{NC}: {msg}")

FAILURES_FILE = Path.home() / "edge" / "logs" / "pipeline-failures.jsonl"
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

# ── Ler frontmatter ──
try:
    raw = Path(entry_path).read_text()
    parts = raw.split("---", 2)
    fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
    fm = fm or {}
except Exception as e:
    fm = {}
    log_failure("6", "read_frontmatter", e, traceback.format_exc())
    warn(f"Frontmatter não lido em Phase 6: {e}")

title = fm.get("title", slug)
raw_claims = fm.get("claims", [])
threads = fm.get("threads", [])
tags = fm.get("tags", [])

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
_edge_dir = os.environ.get("EDGE_DIR", os.path.expanduser("~/edge"))
_memory_base = os.environ.get("MEMORY_BASE", os.path.expanduser("~/.claude/projects/memory"))
TRACKED = {
    _memory_base: "memory",
    os.path.expanduser("~/.claude/skills"): "skills",
    os.path.join(_edge_dir, "notes"): "notes",
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
        warn(f"Diff {prefix} falhou: {e}")

# ── 2. Captura diffs do ~/edge/ (repo principal) ──
try:
    edge_dir = os.environ.get("EDGE_DIR", os.path.expanduser("~/edge"))
    subprocess.run(["git", "add", "-A"], cwd=edge_dir, capture_output=True, timeout=30)

    # ORPHAN GUARD: unstage blog entries/reports/meta-reports that don't belong to this slug.
    # Prevents files written to disk but never published via blog-full-publish from being
    # swept into another slug's commit by git add -A. (Root cause of orphan entries bug.)
    staged_result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=edge_dir, capture_output=True, text=True, timeout=10
    )
    if staged_result.returncode == 0 and staged_result.stdout.strip():
        staged_files = staged_result.stdout.strip().split("\n")
        orphans = []
        for f in staged_files:
            is_entry = f.startswith("blog/entries/") and f.endswith(".md")
            is_report = f.startswith("reports/") and (f.endswith(".html") or f.endswith(".yaml"))
            is_meta = f.startswith("meta-reports/")
            if (is_entry or is_report or is_meta) and slug not in f:
                orphans.append(f)
        if orphans:
            warn(f"ORPHAN GUARD: {len(orphans)} arquivo(s) de OUTRO slug no staging — removendo:")
            for o in orphans:
                warn(f"  ↳ {o}")
            subprocess.run(
                ["git", "reset", "HEAD", "--"] + orphans,
                cwd=edge_dir, capture_output=True, timeout=10
            )
            warn("Publique arquivos órfãos via blog-full-publish separadamente.")

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
    warn(f"Diff edge repo falhou: {e}")

# ── 3. Posta diffs no blog API ──
if all_diffs:
    payload = json.dumps({"slug": slug, "files": all_diffs}).encode("utf-8")
    try:
        _blog_url = os.environ.get("BLOG_URL", "http://localhost:8766")
        req = urllib.request.Request(
            f"{_blog_url}/api/diffs",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        adds = sum(sum(1 for l in d["diff"].split("\n") if l.startswith("+") and not l.startswith("+++")) for d in all_diffs)
        dels = sum(sum(1 for l in d["diff"].split("\n") if l.startswith("-") and not l.startswith("---")) for d in all_diffs)
        ok(f"Diffs: {len(all_diffs)} arquivos (+{adds} -{dels})")
    except Exception as e:
        log_failure("6", "blog_api_diffs", e, traceback.format_exc())
        warn(f"Blog API diffs: {e}")
else:
    ok("Sem diffs de estado")

# ── 4. Gerar commit message estruturada ──
# State audit status
state_label = {0: "ok", 2: "partial", 4: "divergence", 5: "violation"}.get(state_audit_exit, "skip" if state_audit_exit < 0 else "unknown")

lines = [f"publish: {slug} [state:{state_label}]", ""]

if reason:
    lines.append(f"reason: {reason}")
else:
    lines.append(f"reason: publicação via blog-full-publish")
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
proposal_path = Path.home() / "edge" / "meta-reports" / f"{slug}.state-proposal.yaml"
audit_path = Path.home() / "edge" / "meta-reports" / f"{slug}.state-audit.yaml"
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
        warn(f"Audit summary falhou: {e}")

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
    hotspots_path = Path.home() / "edge" / "state" / "ops-hotspots.json"
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
        warn(f"Commit {prefix} falhou: {e}")

# ── 6. Commit ~/edge/ ──
try:
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
        warn("Nada para commitar ou git falhou")
except Exception as e:
    log_failure("6", "commit_edge", e, traceback.format_exc())
    fail(f"Git commit falhou: {e}")
PYPHASE5

echo ""
echo "========================================="
if $ALL_OK && [[ "$REPORT_RESULT" != "fail" ]]; then
    echo -e " ${GREEN}PUBLICADO COMPLETO${NC}: $SLUG"
    [[ -n "$REPORT_FILENAME" ]] && echo " Content report: $REPORT_FILENAME"
    [[ -n "$META_REPORT_PATH" ]] && echo " Meta-report: $META_REPORT_PATH"
    [[ -n "$META_REPORT_PATH" ]] && echo ""
    [[ -n "$META_REPORT_PATH" ]] && echo -e " ${YELLOW}→ Ler meta-report ANTES de editar estado${NC}"
    echo "========================================="
    exit 0
elif $ALL_OK; then
    echo -e " ${YELLOW}PARCIAL${NC}: Entry OK, report com issues"
    [[ -n "$META_REPORT_PATH" ]] && echo " Meta-report: $META_REPORT_PATH"
    echo "========================================="
    exit 2
else
    echo -e " ${RED}ISSUES${NC}: verificar manualmente"
    echo "========================================="
    exit 2
fi
