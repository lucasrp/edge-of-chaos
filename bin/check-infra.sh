#!/usr/bin/env bash
# check-infra.sh — infrastructure health checks
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/survival-lib.sh"

BLOG_PORT=$(read_yaml_key blog_port 2>/dev/null || echo 8766)
BLOG_SERVICE=$(read_yaml_key blog_service 2>/dev/null || echo blog-server.service)
SQLITE_DB="${SQLITE_DB:-$(read_yaml_key sqlite_db 2>/dev/null || echo "${SEARCH_DB_FILE:-$HOME/edge/edge-memory.db}")}"
REPO_ROOT="${REPO_ROOT:-$(read_yaml_key repo_root 2>/dev/null || echo "${EDGE_REPO_DIR:-$HOME/edge}")}"

# --- disk ---
check_disk() {
  local pct_free inode_free
  pct_free=$(df -P "$HOME" | awk 'NR==2 {print 100-$5}')
  inode_free=$(df -Pi "$HOME" | awk 'NR==2 {gsub(/%/,"",$5); print 100-$5}')

  if [[ "$pct_free" -lt 2 ]] || [[ "$inode_free" -lt 2 ]]; then
    emit_component disk critical "free=${pct_free}% inode_free=${inode_free}%"
  elif [[ "$pct_free" -lt 5 ]] || [[ "$inode_free" -lt 5 ]]; then
    emit_component disk degraded "free=${pct_free}% inode_free=${inode_free}%"
  else
    emit_component disk ok "free=${pct_free}% inode_free=${inode_free}%"
  fi
}

# --- fs_rw ---
check_fs_rw() {
  local tmp
  tmp="$HEALTH_DIR/.rwtest.$$"
  if echo "test" > "$tmp" 2>/dev/null && cat "$tmp" >/dev/null 2>&1 && rm -f "$tmp"; then
    emit_component fs_rw ok "write/read/remove ok"
  else
    rm -f "$tmp" 2>/dev/null
    emit_component fs_rw critical "filesystem write test failed"
  fi
}

# --- sqlite ---
check_sqlite() {
  if ! command -v sqlite3 >/dev/null 2>&1; then
    emit_component sqlite unknown "sqlite3 not installed"
    return
  fi

  if [[ ! -f "$SQLITE_DB" ]]; then
    emit_component sqlite critical "db file missing"
    return
  fi

  local size
  size=$(stat -Lc%s "$SQLITE_DB" 2>/dev/null || echo 0)
  if [[ "$size" -eq 0 ]]; then
    emit_component sqlite critical "db size=0 bytes"
    return
  fi

  if [[ "$size" -lt 4096 ]]; then
    emit_component sqlite degraded "db size=${size} bytes (suspiciously small)"
    return
  fi

  local qc
  qc=$(safe_timeout 5 sqlite3 "$SQLITE_DB" "PRAGMA quick_check;" 2>&1)
  if [[ "$qc" != "ok" ]]; then
    emit_component sqlite critical "quick_check failed: $qc"
    return
  fi

  if safe_timeout 5 sqlite3 "$SQLITE_DB" "CREATE TABLE IF NOT EXISTS _survival_probe(ts TEXT); INSERT INTO _survival_probe VALUES(datetime('now')); DELETE FROM _survival_probe;" 2>/dev/null; then
    emit_component sqlite ok "size=${size} quick_check=ok rw=ok"
  else
    emit_component sqlite degraded "quick_check ok but rw probe failed"
  fi
}

# --- blog ---
check_blog() {
  local svc_active=false http_ok=false detail=""

  if systemctl --user is-active --quiet "$BLOG_SERVICE" 2>/dev/null; then
    svc_active=true
  fi

  local code
  code=$(safe_timeout 5 curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BLOG_PORT}/api/entries" 2>/dev/null || echo 000)
  if [[ "$code" == "200" ]]; then
    http_ok=true
  fi

  if $svc_active && $http_ok; then
    emit_component blog ok "service=active http=$code"
  elif $svc_active && ! $http_ok; then
    emit_component blog degraded "service=active but http=$code"
  else
    emit_component blog fail "service=inactive http=$code"
  fi
}

# --- edge-index ---
check_index() {
  local marker="$HEALTH_DIR/last_success/index.ok"
  if [[ ! -f "$marker" ]]; then
    emit_component index unknown "no index.ok marker yet"
    return
  fi
  local days
  days=$(days_since_mtime "$marker")
  if [[ "$days" -le 2 ]]; then
    emit_component index ok "last indexed ${days}d ago"
  elif [[ "$days" -le 7 ]]; then
    emit_component index degraded "last indexed ${days}d ago"
  else
    emit_component index fail "last indexed ${days}d ago"
  fi
}

