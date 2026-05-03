#!/usr/bin/env bash
# check-content.sh — content staleness health checks
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

ENTRIES_DIR="${ENTRIES_DIR:-$(read_yaml_key blog_entries_dir 2>/dev/null || echo "$HOME/edge/blog/entries")}"
THREADS_DIR="${THREADS_DIR:-$(read_yaml_key threads_dir 2>/dev/null || echo "$HOME/edge/threads")}"

stale_files=()
remediation=()
total_monitored=0
total_stale=0
stable_dates=()
content_scan_truncated=false
content_scan_matched_total=0
content_scan_limit="${EDGE_CONTENT_MAX_FILES:-300}"

# Parse monitored_files from config
check_files() {
  local files_json
  files_json=$(CONFIG_FILE="$CONFIG_FILE" EDGE_CONTENT_MAX_FILES="$content_scan_limit" python3 - <<'PY' 2>/dev/null
import glob
import json
import os
import time
from pathlib import Path

import yaml

config_file = os.environ["CONFIG_FILE"]
max_files = int(os.environ.get("EDGE_CONTENT_MAX_FILES") or "300")
data = yaml.safe_load(open(config_file, encoding="utf-8")) or {}
expanded = []
for item in data.get("monitored_files", []) or []:
    base = str(item.get("path") or "")
    if item.get("glob"):
        for match in glob.glob(os.path.join(base, str(item.get("glob") or ""))):
            expanded.append({
                "path": match,
                "category": item.get("category"),
                "threshold_days": item.get("threshold_days"),
                "remedy_skill": item.get("remedy_skill"),
            })
    else:
        expanded.append({
            "path": base,
            "category": item.get("category"),
            "threshold_days": item.get("threshold_days"),
            "remedy_skill": item.get("remedy_skill"),
        })

def mtime(path):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0

matched_total = len(expanded)
expanded.sort(key=lambda row: mtime(row["path"]), reverse=True)
truncated = matched_total > max_files
if truncated:
    expanded = expanded[:max_files]

now = time.time()
stale_files = []
stable_dates = []
remediation = []
for row in expanded:
    path = row["path"]
    try:
        days = int((now - Path(path).stat().st_mtime) // 86400)
    except OSError:
        days = 9999
    category = row.get("category")
    threshold = row.get("threshold_days")
    remedy = row.get("remedy_skill")
    if category == "stable":
        stable_dates.append(days)
        continue
    if threshold is not None and days > int(threshold):
        name = Path(path).name or str(path)
        stale_files.append(f"{name}:{days}d")
        if remedy:
            remediation.append({"file": name, "days_stale": days, "remedy_skill": remedy, "priority": 2})

if len(stable_dates) > 1:
    first = stable_dates[0]
    all_same = all(abs(first - day) <= 2 for day in stable_dates)
    if all_same and first > 7:
        stale_files.append(f"STABLE_GROUP:{first}d")
        remediation.append({"file": "stable_group", "days_stale": first, "remedy_skill": "/ed-planner", "priority": 1})

print(json.dumps({
    "total_monitored": len(expanded),
    "matched_total": matched_total,
    "truncated": truncated,
    "stale_files": stale_files,
    "total_stale": len(stale_files),
    "remediation": remediation,
}))
PY
)

  if [[ -z "$files_json" ]]; then
    log_health "WARN: could not parse monitored_files from config"
    return
  fi

  total_monitored=$(echo "$files_json" | jq -r '.total_monitored // 0')
  total_stale=$(echo "$files_json" | jq -r '.total_stale // 0')
  content_scan_truncated=$(echo "$files_json" | jq -r '.truncated // false')
  content_scan_matched_total=$(echo "$files_json" | jq -r '.matched_total // 0')
  mapfile -t stale_files < <(echo "$files_json" | jq -r '.stale_files[]?')
  mapfile -t remediation < <(echo "$files_json" | jq -c '.remediation[]?')
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
if [[ "$total_stale" -gt 0 ]] || [[ ${#overdue_skills[@]} -gt 0 ]] || [[ "$overdue_threads" -gt 2 ]] || [[ "$content_scan_truncated" == "true" ]]; then
  local_status="degraded"
fi
if [[ "$total_stale" -gt 3 ]] || [[ ${#overdue_skills[@]} -gt 2 ]]; then
  local_status="fail"
fi

detail="stale=${total_stale}/${total_monitored}"
if [[ "$content_scan_truncated" == "true" ]]; then
  detail+=" scan_truncated=${total_monitored}/${content_scan_matched_total} limit=${content_scan_limit}"
fi
[[ ${#stale_files[@]} -gt 0 ]] && detail+=" files=[$(IFS=,; echo "${stale_files[*]}")]"
[[ ${#overdue_skills[@]} -gt 0 ]] && detail+=" skills=[$(IFS=,; echo "${overdue_skills[*]}")]"
[[ "$overdue_threads" -gt 0 ]] && detail+=" threads_overdue=${overdue_threads}"

emit_component content "$local_status" "$detail"

# Write remediation queue
echo "[$(IFS=,; echo "${remediation[*]}")]" | jq '.' > "$RAW_DIR/content-remediation.json" 2>/dev/null || \
  echo "[]" > "$RAW_DIR/content-remediation.json"

log_health "check-content done: $local_status"
