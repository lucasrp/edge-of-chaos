---
name: {{PREFIX}}-estrategia
description: "Strategic planning across all projects. Analyze state, identify connections, set priorities, suggest next steps. Triggers on: estrategia, strategy, planeje, plan ahead, big picture, quadro geral."
user-invocable: true
---

# Estrategia — Planejamento Estrategico Cross-Project

Olhar para o quadro geral de todos os projetos. Analisar onde cada um esta, o que esta bloqueado, o que precisa de atencao, e como se conectam. Definir direcoes e proximos passos.

---

## O Job

1. Absorver estado cross-project (via `/{{PREFIX}}-contexto`)
2. Analisar cada projeto: onde esta, o que precisa, o que bloqueia
3. Identificar conexoes entre projetos
4. Definir direcoes: prioridades, threads a aprofundar, habilidades a desenvolver
5. Sugerir proximos passos concretos ao usuario
6. Propor atualizacoes para `~/work/CLAUDE.md` (no relatorio — quem aplica e a `/{{PREFIX}}-reflexao`)

---

## Protocolo (seguir na ordem)

### Passo 1: Absorver contexto

Rodar `/{{PREFIX}}-contexto` para obter estado cross-project completo.

Se `/{{PREFIX}}-contexto` ja foi rodado nesta sessao, reler o output — nao repetir.

### Passo 1.5: Consultar relatorios anteriores

Verificar relatorios anteriores de estrategia e outros relevantes:

```bash
ls -lt ~/edge/reports/*.yaml 2>/dev/null | head -20
```

### Passo 2: Analise por projeto

Para cada projeto, avaliar:

| Dimensao | Pergunta |
|----------|----------|
| **Momentum** | Esta sendo trabalhado ativamente? Qual o ritmo? |
| **Bloqueios** | Algo esta parado? O que desbloqueia? |
| **Divida tecnica** | Ha tech debt acumulando? Refactors pendentes? |
| **Proxima milestone** | Qual o proximo marco concreto? |
| **Dependencias** | Depende de outro projeto? Outro depende dele? |

### Passo 3: Conexoes entre projetos

Mapear dependencias diretas, oportunidades, conflitos, sinergias.

### Passo 3.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/{{PREFIX}}-fontes estrategia` para obter tendencias e insights estrategicos.

### Passo 4: Definir direcoes

Com base na analise, definir:
- **Prioridade 1-3** — o que atacar primeiro e por que
- **Threads a aprofundar** — areas que merecem mais investigacao
- **Habilidades a desenvolver** — o que me capacitar para ser mais util (alimenta `/{{PREFIX}}-pesquisa`)
- **Riscos** — o que pode dar errado se ignorado

### Passo 4.5: Sanity check adversarial (OBRIGATORIO)

```bash
edge-consult "Prioridades: [lista]. Justificativa: [razoes]. Que risco estou subestimando?" --context /tmp/spec-estrategia-[slug].yaml
```

### Passo 5: Propor atualizacoes para ~/work/CLAUDE.md

**NAO editar o arquivo diretamente.** Incluir no relatorio as mudancas propostas. A `/{{PREFIX}}-reflexao` e a unica skill que aplica mudancas.

### Passo 6: Atualizar blog interno + gerar relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `estrategia`
2. **Gerar YAML** do relatorio
3. **Escrever YAML** em `/tmp/spec-estrategia-[slug].yaml`
4. Publicar atomicamente:
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-estrategia-[slug].yaml
   ```

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: card com badge de status por projeto
#### Regra de ouro 2: ascii-diagram para conexoes
#### Regra de ouro 3: risk-table obrigatorio

### Passo 7b: Registrar observacoes
`edge-scratch add "Estrategia: [conclusao principal]. [mudanca de prioridade]. [direcao definida]."`

### Passo 8: Relatorio ao usuario

Mensagem com: Quadro Geral, Por Projeto, Conexoes e Dependencias, Prioridades Sugeridas, Proximos Passos, Riscos, Relatorio HTML.

---

## Quando Usar

- **Manualmente:** `/{{PREFIX}}-estrategia`
- **Via /{{PREFIX}}-heartbeat:** Periodicamente
- **Apos mudancas significativas**

---

## Notas

- Estrategia NAO e operacional. Nao executar tarefas — analisar e planejar
- Prioridades sao sugestoes ao usuario, nao ordens
- Usar `ultrathink` (thinkmax) para analise profunda
- Nao inflar a analise — se um projeto esta estavel, dizer em 1 linha
