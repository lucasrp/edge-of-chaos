#!/usr/bin/env bash
# edge-supervisor.sh — heartbeat wrapper with health gating
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config/paths.sh
source "$SCRIPT_DIR/../config/paths.sh"
source "$SCRIPT_DIR/survival-lib.sh"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

LOCK_FILE="$HEALTH_DIR/supervisor.lock"
START_TIME=$(date +%s)

# Exclusive lock
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log_health "supervisor: another instance running, exiting"
  exit 0
fi

log_health "supervisor: starting (dry_run=$DRY_RUN)"

# Step 1: Health check
"$SCRIPT_DIR/edge-check.sh" 2>&1

score_before=$(jq -r '.score' "$HEALTH_DIR/current.json" 2>/dev/null || echo 0)
status=$(jq -r '.status' "$HEALTH_DIR/current.json" 2>/dev/null || echo unknown)

# Step 2: Repair if needed
repair_attempted=false
if [[ "$status" != "healthy" ]]; then
  repair_attempted=true
  log_health "supervisor: status=$status score=$score_before, attempting repair"
  "$SCRIPT_DIR/edge-repair.sh" 2>&1 || true
  "$SCRIPT_DIR/edge-check.sh" 2>&1
  status=$(jq -r '.status' "$HEALTH_DIR/current.json" 2>/dev/null || echo unknown)
fi

score_after=$(jq -r '.score' "$HEALTH_DIR/current.json" 2>/dev/null || echo 0)

# Step 3: Determine mode
mode="normal"
if [[ "$score_after" -lt 70 ]]; then mode="degraded"; fi
if [[ "$score_after" -lt 40 ]]; then mode="maintenance"; fi

echo "$mode" > "$HEALTH_DIR/mode"
log_health "supervisor: mode=$mode score=$score_after"

HEARTBEAT_SKILL="/${SKILL_PREFIX}-heartbeat"
RUNNER="$EDGE_REPO_DIR/tools/edge-runner"
RUNNER_CWD="${WORK_DIR:-$EDGE_REPO_DIR}"

# Step 4: Execute according to mode
if $DRY_RUN; then
  log_health "supervisor: DRY RUN — skipping claude invocation"
else
  case "$mode" in
    normal)
      log_health "supervisor: running normal heartbeat"
      cd "$RUNNER_CWD"
      "$RUNNER" skill \
        --skill "$HEARTBEAT_SKILL" \
        --dispatch-trigger heartbeat \
        --dispatch-policy autonomous \
        --dispatch-routing-mode auto \
        --dispatch-preflight-profile heartbeat_default \
        --dispatch-postflight-profile standard \
        --dispatch-force \
        --max-turns 30 \
        --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*),WebSearch(*),WebFetch(*),Task(*),Skill(*)" \
        2>&1 || true

      # Run 1 remediation action from queue
      local_action=$(jq -r '.[0].remedy_skill // empty' "$HEALTH_DIR/raw/content-remediation.json" 2>/dev/null)
      if [[ -n "$local_action" ]]; then
        log_health "supervisor: running remediation: $local_action"
        cd "$RUNNER_CWD"
        "$RUNNER" skill --skill "$local_action" --max-turns 15 \
          --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*),WebSearch(*),WebFetch(*),Task(*),Skill(*)" \
          2>&1 || true
      fi
      ;;

    degraded)
      log_health "supervisor: running degraded heartbeat (limited)"
      cd "$RUNNER_CWD"
      "$RUNNER" skill \
        --skill "$HEARTBEAT_SKILL" \
        --dispatch-trigger heartbeat \
        --dispatch-policy autonomous \
        --dispatch-routing-mode auto \
        --dispatch-preflight-profile heartbeat_default \
        --dispatch-postflight-profile standard \
        --dispatch-force \
        --max-turns 15 \
        --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*),WebSearch(*),WebFetch(*),Task(*),Skill(*)" \
        2>&1 || true

      local_action=$(jq -r '.[0].remedy_skill // empty' "$HEALTH_DIR/raw/content-remediation.json" 2>/dev/null)
      if [[ -n "$local_action" ]]; then
        log_health "supervisor: running remediation: $local_action"
        cd "$RUNNER_CWD"
        "$RUNNER" skill --skill "$local_action" --max-turns 10 \
          --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*),WebSearch(*),WebFetch(*),Task(*),Skill(*)" \
          2>&1 || true
      fi
      ;;

    maintenance)
      log_health "supervisor: MAINTENANCE MODE — diagnostics only"
      touch "$HEALTH_DIR/operator-alert.flag"
      cd "$RUNNER_CWD"
      "$RUNNER" prompt --prompt "Leia $HEALTH_CURRENT_FILE e $EDGE_REPO_DIR/SURVIVAL_POLICY.md. Status: $status, score: $score_after. Diagnostique os problemas e tente reparar o que puder. NÃO execute missão normal." \
        --max-turns 10 \
        --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*)" \
        2>&1 || true
      ;;
  esac
fi

# Step 5: Write heartbeat.json
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

jq -n \
  --arg ts "$(ts_now)" \
  --arg hostname "$(hostname)" \
  --argjson score_before "$score_before" \
  --argjson repair_attempted "$repair_attempted" \
  --argjson score_after "$score_after" \
  --arg mode "$mode" \
  --argjson duration "$DURATION" \
  --arg status "$status" \
  '{ts:$ts, hostname:$hostname, score_before:$score_before, repair_attempted:$repair_attempted, score_after:$score_after, mode:$mode, duration_secs:$duration, status:$status}' \
  | atomic_write "$HEALTH_DIR/heartbeat.json"

log_health "supervisor: done (duration=${DURATION}s)"
