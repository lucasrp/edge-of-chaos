#!/usr/bin/env bash
# heartbeat-preflight.sh — checagem determinística antes de invocar LLM
# Custo: ~2-3 segundos, zero tokens
# Exit 0 + sinais no stdout = tem trabalho → heartbeat normal
# Exit 0 + "PREFLIGHT_CLEAN" = nada urgente → explorar (/ed-lazer, /ed-descoberta)

set -uo pipefail

TODAY=$(date +%Y-%m-%d)
SIGNALS=()

# 1. Chat pendente?
chat_pending=$(curl -s --max-time 3 'http://localhost:8766/api/chat?unprocessed=true' 2>/dev/null | \
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
insights_file=~/.claude/projects/-home-vboxuser/memory/insights.md
if [ -f "$insights_file" ]; then
  new_insights=$(grep -c '^\-' "$insights_file" 2>/dev/null || echo 0)
  read_insights=$(grep -c '\[LIDO' "$insights_file" 2>/dev/null || echo 0)
  unread=$((new_insights - read_insights))
  if [ "$unread" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("INSIGHT:${unread} insights novos")
  fi
fi

# 4. Erro pendente no debugging.md?
debug_file=~/.claude/projects/-home-vboxuser/memory/debugging.md
if [ -f "$debug_file" ]; then
  open_errors=$(grep -ci 'status:.*aberto\|status:.*open\|\[ \]' "$debug_file" 2>/dev/null || echo 0)
  if [ "$open_errors" -gt 0 ] 2>/dev/null; then
    SIGNALS+=("ERRO:${open_errors} erros pendentes")
  fi
fi

# 5. Nova sessão do usuario (última hora)?
latest_session=$(ls -t ~/.claude/projects/-home-vboxuser/*.jsonl 2>/dev/null | head -1)
if [ -n "$latest_session" ]; then
  session_age=$(( $(date +%s) - $(stat -c %Y "$latest_session" 2>/dev/null || echo 0) ))
  if [ "$session_age" -lt 7200 ] 2>/dev/null; then
    SIGNALS+=("SESSAO:sessão interativa recente ($(( session_age / 60 ))min atrás)")
  fi
fi

# 6. Bob com erro? (timeout rápido, não bloqueia)
bob_last_error=$(ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no bob \
  "tail -1 ~/edge/logs/heartbeat-${TODAY}.log 2>/dev/null" 2>/dev/null || echo "")
if echo "$bob_last_error" | grep -qi "erro\|error\|fail" 2>/dev/null; then
  SIGNALS+=("BOB:erro detectado no último beat")
fi

# 7. Inbox docs?
inbox_count=0
for dir in ~/work/docs/transcricoes/inbox/produto/ ~/work/docs/transcricoes/inbox/dev/; do
  if [ -d "$dir" ]; then
    count=$(find "$dir" -type f -name "*.md" -o -name "*.txt" 2>/dev/null | wc -l)
    inbox_count=$((inbox_count + count))
  fi
done
if [ "$inbox_count" -gt 0 ] 2>/dev/null; then
  SIGNALS+=("INBOX:${inbox_count} arquivos no inbox")
fi

# Resultado
echo "=== PREFLIGHT $(date +%H:%M) ==="
if [ ${#SIGNALS[@]} -eq 0 ]; then
  echo "PREFLIGHT_CLEAN"
  echo "Nenhum sinal detectado. Sugestão: /ed-lazer ou /ed-descoberta."
else
  echo "PREFLIGHT_WORK (${#SIGNALS[@]} sinais)"
  for s in "${SIGNALS[@]}"; do
    echo "  → $s"
  done
fi
