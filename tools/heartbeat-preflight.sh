#!/usr/bin/env bash
# heartbeat-preflight.sh — checagem determinística antes de invocar LLM
# Custo: ~2-3 segundos, zero tokens
# Exit 0 + sinais no stdout = tem trabalho → heartbeat normal
# Exit 0 + "PREFLIGHT_CLEAN" = nada urgente → explorar

set -uo pipefail

TODAY=$(date +%Y-%m-%d)
SIGNALS=()

# --- Load shared paths (branding, memory, blog config) ---
# shellcheck source=../config/paths.sh
source "$(dirname "$0")/../config/paths.sh"

# 0. Health check (runs edge-check.sh, updates health/current.json)
HEALTH_SCRIPT="$(dirname "$0")/../bin/edge-check.sh"
HEALTH_FILE="$EDGE_DIR/health/current.json"

if [ -x "$HEALTH_SCRIPT" ]; then
  bash "$HEALTH_SCRIPT" >/dev/null 2>&1
fi

if [ -f "$HEALTH_FILE" ]; then
  health_score=$(python3 -c "import json; print(json.load(open('$HEALTH_FILE')).get('score', 100))" 2>/dev/null || echo 100)
  health_status=$(python3 -c "import json; print(json.load(open('$HEALTH_FILE')).get('status', 'unknown'))" 2>/dev/null || echo "unknown")

  if [ "$health_status" = "critical" ] || [ "$health_score" -lt 40 ] 2>/dev/null; then
    SIGNALS+=("HEALTH:CRITICAL score=${health_score} — maintenance mode, repair before working")
  elif [ "$health_status" = "unhealthy" ] || [ "$health_score" -lt 70 ] 2>/dev/null; then
    SIGNALS+=("HEALTH:UNHEALTHY score=${health_score} — reserve part of beat for repair")
  elif [ "$health_status" = "degraded" ] || [ "$health_score" -lt 85 ] 2>/dev/null; then
    SIGNALS+=("HEALTH:DEGRADED score=${health_score} — 1 remediation action recommended")
  fi
fi

# 1. Chat pendente?
chat_pending=$(curl -s --max-time 3 $CURL_AUTH "http://localhost:${BLOG_PORT}/api/chat?unprocessed=true" 2>/dev/null | \
  python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    msgs = [m for m in data.get('messages', []) if m.get('author') == 'user' and not m.get('processed')]
    print(len(msgs))
except: print(0)
" 2>/dev/null || echo 0)

if [ "$chat_pending" -gt 0 ] 2>/dev/null; then
  SIGNALS+=("CHAT:${chat_pending} mensagens pendentes")
fi

# 2. Fios com resurface <= hoje?
for f in "$THREADS_DIR"/*.md; do
  [ -f "$f" ] || continue
  status=$(grep '^status:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  resurface=$(grep '^resurface:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  title=$(grep '^title:' "$f" 2>/dev/null | head -1 | sed 's/^title: *//' | tr -d '"')
  owner=$(grep '^owner:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  if [ "$status" = "active" ] || [ "$status" = "waiting" ]; then
    if [ -n "$resurface" ] && [[ "$resurface" < "$TODAY" || "$resurface" == "$TODAY" ]]; then
      SIGNALS+=("THREAD:[$status] $title (owner:$owner)")
    fi
  fi
done

# 3. Insight novo (sem [LIDO])?
insights_file="${MEMORY_BASE}/insights.md"
if [ -f "$insights_file" ]; then
  new_insights=$(grep -c '^\-' "$insights_file" 2>/dev/null || echo 0)
  read_insights=$(grep -c '\[LIDO' "$insights_file" 2>/dev/null || echo 0)
  unread=$((new_insights - read_insights))
  if [ "$unread" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("INSIGHT:${unread} insights novos")
  fi
fi

# 4. Erro pendente no debugging.md?
debug_file="${MEMORY_BASE}/debugging.md"
if [ -f "$debug_file" ]; then
  open_errors=$(grep -ci 'status:.*aberto\|status:.*open\|\[ \]' "$debug_file" 2>/dev/null || echo 0)
  if [ "$open_errors" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("ERRO:${open_errors} erros pendentes")
  fi
fi

# 5. Sessão recente do operador (última 2h)?
# PROJECT_DIR already set by paths.sh
latest_session=$(ls -t "${PROJECT_DIR}"/*.jsonl 2>/dev/null | head -1)
if [ -n "$latest_session" ]; then
  session_age=$(( $(date +%s) - $(stat -c %Y "$latest_session" 2>/dev/null || echo 0) ))
  if [ "$session_age" -lt 7200 ] 2>/dev/null; then
    SIGNALS+=("SESSAO:sessão interativa recente ($(( session_age / 60 ))min atrás)")
  fi
fi

# Resultado
echo "=== PREFLIGHT $(date +%H:%M) ==="
if [ ${#SIGNALS[@]} -eq 0 ]; then
  echo "PREFLIGHT_CLEAN"
  echo "Nenhum sinal detectado. Sugestão: /${SKILL_PREFIX}-lazer ou /${SKILL_PREFIX}-descoberta."
else
  echo "PREFLIGHT_WORK (${#SIGNALS[@]} sinais)"
  for s in "${SIGNALS[@]}"; do
    echo "  → $s"
  done
fi
