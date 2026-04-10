#!/usr/bin/env bash
# edge-repair.sh — idempotent auto-repair
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

REPAIR_STATE="$HEALTH_DIR/repair-state.json"
REPAIR_LOG="$HEALTH_DIR/repair.log"
BLOG_SERVICE=$(read_yaml_key blog_service 2>/dev/null || echo blog-server.service)
BLOG_PORT=$(read_yaml_key blog_port 2>/dev/null || echo 8766)
SQLITE_DB=$(read_yaml_key sqlite_db 2>/dev/null || echo "$HOME/edge/edge-memory.db")

# Initialize repair state if missing
if [[ ! -f "$REPAIR_STATE" ]]; then
  echo '{"repairs":{}}' > "$REPAIR_STATE"
fi

repair_log() {
  echo "[$(ts_now)] $*" >> "$REPAIR_LOG"
  log_health "REPAIR: $*"
}

get_repair_count() {
  local comp="$1"
  jq -r ".repairs[\"$comp\"].attempts // 0" "$REPAIR_STATE" 2>/dev/null
}

get_cooldown_until() {
  local comp="$1"
  jq -r ".repairs[\"$comp\"].cooldown_until // \"\"" "$REPAIR_STATE" 2>/dev/null
}

update_repair_state() {
  local comp="$1" success="$2"
  local attempts cooldown_until=""
  attempts=$(get_repair_count "$comp")

  if [[ "$success" == "true" ]]; then
    attempts=0
  else
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge 3 ]]; then
      local hours=$((2 ** (attempts - 2)))
      [[ "$hours" -gt 24 ]] && hours=24
      cooldown_until=$(date -u -d "+${hours} hours" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)
    fi
  fi

  local tmp
  tmp=$(jq --arg c "$comp" --argjson a "$attempts" --arg cu "$cooldown_until" --arg ts "$(ts_now)" \
    '.repairs[$c] = {attempts:$a, cooldown_until:$cu, last_attempt:$ts}' "$REPAIR_STATE")
  echo "$tmp" | atomic_write "$REPAIR_STATE"
}

in_cooldown() {
  local comp="$1"
  local until
  until=$(get_cooldown_until "$comp")
  [[ -z "$until" || "$until" == "null" || "$until" == "" ]] && return 1
  local now_epoch until_epoch
  now_epoch=$(date +%s)
  until_epoch=$(date -d "$until" +%s 2>/dev/null || echo 0)
  [[ "$now_epoch" -lt "$until_epoch" ]]
}

# Read current health
if [[ ! -f "$HEALTH_DIR/current.json" ]]; then
  repair_log "No current.json — run edge-check.sh first"
  exit 1
fi

repair_log "=== repair cycle starting ==="

# --- Blog ---
blog_status=$(jq -r '.infra.blog.status // "unknown"' "$HEALTH_DIR/current.json")
if [[ "$blog_status" == "fail" || "$blog_status" == "degraded" ]]; then
  repair_log "Blog: attempting restart"
  if systemctl --user restart "$BLOG_SERVICE" 2>/dev/null; then
    sleep 3
    code=$(safe_timeout 5 curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BLOG_PORT}/api/entries" 2>/dev/null || echo 000)
    if [[ "$code" == "200" ]]; then
      repair_log "Blog: restart SUCCESS (http=$code)"
      update_repair_state blog true
    else
      repair_log "Blog: restart but still failing (http=$code)"
      update_repair_state blog false
    fi
  else
    repair_log "Blog: systemctl restart failed"
    update_repair_state blog false
  fi
fi

# --- SQLite ---
sqlite_status=$(jq -r '.infra.sqlite.status // "unknown"' "$HEALTH_DIR/current.json")
if [[ "$sqlite_status" == "critical" || "$sqlite_status" == "fail" ]]; then
  if in_cooldown sqlite; then
    repair_log "SQLite: in cooldown, skipping"
  else
    local_size=$(stat -c%s "$SQLITE_DB" 2>/dev/null || echo 0)
    if [[ "$local_size" -eq 0 ]]; then
      repair_log "SQLite: db is 0 bytes, quarantining and recreating"
      mv "$SQLITE_DB" "$HEALTH_DIR/quarantine/edge-memory.db.$(date +%s)" 2>/dev/null || true
      if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$SQLITE_DB" "CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, path TEXT UNIQUE, content TEXT, ts TEXT);" 2>/dev/null
        repair_log "SQLite: recreated with minimal schema"
        update_repair_state sqlite true
      else
        repair_log "SQLite: sqlite3 not available, cannot recreate"
        update_repair_state sqlite false
      fi
    else
      repair_log "SQLite: not 0 bytes (size=$local_size), skipping destructive repair"
      update_repair_state sqlite false
    fi
  fi
fi

# --- Index ---
index_status=$(jq -r '.infra.index.status // "unknown"' "$HEALTH_DIR/current.json")
if [[ "$index_status" == "fail" || "$index_status" == "degraded" || "$index_status" == "unknown" ]]; then
  if in_cooldown index; then
    repair_log "Index: in cooldown, skipping"
  else
    repair_log "Index: attempting reindex"
    if safe_timeout 60 edge-index "$HOME/edge/blog/entries/" "$HOME/edge/reports/" "$HOME/edge/notes/" 2>/dev/null; then
      repair_log "Index: reindex SUCCESS"
      update_repair_state index true
      jq -n --arg ts "$(ts_now)" '{ts:$ts, source:"repair"}' > "$HEALTH_DIR/last_success/index.ok"
    else
      repair_log "Index: reindex FAILED"
      update_repair_state index false
    fi
  fi
fi

# --- Git ---
git_status=$(jq -r '.infra.git.status // "unknown"' "$HEALTH_DIR/current.json")
if [[ "$git_status" == "fail" ]]; then
  repair_log "Git: repo invalid — REQUIRES HUMAN INTERVENTION"
elif [[ "$git_status" == "degraded" ]]; then
  repair_log "Git: uncommitted changes — noting only (no auto-commit)"
fi

# --- Mini-repos (skills, memory) ---
mini_status=$(jq -r '.infra.mini_repos.status // "unknown"' "$HEALTH_DIR/current.json")
if [[ "$mini_status" == "degraded" || "$mini_status" == "fail" ]]; then
  if in_cooldown mini_repos; then
    repair_log "Mini-repos: in cooldown, skipping"
  else
    repair_log "Mini-repos: auto-committing dirty .claude state"
    claude_dir="$HOME/.claude"

    if [[ -d "$claude_dir/.git" ]]; then
      dirty=$(cd "$claude_dir" && git status --porcelain 2>/dev/null | wc -l)
      if [[ "$dirty" -gt 0 ]]; then
        if cd "$claude_dir" && git add -A 2>/dev/null && git commit -m "chore: auto-commit ${dirty} pending changes (edge-repair)" 2>/dev/null; then
          repair_log "Mini-repos: committed .claude ($dirty files)"
          update_repair_state mini_repos true
        else
          repair_log "Mini-repos: failed to commit .claude"
          update_repair_state mini_repos false
        fi
      fi
    else
      repair_log "Mini-repos: no .git in .claude, skipping"
      update_repair_state mini_repos false
    fi
  fi
fi

repair_log "=== repair cycle done ==="
