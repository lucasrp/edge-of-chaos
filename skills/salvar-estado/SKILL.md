---
name: salvar-estado
description: "Save current session state to persistent memory. Checkpoint working context, pending decisions, and insights before ending a session or switching context. Triggers on: salvar estado, save state, checkpoint, salvar, guardar estado, salvar contexto."
user-invocable: true
---

# Salvar Estado — Checkpoint de Sessao

Complemento write-side do `/carregar` (que e read-side). Salva o estado da sessao atual em memoria persistente, permitindo que a proxima sessao retome de onde parou.

**Quando usar:**
- Antes de encerrar uma sessao longa
- Quando o usuario pede para "lembrar onde parei"
- Antes de trocar de contexto (ex: de projeto A para projeto B)
- Quando ha decisoes pendentes que nao devem ser perdidas
- No final de qualquer trabalho significativo que ainda nao foi commitado via consolidar-estado

**O que NAO e:**
- NAO e `/blog` (publicar no blog interno)
- NAO e `/reflexao` (auto-revisao profunda)
- NAO e git commit (controle de versao)
- E um checkpoint rapido e leve — maximo 2-3 minutos

---

## O Job

Capturar e persistir o estado da sessao atual em 4 dimensoes:
1. **O que estava sendo feito** — tarefa, projeto, contexto
2. **Decisoes tomadas** — o que foi decidido e por que
3. **Pendencias** — o que ficou para depois
4. **Insights** — o que foi aprendido (candidato a claim)

---

## Protocolo (seguir na ordem)

### Passo 1: Sintetizar o estado da sessao

Sem ler arquivos adicionais — usar o que ja esta no contexto da conversa. Produzir mentalmente:

- **Projeto/area:** em que area de trabalho a sessao operou
- **Tarefa principal:** o que o usuario pediu ou o heartbeat despachou
- **Status:** concluido / parcialmente concluido / bloqueado / abandonado
- **Decisoes:** qualquer decisao tomada (tecnica, arquitetural, de prioridade)
- **Pendencias:** o que ficou aberto, depende de terceiro, ou precisa de mais trabalho
- **Insights:** qualquer aprendizado que vale preservar
- **Artefatos criados:** arquivos novos ou modificados significativamente

### Passo 2: Atualizar breaks-active.md

Adicionar/atualizar na secao "Ultimos 5 Breaks" (ou secao equivalente):

```bash
# Ler estado atual
cat ~/.claude/projects/-home-vboxuser/memory/breaks-active.md | head -30
```

Formato da entrada:
```markdown
- **[DATA] [TIPO] — [RESUMO]**: [Status]. [Pendencias se houver].
```

### Passo 3: Registrar observacoes no scratchpad

```bash
edge-scratch add "[resumo do que aconteceu na sessao]"
```

Se multiplos pontos, registrar cada um:
```bash
edge-scratch add "Decisao: [o que foi decidido]"
edge-scratch add "Pendencia: [o que ficou aberto]"
edge-scratch add "Insight: [o que aprendi]"
```

### Passo 4: Atualizar insights (se houver)

Se a sessao produziu insights do usuario (Lucas disse algo que vale preservar):

```bash
# Verificar se insights.md existe e adicionar
cat >> ~/.claude/projects/-home-vboxuser/memory/insights.md << 'EOF'

### [DATA] — [Titulo do Insight]
[Conteudo do insight]
EOF
```

### Passo 5: Atualizar fios relevantes (se aplicavel)

Se a sessao avancou algum fio de investigacao:

```bash
# Verificar fios existentes
ls ~/edge/threads/
```

Atualizar o arquivo do fio com:
- Novo `updated:` no frontmatter
- Nota sobre o que avancou
- Ajuste de `resurface:` se necessario

### Passo 6: Claims (se aplicavel)

Se a sessao produziu conhecimento duravel que merece virar claim:

```bash
edge-claims add "Fato verificado que aprendi nesta sessao"
edge-claims add '!Gap que identifiquei e ainda nao sei'
```

### Passo 7: Confirmar ao usuario

Formato de saida:

```
## Estado Salvo

**Sessao:** [data/hora]
**Area:** [projeto/contexto]
**Status:** [concluido/parcial/bloqueado]

### O que foi feito
- [item 1]
- [item 2]

### Decisoes
- [decisao 1 e racional]

### Pendencias
- [pendencia 1]

### Para retomar
[Instrucao concreta do que fazer no proximo /carregar]
```

---

## Regras

1. **Rapidez:** Maximo 2-3 minutos. Nao e reflexao profunda — e checkpoint.
2. **Nao duplicar:** Se a sessao ja publicou via consolidar-estado, o state commit (Phase 5) ja salvou claims/threads. Nao duplicar.
3. **Sem overthink:** Se a sessao foi curta ou trivial, registrar apenas no scratchpad. Nao forcar insights onde nao ha.
4. **Sempre confirmar:** Mostrar ao usuario o que foi salvo. Transparencia.
5. **Git:** NAO fazer git commit automaticamente. O estado e salvo em arquivos de memoria, nao em VCS.
