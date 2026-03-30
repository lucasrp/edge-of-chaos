#!/usr/bin/env bash
# check-content.sh — content staleness health checks
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

ENTRIES_DIR=$(read_yaml_key blog_entries_dir 2>/dev/null || echo "$HOME/edge/blog/entries")
THREADS_DIR=$(read_yaml_key threads_dir 2>/dev/null || echo "$HOME/edge/threads")

stale_files=()
remediation=()
total_monitored=0
total_stale=0
missing_paths=()

# Parse monitored_files from config and process in a single Python pass.
# This replaces the previous O(n) bash+jq loop that hung on large directories
# (1000+ blog entries = ~4000 jq calls = minutes of CPU).
check_files() {
  local result
  result=$(python3 -c "
import yaml, json, sys, glob, os, time

config_file = '$CONFIG_FILE'
if not os.path.exists(config_file):
    print(json.dumps({'error': 'config not found', 'path': config_file}))
    sys.exit(0)

d = yaml.safe_load(open(config_file))
monitored = d.get('monitored_files', [])
now = time.time()
day_secs = 86400

results = {
    'total': 0,
    'stale': 0,
    'stale_files': [],
    'missing_paths': [],
    'remediation': [],
    'stable_days': []
}

for entry in monitored:
    path = entry['path']
    category = entry.get('category', 'unknown')
    threshold = entry.get('threshold_days')
    remedy = entry.get('remedy_skill')
    file_glob = entry.get('glob')

    # Validate path exists — absence is NOT health
    if not os.path.exists(path):
        results['missing_paths'].append(path)
        continue

    if file_glob:
        files = glob.glob(os.path.join(path, file_glob))
    else:
        files = [path]

    for f in files:
        results['total'] += 1
        if not os.path.exists(f):
            continue
        mtime = os.stat(f).st_mtime
        days = int((now - mtime) / day_secs)

        if category == 'stable':
            results['stable_days'].append(days)
            continue

        if threshold is not None and days > threshold:
            results['stale'] += 1
            results['stale_files'].append(f'{os.path.basename(f)}:{days}d')
            if remedy:
                results['remediation'].append({
                    'file': os.path.basename(f),
                    'days_stale': days,
                    'remedy_skill': remedy,
                    'priority': 2
                })

# Stable group alarm: if all stable files same staleness (within 2d) and >7d
stable = results['stable_days']
if len(stable) > 1:
    first = stable[0]
    all_same = all(abs(d - first) <= 2 for d in stable)
    if all_same and first > 7:
        results['stale'] += 1
        results['stale_files'].append(f'STABLE_GROUP:{first}d')
        results['remediation'].append({
            'file': 'stable_group',
            'days_stale': first,
            'remedy_skill': '/ed-reflexao',
            'priority': 1
        })

print(json.dumps(results))
" 2>/dev/null)

  if [[ -z "$result" ]]; then
    log_health "WARN: could not parse monitored_files from config"
    return
  fi

  # Check for config read error
  local err
  err=$(echo "$result" | jq -r '.error // empty')
  if [[ -n "$err" ]]; then
    log_health "WARN: config error: $err"
    return
  fi

  total_monitored=$(echo "$result" | jq -r '.total')
  total_stale=$(echo "$result" | jq -r '.stale')

  # Extract stale files
  while IFS= read -r f; do
    [[ -n "$f" ]] && stale_files+=("$f")
  done < <(echo "$result" | jq -r '.stale_files[]' 2>/dev/null)

  # Extract missing paths — these are NOT healthy, they're invisible failures
  while IFS= read -r p; do
    [[ -n "$p" ]] && missing_paths+=("$p")
  done < <(echo "$result" | jq -r '.missing_paths[]' 2>/dev/null)

  # Write remediation from Python output
  echo "$result" | jq '.remediation' > "$RAW_DIR/content-remediation.json" 2>/dev/null || \
    echo "[]" > "$RAW_DIR/content-remediation.json"
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

# Missing monitored paths is always a failure — absence is NOT health
if [[ ${#missing_paths[@]} -gt 0 ]]; then
  local_status="fail"
fi

if [[ "$total_stale" -gt 0 ]] || [[ ${#overdue_skills[@]} -gt 0 ]] || [[ "$overdue_threads" -gt 2 ]]; then
  local_status="degraded"
fi
if [[ "$total_stale" -gt 3 ]] || [[ ${#overdue_skills[@]} -gt 2 ]]; then
  local_status="fail"
fi

detail="stale=${total_stale}/${total_monitored}"
[[ ${#missing_paths[@]} -gt 0 ]] && detail+=" MISSING_PATHS=[$(IFS=,; echo "${missing_paths[*]}")]"
[[ ${#stale_files[@]} -gt 0 ]] && detail+=" files=[$(IFS=,; echo "${stale_files[*]}")]"
[[ ${#overdue_skills[@]} -gt 0 ]] && detail+=" skills=[$(IFS=,; echo "${overdue_skills[*]}")]"
[[ "$overdue_threads" -gt 0 ]] && detail+=" threads_overdue=${overdue_threads}"

emit_component content "$local_status" "$detail"

log_health "check-content done: $local_status"
