#!/usr/bin/env bash
# heartbeat-preflight.sh — checagem determinística antes de invocar LLM
# Custo: ~2-3 segundos, zero tokens
# Exit 0 + sinais no stdout = tem trabalho → heartbeat normal
# Exit 0 + "PREFLIGHT_CLEAN" = nada urgente → explorar

set -uo pipefail

TODAY=$(date +%Y-%m-%d)
SIGNALS=()

# --- Load branding config (phenotype) ---
BRANDING_FILE="$HOME/edge/config/branding.yaml"
if [ -f "$BRANDING_FILE" ]; then
  BLOG_PORT=$(grep '^  port:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}')
  BLOG_AUTH_ENABLED=$(grep '^  auth_enabled:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}')
  BLOG_AUTH_USER=$(grep '^  auth_user:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  BLOG_AUTH_PASS=$(grep '^  auth_pass:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  MEMORY_PROJECT_DIR=$(grep '^memory_project_dir:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  SKILL_PREFIX=$(grep '^skill_prefix:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
else
  BLOG_PORT=8766
  BLOG_AUTH_ENABLED=false
  BLOG_AUTH_USER=""
  BLOG_AUTH_PASS=""
  MEMORY_PROJECT_DIR=""
  SKILL_PREFIX="ed"
fi
BLOG_PORT=${BLOG_PORT:-8766}
SKILL_PREFIX=${SKILL_PREFIX:-ed}

# Build curl auth flag
CURL_AUTH=""
if [ "$BLOG_AUTH_ENABLED" = "true" ] && [ -n "$BLOG_AUTH_USER" ]; then
  CURL_AUTH="-u ${BLOG_AUTH_USER}:${BLOG_AUTH_PASS}"
fi

# Memory project path
if [ -n "$MEMORY_PROJECT_DIR" ]; then
  MEMORY_BASE="$HOME/.claude/projects/${MEMORY_PROJECT_DIR}/memory"
else
  MEMORY_BASE="$HOME/.claude/projects/$(ls "$HOME/.claude/projects/" 2>/dev/null | head -1)/memory"
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
for f in ~/edge/threads/*.md; do
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
PROJECT_DIR="$HOME/.claude/projects/${MEMORY_PROJECT_DIR}"
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
