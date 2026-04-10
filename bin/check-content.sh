#!/usr/bin/env bash
# check-content.sh — content staleness health checks
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

ENTRIES_DIR=$(read_yaml_key blog_entries_dir 2>/dev/null || echo "$EDGE_DIR/blog/entries")
THREADS_DIR=$(read_yaml_key threads_dir 2>/dev/null || echo "$EDGE_DIR/threads")

stale_files=()
remediation=()
total_monitored=0
total_stale=0
stable_dates=()

# Parse monitored_files from config
check_files() {
  local files_json
  files_json=$(python3 -c "
import yaml, json, sys, glob, os
d = yaml.safe_load(open('$CONFIG_FILE'))
result = []
for f in d.get('monitored_files', []):
    path = f['path']
    if f.get('glob'):
        matches = glob.glob(os.path.join(path, f['glob']))
        for m in matches:
            result.append({'path': m, 'category': f['category'], 'threshold_days': f.get('threshold_days'), 'remedy_skill': f.get('remedy_skill')})
    else:
        result.append({'path': path, 'category': f['category'], 'threshold_days': f.get('threshold_days'), 'remedy_skill': f.get('remedy_skill')})
print(json.dumps(result))
" 2>/dev/null)

  if [[ -z "$files_json" ]]; then
    log_health "WARN: could not parse monitored_files from config"
    return
  fi

  local count
  count=$(echo "$files_json" | jq 'length')

  for i in $(seq 0 $((count - 1))); do
    local path category threshold remedy days
    path=$(echo "$files_json" | jq -r ".[$i].path")
    category=$(echo "$files_json" | jq -r ".[$i].category")
    threshold=$(echo "$files_json" | jq -r ".[$i].threshold_days")
    remedy=$(echo "$files_json" | jq -r ".[$i].remedy_skill")

    total_monitored=$((total_monitored + 1))
    days=$(days_since_mtime "$path")

    if [[ "$category" == "stable" ]]; then
      stable_dates+=("$days")
      continue
    fi

    if [[ "$threshold" != "null" ]] && [[ "$days" -gt "$threshold" ]]; then
      total_stale=$((total_stale + 1))
      stale_files+=("$(basename "$path"):${days}d")
      if [[ "$remedy" != "null" ]]; then
        remediation+=("{\"file\":\"$(basename "$path")\",\"days_stale\":$days,\"remedy_skill\":\"$remedy\",\"priority\":2}")
      fi
    fi
  done

  # Group alarm for stable files: if all have same staleness (within 2 days), skill stopped
  if [[ ${#stable_dates[@]} -gt 1 ]]; then
    local first="${stable_dates[0]}"
    local all_same=true
    for d in "${stable_dates[@]}"; do
      if [[ $(( first - d )) -gt 2 ]] || [[ $(( d - first )) -gt 2 ]]; then
        all_same=false
        break
      fi
    done
    if $all_same && [[ "$first" -gt 7 ]]; then
      stale_files+=("STABLE_GROUP:${first}d")
      total_stale=$((total_stale + 1))
      remediation+=("{\"file\":\"stable_group\",\"days_stale\":$first,\"remedy_skill\":\"/ed-reflexao\",\"priority\":1}")
    fi
  fi
}

# Check monitored skills usage
overdue_skills=()
check_skills() {
  local skills_json
  skills_json=$(python3 -c "
import yaml, json
d = yaml.safe_load(open('$CONFIG_FILE'))
print(json.dumps(d.get('monitored_skills', [])))
" 2>/dev/null)

  if [[ -z "$skills_json" ]]; then return; fi

  local count
  count=$(echo "$skills_json" | jq 'length')

  for i in $(seq 0 $((count - 1))); do
    local name tag max_gap
    name=$(echo "$skills_json" | jq -r ".[$i].name")
    tag=$(echo "$skills_json" | jq -r ".[$i].tag")
    max_gap=$(echo "$skills_json" | jq -r ".[$i].max_gap_days")

    # Find most recent blog entry with this tag
    local latest_entry days_since=9999
    latest_entry=$(grep -rl "tags:.*$tag" "$ENTRIES_DIR"/2026-*.md 2>/dev/null | xargs -r stat -c '%Y %n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

    if [[ -n "$latest_entry" ]]; then
      days_since=$(days_since_mtime "$latest_entry")
    fi

    if [[ "$days_since" -gt "$max_gap" ]]; then
      overdue_skills+=("${name}:${days_since}d")
      remediation+=("{\"file\":\"skill:$name\",\"days_stale\":$days_since,\"remedy_skill\":\"/ed-$name\",\"priority\":2}")
    fi
  done
}

# Check overdue threads
overdue_threads=0
check_threads() {
  local today
  today=$(date +%Y-%m-%d)

  for f in "$THREADS_DIR"/*.md; do
    [[ -f "$f" ]] || continue
    local resurface
    resurface=$(grep -oP 'resurface:\s*\K\S+' "$f" 2>/dev/null | head -1)
    if [[ -n "$resurface" ]] && [[ "$resurface" < "$today" || "$resurface" == "$today" ]]; then
      local status
      status=$(grep -oP 'status:\s*\K\S+' "$f" 2>/dev/null | head -1)
      if [[ "$status" == "active" || "$status" == "waiting" ]]; then
        overdue_threads=$((overdue_threads + 1))
      fi
    fi
  done
}

# --- run ---
log_health "check-content starting"
check_files
check_skills
check_threads

# Determine status
local_status="ok"
if [[ "$total_stale" -gt 0 ]] || [[ ${#overdue_skills[@]} -gt 0 ]] || [[ "$overdue_threads" -gt 2 ]]; then
  local_status="degraded"
fi
if [[ "$total_stale" -gt 3 ]] || [[ ${#overdue_skills[@]} -gt 2 ]]; then
  local_status="fail"
fi

detail="stale=${total_stale}/${total_monitored}"
[[ ${#stale_files[@]} -gt 0 ]] && detail+=" files=[$(IFS=,; echo "${stale_files[*]}")]"
[[ ${#overdue_skills[@]} -gt 0 ]] && detail+=" skills=[$(IFS=,; echo "${overdue_skills[*]}")]"
[[ "$overdue_threads" -gt 0 ]] && detail+=" threads_overdue=${overdue_threads}"

emit_component content "$local_status" "$detail"

# Write remediation queue
echo "[$(IFS=,; echo "${remediation[*]}")]" | jq '.' > "$RAW_DIR/content-remediation.json" 2>/dev/null || \
  echo "[]" > "$RAW_DIR/content-remediation.json"

log_health "check-content done: $local_status"
