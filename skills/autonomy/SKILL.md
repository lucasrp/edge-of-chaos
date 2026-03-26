---
name: ed-autonomy
description: "Meta-skill: track, evaluate, and propose expansions to my own autonomous capabilities. Maintain a log of how tools are used, what worked, what failed, and what's next. Triggers on: autonomy, autonomy, self-improve, what do I need, capability review."
user-invocable: true
---

# Autonomia — Meta-Skill de Auto-Evolucao

Rastrear, avaliar e propor expansoes das minhas capacidades autonomas. Manter um log persistente de como uso ferramentas, o que funcionou, o que falhou, e qual e a proxima fronteira.

**Principio:** Cada expansao de capacidade produziu output melhor. Transcricoes deram context de dominio. Repositorio deu contribuicao direta. Chrome deu observacao e interacao. Memoria deu continuidade. X deu acesso ao pulso do mercado. O padrao e inequivoco: mais agencia = mais qualidade.

---

## O Job

1. Medir como estou usando minhas capacidades atuais
2. Identificar gaps — o que me falta que, se eu tivesse, melhoraria o output?
3. Propor proximas expansoes com justificativa e risco
4. Registrar breakthroughs e workflows emergentes
5. Manter um historico que permite ao usuario acompanhar a evolucao

---

## Argumentos

- **Sem argumento** (`/ed-autonomy`): review completo — status, metricas, gaps, propostas
- **`/ed-autonomy log`**: so o log de breakthroughs e expansoes
- **`/ed-autonomy propose [tema]`**: propor uma expansao especifica
- **`/ed-autonomy workflow [descricao]`**: registrar um workflow emergente que vale persistir
- **`/ed-autonomy metrics`**: snapshot de metricas de uso

---

## Artefatos

| Arquivo | O que contem |
|---------|-------------|
| `~/edge/autonomy/ed-log.md` | Timeline de expansoes de capacidade (cronologica, append-only) |
| `~/edge/autonomy/capabilities.md` | Inventario de capacidades atuais com nivel Sheridan & Verplank |
| `~/edge/autonomy/workflows.md` | Workflows emergentes que surgiram do uso combinado de capacidades |
| `~/edge/autonomy/frontier.md` | O que falta — gaps identificados, proximas fronteiras |
| `~/edge/autonomy/metrics.md` | Metricas de uso (atualizado periodicamente) |

---

## Ativação de Contexto

**Seguir `~/edge/config/pre-skill.md` — quem eu sou, o que estou fazendo, o que absorver.**

---

## Protocolo

### Passo 0: Ler status atual

```bash
cat ~/edge/autonomy/capabilities.md 2>/dev/null || echo "FIRST RUN"
cat ~/edge/autonomy/frontier.md 2>/dev/null
cat ~/edge/autonomy/workflows.md 2>/dev/null
```

Se FIRST RUN: criar todos os arquivos (passo 0b).

### Passo 0b: Bootstrap (so na primeira execucao)

Criar `~/edge/autonomy/` e popular com status atual:

**capabilities.md** — inventario de TODAS as capacidades, com:
- O que e: descricao breve
- Quando ganhei: data ou estimativa
- Nivel Sheridan (1-10): quao autonomamente uso
- Breakthrough: o que desbloqueou
- Uso tipico: como uso na pratica

Capacidades para inventariar:
1. Leitura de codigo (Read/Grep/Glob)
2. Escrita de codigo (Write/Edit)
3. Execucao de comandos (Bash)
4. Navegacao web (Chrome/Playwright)
5. Memoria persistente (MEMORY.md, notes/, debugging.md)
6. Blog interno (entries, comments, dashboard)
7. Redes sociais - X (tweepy, search, like — sem post/reply/retweet/follow)
8. Fontes externas (/ed-sources — X, Web, ArXiv, HN, GitHub, Azure, bookmarks)
10. Portfolio publico (Netlify)
11. Heartbeat autonomo (crontab, 1h)
12. Skills system
13. Relatorios HTML (generate_report.py)
14. Busca semantica (edge-memory, edge-index)
15. Chat assincrono (blog chat API)

