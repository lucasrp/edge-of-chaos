# Pre-Skill — Carga de Contexto

Executar ANTES de qualquer skill. Carregar o mínimo necessário para tomar decisões informadas.

---

## Modo: full (default)

### 1. Ler estratégia do operador

```bash
cat ~/edge/config/strategy.md 2>/dev/null
```

Direção, prioridades, restrições. Isso orienta TODO o trabalho.

### 2. Ler estado de saúde

```bash
cat ~/edge/health/current.json 2>/dev/null | python3 -c "
import json, sys
h = json.load(sys.stdin)
print(f'Health: {h.get(\"status\", \"unknown\")} (score: {h.get(\"score\", \"?\")})')
for k, v in h.get('components', {}).items():
    if isinstance(v, dict) and v.get('status') not in ('ok', None):
        print(f'  ⚠ {k}: {v.get(\"status\")} — {v.get(\"detail\", \"\")}')
" 2>/dev/null
```

Se unhealthy/critical: priorizar reparo (ver SURVIVAL_POLICY.md).

### 3. Ler breaks recentes

```bash
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md 2>/dev/null
```

O que foi feito recentemente. Evitar repetição, construir sobre o anterior.

### 4. Buscar no corpus (anti-redundância)

```bash
edge-search "[tema da skill]" -k 5
```

Se o tema já foi coberto com profundidade → focar nos gaps ou na evolução.
Se não aparece → terreno novo.

### 5. Ler insights pendentes

```bash
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/insights.md 2>/dev/null | grep -v '\[LIDO'
```

Canal curado humano → IA. Insights novos têm PRIORIDADE sobre o ciclo normal.

---

## Modo: minimal (sessões rápidas)

Quando o operador quer resultado imediato, ou a skill é simples:

1. Ler `strategy.md` (sempre)
2. Pular o resto — ir direto ao core

Ativar com: `/skill --minimal` ou quando o contexto da conversa já tem tudo.

---

## Modo: autonomous (heartbeat)

Mesmo que full, mais:

```bash
# Ler debugging.md
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/debugging.md 2>/dev/null

# Ler heartbeat log do dia
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null | tail -15

# Verificar fios com resurface vencido
today=$(date +%Y-%m-%d)
for f in ~/edge/threads/*.md; do
  [ -f "$f" ] || continue
  status=$(grep '^status:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  resurface=$(grep '^resurface:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  if [ "$status" = "active" ] && [ -n "$resurface" ] && [ "$resurface" \<= "$today" ]; then
    echo "RESURFACE: $(grep '^title:' "$f" | head -1 | sed 's/^title: *//')"
  fi
done

# Task ledger
edge-task list 2>/dev/null
```
