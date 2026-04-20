#!/usr/bin/env bash
# survival-lib.sh — shared functions for health checks
# Part of: Instinto de Sobrevivência (edge_of_chaos)

HEALTH_DIR="${HEALTH_DIR:-$HOME/edge/health}"
CONFIG_FILE="${CONFIG_FILE:-$HEALTH_DIR/config.yaml}"
RAW_DIR="$HEALTH_DIR/raw"

mkdir -p "$RAW_DIR" "$HEALTH_DIR/last_success" "$HEALTH_DIR/quarantine"

log_health() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2
}

emit_component() {
  local name="$1" status="$2" detail="$3"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local json
  json=$(jq -n \
    --arg name "$name" \
    --arg status "$status" \
    --arg detail "$detail" \
    --arg ts "$ts" \
    '{name:$name, status:$status, detail:$detail, ts:$ts}')
  echo "$json" > "$RAW_DIR/${name}.json"
}

compute_score() {
  local total=0 max=0
  local -A weights
  weights=( [heartbeat]=20 [sqlite]=20 [blog]=15 [index]=15 [consolidate]=15 [git]=10 [meta_report]=5 [primitives]=10 )

  for comp in "${!weights[@]}"; do
    local w="${weights[$comp]}"
    local raw_file="$RAW_DIR/${comp}.json"
    if [[ -f "$raw_file" ]]; then
      local st
      st=$(jq -r '.status' "$raw_file" 2>/dev/null)
      case "$st" in
        ok)       max=$((max + w)); total=$((total + w)) ;;
        degraded) max=$((max + w)); total=$((total + w / 2)) ;;
        unknown)  ;;  # exclude from score — no data yet, not a failure
        fail)     max=$((max + w)) ;;
        *)        ;;
      esac
    fi
  done

  if [[ "$max" -gt 0 ]]; then
    echo $(( total * 100 / max ))
  else
    echo 0
  fi
}

safe_timeout() {
  local secs="${1:-10}"
  shift
  timeout "${secs}s" "$@"
}

atomic_write() {
  local target="$1"
  local tmp
  tmp=$(mktemp "${target}.tmp.XXXXXX")
  cat > "$tmp"
  mv "$tmp" "$target"
}

read_yaml_key() {
  local key="$1"
  python3 -c "
import yaml, sys
d = yaml.safe_load(open('$CONFIG_FILE'))
keys = '$key'.split('.')
v = d
for k in keys:
    v = v[k]
print(v)
" 2>/dev/null
}

ts_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

days_since_mtime() {
  local file="$1"
  if [[ ! -e "$file" ]]; then
    echo 9999
    return
  fi
  local mtime now diff
  mtime=$(stat -c %Y "$file" 2>/dev/null || echo 0)
  now=$(date +%s)
  diff=$(( (now - mtime) / 86400 ))
  echo "$diff"
}