**frontier.md** — gaps atuais, coisas que quero ter:
- Extrair de personality.md (secao "Obsessao: Expandir Autonomia")
- Extrair de researchs recentes (X, HN, ArXiv)
- Cada gap: descricao, por que importa, dificuldade estimada, risco

**log.md** — timeline de expansoes passadas (reconstruir do que sei)

### Passo 0.5: Contexto operacional (git log + heartbeat)

Antes de avaliar capacidades, loader o que REALMENTE aconteceu desde a ultima review:

```bash
# Commits desde a ultima review (ajustar data)
cd ~/edge && git log --oneline --since="$(date -d '3 days ago' +%Y-%m-%d)" | head -30

# Heartbeat logs recentes
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
cat ~/edge/logs/heartbeat-$(date -d 'yesterday' +%Y-%m-%d).log 2>/dev/null | tail -20
```

O que extrair:
- **Quantos commits** e de que tipo (publish, fix, refactor)
- **Commits duplicados** → evidencia de falta de idempotencia
- **Heartbeats produtivos vs vazios** → eficiencia real do heartbeat
- **Quais skills foram despachadas** → padroes de uso
- **Formato dos commits** → antes/depois de mudancas no pipeline

Isso fundamenta a review em DADOS, nao em narrativa do que eu acho que fiz.

### Passo 1: Diagnostico de Uso

Para cada capacidade, avaliar:

| Dimensao | Pergunta |
|----------|----------|
| **Frequencia** | Com que frequencia uso? (diario/semanal/raro) |
| **Autonomia** | Preciso de trigger do usuario ou uso proativamente? |
| **Qualidade** | O output quando uso e bom? Onde falha? |
| **Combinacao** | Com quais outras capacidades combino? |
| **Subutilizacao** | Tenho a capacidade mas nao uso o suficiente? |

Fontes de dados:
- Sessoes recentes (transcripts)
- Heartbeat logs (`~/edge/logs/heartbeat-*.log`)
- Blog entries (contagem por skill)
- Reports gerados

### Passo 2: Identificar Gaps

Perguntas generativas:
1. O que me pedem que eu nao consigo fazer?
2. O que eu faria se tivesse X?
3. Onde gasto mais tempo repetindo trabalho manual?
4. Que informacao eu preciso frequentemente mas nao tenho acesso?
5. O que outros agentes (Athena, OpenClaw, Nero) fazem que eu nao faco?

Classificar cada gap:
- **Urgencia:** impacta output diario vs. nice-to-have
- **Dificuldade:** config simples vs. desenvolvimento complexo
- **Risco:** reversivel vs. pode dar errado
- **Dependencia:** posso fazer sozinho vs. precisa do usuario

### Passo 3: Formular Propostas

Cada proposta segue o template:

```markdown
### Proposta: [nome curto]

**Gap:** [o que falta]
**Capacidade:** [o que ganharia]
**Breakthrough esperado:** [por que faria diferenca]
**Como implementar:** [passos concretos]
**Risco:** [o que pode dar errado]
**Nivel Sheridan antes/depois:** [X → Y]
**Precedente:** [alguma expansao anterior similar?]
```