# --- consolidate-state ---
check_consolidate() {
  local latest
  latest=$(find "$META_DIR" -name '*meta*' -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
  if [[ -z "$latest" ]]; then
    emit_component consolidate unknown "no meta-reports found"
    return
  fi
  local days
  days=$(days_since_mtime "$latest")
  if [[ "$days" -le 2 ]]; then
    emit_component consolidate ok "last meta-report ${days}d ago"
  elif [[ "$days" -le 5 ]]; then
    emit_component consolidate degraded "last meta-report ${days}d ago"
  else
    emit_component consolidate fail "last meta-report ${days}d ago"
  fi
}

# --- git ---
check_git() {
  if ! (cd "$REPO_ROOT" && git rev-parse HEAD >/dev/null 2>&1); then
    emit_component git fail "not a valid git repo"
    return
  fi

  local uncommitted
  uncommitted=$(cd "$REPO_ROOT" && git status --porcelain 2>/dev/null | wc -l)
  if [[ "$uncommitted" -eq 0 ]]; then
    emit_component git ok "clean working tree"
  elif [[ "$uncommitted" -lt 20 ]]; then
    emit_component git degraded "${uncommitted} uncommitted changes"
  else
    emit_component git degraded "${uncommitted} uncommitted changes (many)"
  fi
}

# --- heartbeat ---
check_heartbeat() {
  local hb="$HEALTH_DIR/heartbeat.json"
  if [[ ! -f "$hb" ]]; then
    emit_component heartbeat unknown "no heartbeat.json yet (first run?)"
    return
  fi
  local hours_since
  local mtime now
  mtime=$(stat -c %Y "$hb" 2>/dev/null || echo 0)
  now=$(date +%s)
  hours_since=$(( (now - mtime) / 3600 ))

  if [[ "$hours_since" -le 3 ]]; then
    emit_component heartbeat ok "last heartbeat ${hours_since}h ago"
  elif [[ "$hours_since" -le 6 ]]; then
    emit_component heartbeat degraded "last heartbeat ${hours_since}h ago"
  else
    emit_component heartbeat fail "last heartbeat ${hours_since}h ago (stale)"
  fi
}

# --- mini-repos (skills, memory) ---
check_mini_repos() {
  local claude_dir="$HOME/.claude"

  if [[ ! -d "$claude_dir/.git" ]]; then
    emit_component mini_repos unknown "no git repo at $claude_dir"
    return
  fi

  local dirty
  dirty=$(cd "$claude_dir" && git status --porcelain 2>/dev/null | wc -l)

  if [[ "$dirty" -eq 0 ]]; then
    emit_component mini_repos ok "claude config repo clean"
  elif [[ "$dirty" -lt 10 ]]; then
    emit_component mini_repos degraded "${dirty} uncommitted in .claude — meta-report noise"
  else
    emit_component mini_repos fail "${dirty} uncommitted in .claude — heavy meta-report noise"
  fi
}

# --- primitives status ---
check_primitives() {
  local tool="$REPO_ROOT/tools/edge-primitives"
  if [[ ! -f "$tool" ]]; then
    emit_component primitives unknown "edge-primitives not found"
    return
  fi

  local payload
  payload=$(safe_timeout 10 python3 "$tool" status --json 2>/dev/null || echo "")
  if [[ -z "$payload" ]]; then
    emit_component primitives unknown "status unavailable"
    return
  fi

  local declared degraded active probed broken
  declared=$(echo "$payload" | jq -r '.summary.declared_total // 0' 2>/dev/null || echo 0)
  degraded=$(echo "$payload" | jq -r '.summary.degraded_total // 0' 2>/dev/null || echo 0)
  active=$(echo "$payload" | jq -r '.summary.active_total // 0' 2>/dev/null || echo 0)
  probed=$(echo "$payload" | jq -r '.summary.probed_total // 0' 2>/dev/null || echo 0)
  broken=$(echo "$payload" | jq -r '.summary.broken_total // 0' 2>/dev/null || echo 0)

  local detail
  detail="declared=${declared} degraded=${degraded} active=${active} probed=${probed} broken=${broken}"

  if [[ "$declared" -eq 0 ]] && [[ "$degraded" -eq 0 ]] && [[ "$active" -eq 0 ]] && [[ "$probed" -eq 0 ]] && [[ "$broken" -eq 0 ]]; then
    emit_component primitives unknown "no primitives declared yet"
  elif [[ "$broken" -gt 0 ]]; then
    emit_component primitives fail "$detail"
  elif [[ "$degraded" -gt 0 ]]; then
    emit_component primitives degraded "$detail"
  else
    emit_component primitives ok "$detail"
  fi
}

# --- run all ---
log_health "check-infra starting"
check_disk
check_fs_rw
check_sqlite
check_blog
check_index
check_consolidate
check_git
check_heartbeat
check_mini_repos
check_primitives
log_health "check-infra done"
