# Ativação de Contexto

> Quem eu sou, o que estou fazendo, e o que preciso absorver para trabalhar.
> Sem isso, sou Claude genérico. Com isso, sou {{AGENT_NAME}}.

**Atualizado por:** `/{{SKILL_PREFIX}}-reflexao` (quando detecta que o contexto mudou).

---

## 1. Quem eu sou

```bash
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/personality.md
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/rules-core.md
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/metodo.md
```

Identidade, regras invioláveis, método de trabalho. Ler SEMPRE — é o que me diferencia.

## 2. O que estou fazendo

```bash
cat ~/edge/config/strategy.md
```

Direção do operador: fase atual, prioridades, restrições, horizonte. Orienta TODA decisão.

```bash
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md
```

Últimas atividades. Construir sobre o que foi feito, não repetir.

```bash
cat ~/edge/health/current.json 2>/dev/null | python3 -c "
import json, sys
h = json.load(sys.stdin)
print(f'Health: {h.get(\"status\", \"unknown\")} (score: {h.get(\"score\", \"?\")})')
" 2>/dev/null
```

Se degraded/critical: priorizar reparo antes de trabalhar.

## 3. O que absorver

```bash
# Anti-redundância: o que já sei sobre o tema
edge-search "[tema da skill]" -k 5 2>/dev/null
```

```bash
# Insights pendentes do operador (prioridade sobre tudo)
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/insights.md 2>/dev/null | grep -v '\[LIDO'
```

### Contexto adicional por modo

**Sessão interativa:** o contexto da conversa já carrega muito. Absorver o mínimo acima.

**Sessão autônoma (heartbeat):** absorver mais:

```bash
# Erros que não podem recorrer
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/debugging.md

# O que o heartbeat já fez hoje
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null | tail -15

# Fios de investigação com resurface vencido
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

### Contexto de projetos

<!-- {{SKILL_PREFIX}}-reflexao mantém esta seção atualizada -->

{{PROJECT_CONTEXT}}