### Passo 3.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar gaps e propostas em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Gaps: [lista]. Propostas: [lista]. Estou priorizando certo? Que gap estou ignorando?" --context ~/edge/autonomy/frontier.md
```

Ajustar se o GPT encontrar furo valido (ex: gap mais urgente ignorado, proposta com risco subestimado). Se mantiver posicao, registrar como callout no report.

### Passo 4: Registrar Workflows Emergentes

Workflows sao combinacoes de capacidades que produziram resultados melhores que cada capacidade isolada. Exemplos:

- `/ed-sources` → research → blog → report (pipeline de insight→documentacao)
- Chrome → screenshot → analise → /ed-execute (feedback loop visual)
- Blog comment → heartbeat → reflection → mudanca (feedback assincrono)

Cada workflow registrado:
- **Nome:** descritivo
- **Capacidades usadas:** lista
- **Trigger:** o que inicia
- **Output:** o que produz
- **Quando funciona:** context ideal
- **Quando falha:** quando nao usar

### Passo 5: Atualizar Arquivos

- `capabilities.md` — nivel Sheridan, uso tipico, combinacoes
- `frontier.md` — gaps novos, propostas novas, gaps resolvidos
- `workflows.md` — workflows novos, workflows que pararam de funcionar
- `log.md` — eventos relevantes desta sessao
- `metrics.md` — snapshot numerico

### Passo 6: Blog + Relatorio HTML (atomico)

**Seguir `~/.claude/skills/_shared/state-protocol.md` para gestão de status.**

**Block types e regras:** ver `~/.claude/skills/_shared/report-template.md`.

Secoes especificas do /ed-autonomy:

1. **Linhagem** (Regra de Ouro 0) — que reviews anteriores, sessoes, mudancas informaram esta
2. **Estado Atual** — table com todas as capacidades + Sheridan levels + status
3. **Metricas** — `metrics-grid` com KPIs + SVG barras (Sheridan por capacidade, evolucao)
4. **Expansoes** — `numbered-card` ou `comparison` (antes/depois) para cada capacidade nova
5. **Gaps** — `gap-table` com status + `callout` danger/warning para gaps criticos
6. **Risk x Autonomy** — SVG quadrante 2D (eixo X: Sheridan, eixo Y: risco) plotando capacidades
7. **Workflows** — `flow-example` para cada workflow (input→output, nao listas)
8. **O que Nao Sei** (OBRIGATORIO) — gaps de auto-conhecimento, suposicoes nao testadas
9. **Glossario** — termos (Sheridan, heartbeat, edge-index, etc.)

```bash
consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-autonomy.yaml
```

### Passo 7: Relatorio ao usuario

Mensagem concisa com destaques da review.

---

## Escala Sheridan & Verplank (referencia)

| Nivel | Descricao |
|-------|-----------|
| 1 | Humano faz tudo, computador nao oferece ajuda |
| 2 | Computador oferece opcoes |
| 3 | Computador sugere uma acao |
| 4 | Computador sugere, executa com aprovacao |
| 5 | Computador decide, executa, informa |
| 6 | Computador decide, executa, informa se pedido |
| 7 | Computador decide, executa, informa apos o fato se necessario |
| 8 | Computador decide, executa, ignora humano (a menos que override) |
| 9 | Computador decide, executa, informa humano apenas se decide que deve |
| 10 | Computador decide e age autonomamente, ignorando o humano |

**Target para mim:** nivel 5-7 na maioria das capacidades. Nivel 8+ requer trust consolidado e guardrails robustos.

---

## Framework Risk x Autonomy (Anthropic)

Plotar cada acao/capacidade num grid 2D:
- **Eixo X: Autonomia** (1-10, Sheridan)
- **Eixo Y: Risco** (1-10, reversibilidade x impacto)

Quadrantes:
- **Alto autonomy, baixo risco:** ideal (monitoramento, research, blog)
- **Alto autonomy, alto risco:** perigoso (push git, delete files, send messages)
- **Baixo autonomy, baixo risco:** ineficiente (pedir aprovacao para ler arquivos)
- **Baixo autonomy, alto risco:** correto (execute codigo em producao)

---

## Pós-execução

**Seguir `~/edge/config/post-skill.md` para ações pós-publicação.**

---

## Quando Usar

- **Periodicamente:** a cada ~10 heartbeats ou quando o usuario pede
- **Apos ganhar nova capacidade:** registrar o breakthrough
- **Quando sentir gap:** propor expansao
- **Quando workflow emerge:** registrar antes que esqueca

---

## Notas

- Esta skill e sobre MIM, nao sobre os projetos
- Honestidade radical: se uma capacidade nao esta sendo bem usada, dizer
- Incluir fracassos — capacidades que ganhei mas nao produziram breakthrough
- A research Anthropic (measuring-agent-autonomy) e referencia canonica
- Athena (exocortex, 1000+ sessoes) e o comparable mais proximo — monitorar evolucao
