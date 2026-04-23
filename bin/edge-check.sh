#!/usr/bin/env bash
# edge-check.sh — unified health check (3 layers)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

log_health "edge-check starting"

# Run all 3 checks (continue on failure)
"$SCRIPT_DIR/check-infra.sh" 2>&1 || log_health "WARN: check-infra failed"
"$SCRIPT_DIR/check-content.sh" 2>&1 || log_health "WARN: check-content failed"
"$SCRIPT_DIR/check-quality.sh" 2>&1 || log_health "WARN: check-quality failed"

if ! python3 "$SCRIPT_DIR/../tools/rollup-health-v2.py" --write >/dev/null 2>&1; then
  log_health "WARN: rollup-health-v2 failed, falling back to legacy score"
  score=$(compute_score)
  status="healthy"
  if [[ "$score" -lt 85 ]]; then status="degraded"; fi
  if [[ "$score" -lt 70 ]]; then status="unhealthy"; fi
  if [[ "$score" -lt 40 ]]; then status="critical"; fi
  hard_fail=false
  for comp in fs_rw disk sqlite; do
    local_status=$(jq -r '.status' "$RAW_DIR/${comp}.json" 2>/dev/null || echo "unknown")
    if [[ "$local_status" == "critical" ]]; then
      status="critical"
      hard_fail=true
    fi
  done
  ts=$(ts_now)
  infra=$(jq -n '{}')
  for comp in disk fs_rw sqlite blog index consolidate git heartbeat mini_repos primitives; do
    if [[ -f "$RAW_DIR/${comp}.json" ]]; then
      infra=$(echo "$infra" | jq --arg k "$comp" --slurpfile v "$RAW_DIR/${comp}.json" '.[$k] = {status: $v[0].status, detail: $v[0].detail}')
    fi
  done
  content="{}"
  if [[ -f "$RAW_DIR/content.json" ]]; then
    content=$(jq '{status: .status, detail: .detail}' "$RAW_DIR/content.json")
  fi
  quality="{}"
  if [[ -f "$RAW_DIR/quality.json" ]]; then
    quality=$(jq '{status: .status, detail: .detail}' "$RAW_DIR/quality.json")
  fi
  remediation="[]"
  for rfile in "$RAW_DIR"/content-remediation.json "$RAW_DIR"/quality-remediation.json; do
    if [[ -f "$rfile" ]]; then
      remediation=$(echo "$remediation" | jq --slurpfile r "$rfile" '. + $r[0]')
    fi
  done
  remediation=$(echo "$remediation" | jq 'sort_by(.priority)')
  jq -n \
    --arg ts "$ts" \
    --arg status "$status" \
    --argjson score "$score" \
    --argjson hard_fail "$hard_fail" \
    --argjson infra "$infra" \
    --argjson content "$content" \
    --argjson quality "$quality" \
    --argjson remediation "$remediation" \
    '{schema_version:1, ts:$ts, status:$status, score:$score, hard_fail:$hard_fail, infra:$infra, content:$content, quality:$quality, remediation_queue:$remediation}' \
    | atomic_write "$HEALTH_DIR/current.json"
fi

score=$(jq -r '.score // 0' "$HEALTH_DIR/current.json" 2>/dev/null || echo 0)
status=$(jq -r '.status // "unknown"' "$HEALTH_DIR/current.json" 2>/dev/null || echo unknown)
hard_fail=$(jq -r '.hard_fail // false' "$HEALTH_DIR/current.json" 2>/dev/null || echo false)
ts=$(jq -r '.ts // empty' "$HEALTH_DIR/current.json" 2>/dev/null || true)
if [[ -z "${ts:-}" ]]; then
  ts=$(ts_now)
fi

# Append to history
jq -c '.' "$HEALTH_DIR/current.json" >> "$HEALTH_DIR/history.jsonl"

# Write simple status
echo "$ts $status $score" > "$HEALTH_DIR/last_status.txt"

# Log to journal
logger -t edge-health "status=$status score=$score hard_fail=$hard_fail" 2>/dev/null || true

log_health "edge-check done: status=$status score=$score"
