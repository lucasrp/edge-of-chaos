#!/usr/bin/env bash
# check-quality.sh — quality gates compliance checks
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

ENTRIES_DIR=$(read_yaml_key blog_entries_dir 2>/dev/null || echo "$HOME/edge/blog/entries")
META_DIR=$(read_yaml_key meta_reports_dir 2>/dev/null || echo "$HOME/edge/meta-reports")
SECRETS_DIR=$(read_yaml_key secrets_dir 2>/dev/null || echo "$HOME/edge/secrets")

# --- Adversarial rate (last 7 days) ---
adversarial_rate=0
total_meta_7d=0
meta_with_adversarial=0

check_adversarial() {
  local cutoff
  cutoff=$(date -d '7 days ago' +%s 2>/dev/null || date -v-7d +%s 2>/dev/null || echo 0)

  while IFS= read -r f; do
    local mtime
    mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    [[ "$mtime" -lt "$cutoff" ]] && continue
    total_meta_7d=$((total_meta_7d + 1))
    if grep -q 'edge-consult' "$f" 2>/dev/null; then
      meta_with_adversarial=$((meta_with_adversarial + 1))
    fi
  done < <(find "$META_DIR" -name '*meta*' -type f 2>/dev/null)

  if [[ "$total_meta_7d" -gt 0 ]]; then
    adversarial_rate=$(( meta_with_adversarial * 100 / total_meta_7d ))
  fi
}

# --- Fontes rate (Q2/Q3 entries, last 7 days) ---
fontes_rate=0
total_q2q3_7d=0
q2q3_with_fontes=0

check_fontes() {
  local cutoff
  cutoff=$(date -d '7 days ago' +%s 2>/dev/null || echo 0)

  while IFS= read -r f; do
    local mtime
    mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    [[ "$mtime" -lt "$cutoff" ]] && continue

    # Check if Q2/Q3 by tags
    if grep -qE 'tags:.*\b(pesquisa|descoberta|estrategia|relatorio|proposta|pitch)\b' "$f" 2>/dev/null; then
      total_q2q3_7d=$((total_q2q3_7d + 1))
      if grep -q 'edge-fontes' "$f" 2>/dev/null; then
        q2q3_with_fontes=$((q2q3_with_fontes + 1))
      fi
    fi
  done < <(find "$ENTRIES_DIR" -name '2026-*.md' -type f 2>/dev/null)

  if [[ "$total_q2q3_7d" -gt 0 ]]; then
    fontes_rate=$(( q2q3_with_fontes * 100 / total_q2q3_7d ))
  fi
}

# --- Review gate active ---
review_gate_active=false

check_review_gate() {
  local cutoff
  cutoff=$(date -d '7 days ago' +%s 2>/dev/null || echo 0)

  while IFS= read -r f; do
    local mtime
    mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    [[ "$mtime" -lt "$cutoff" ]] && continue
    if grep -qE 'overall|review.*score|Review Gate' "$f" 2>/dev/null; then
      review_gate_active=true
      return
    fi
  done < <(find "$META_DIR" -name '*meta*' -type f 2>/dev/null)
}

# --- Provider health ---
exa_status="unknown"
openai_status="unknown"

check_providers() {
  # Exa
  if [[ -f "$SECRETS_DIR/exa.env" ]]; then
    local exa_key
    exa_key=$(grep -oP 'EXA_API_KEY=\K.*' "$SECRETS_DIR/exa.env" 2>/dev/null)
    if [[ -n "$exa_key" ]]; then
      local code
      code=$(safe_timeout 5 curl -sS -o /dev/null -w '%{http_code}' \
        -H "x-api-key: $exa_key" \
        -H "Content-Type: application/json" \
        -d '{"query":"test","num_results":1}' \
        "https://api.exa.ai/search" 2>/dev/null || echo 000)
      if [[ "$code" == "200" ]]; then
        exa_status="ok"
      else
        exa_status="degraded"
      fi
    fi
  fi

  # OpenAI
  if [[ -f "$SECRETS_DIR/openai.env" ]]; then
    local oai_key
    oai_key=$(grep -oP 'OPENAI_API_KEY=\K.*' "$SECRETS_DIR/openai.env" 2>/dev/null)
    if [[ -n "$oai_key" ]]; then
      local code
      code=$(safe_timeout 5 curl -sS -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $oai_key" \
        "https://api.openai.com/v1/models" 2>/dev/null || echo 000)
      if [[ "$code" == "200" ]]; then
        openai_status="ok"
      else
        openai_status="degraded"
      fi
    fi
  fi
}

# --- Backfill queue ---
generate_backfill() {
  # Q2/Q3 entries without adversarial review in last 7 days
  local cutoff backfill_items=()
  cutoff=$(date -d '7 days ago' +%s 2>/dev/null || echo 0)

  while IFS= read -r f; do
    local mtime
    mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    [[ "$mtime" -lt "$cutoff" ]] && continue
    if grep -qE 'tags:.*\b(pesquisa|descoberta|relatorio|proposta|pitch)\b' "$f" 2>/dev/null; then
      if ! grep -q 'edge-consult\|adversarial' "$f" 2>/dev/null; then
        backfill_items+=("$(basename "$f")")
      fi
    fi
  done < <(find "$ENTRIES_DIR" -name '2026-*.md' -type f 2>/dev/null)

  # Write backfill queue (max 5)
  local arr="[]"
  for item in "${backfill_items[@]:0:5}"; do
    arr=$(echo "$arr" | jq --arg f "$item" '. + [{"file":$f,"action":"edge-consult backfill","priority":3}]')
  done
  echo "$arr" > "$RAW_DIR/quality-remediation.json"
}

# --- run ---
log_health "check-quality starting"
check_adversarial
check_fontes
check_review_gate
check_providers
generate_backfill

# Determine status
local_status="ok"
if [[ "$adversarial_rate" -lt 50 ]] || [[ "$fontes_rate" -lt 30 ]]; then
  local_status="degraded"
fi
if [[ "$adversarial_rate" -lt 15 ]] || [[ "$fontes_rate" -lt 10 ]] || [[ "$review_gate_active" == "false" ]]; then
  local_status="fail"
fi

detail="adversarial=${adversarial_rate}% (${meta_with_adversarial}/${total_meta_7d})"
detail+=" fontes=${fontes_rate}% (${q2q3_with_fontes}/${total_q2q3_7d})"
detail+=" review_gate=${review_gate_active}"
detail+=" exa=${exa_status} openai=${openai_status}"

emit_component quality "$local_status" "$detail"

log_health "check-quality done: $local_status"
