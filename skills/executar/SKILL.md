---
name: executar
description: "Execute propostas ou mudancas nos projetos. Implementacao direta ou via Ralph. Invocacao manual exclusiva — so quando o usuario pedir expressamente. Triggers on: executar, execute, rodar proposta, implementar proposta, implementar."
user-invocable: true
---

# /executar — Execucao de Mudancas

Implementacao direta ou via Ralph. Sempre gera relatorio. So roda quando o usuario pede expressamente — heartbeat NUNCA despacha.

**Escopo:** qualquer modificacao que o usuario peca — projetos (`~/tcu/`), sistema (`~/edge/`, `~/.claude/skills/`), ou ambos.

**Dois perfis de execucao:**
- **Projeto (`~/tcu/`):** protocolo completo — git checks, testes, rollback, branch
- **Sistema (`~/edge/`, `~/.claude/`):** protocolo leve — sem git/testes, mas blog + relatorio SEMPRE

---

## Argumentos

| Argumento | Exemplo | Comportamento |
|-----------|---------|---------------|
| `#N` | `/executar #22` | Busca proposta #22 em propostas.md |
| Descricao | `/executar circuit breakers` | Busca por palavra-chave nas propostas |
| Instrucao direta | `/executar adicionar termination conditions no base_chat.py` | Executa sem proposta formal |
| Sem argumento | `/executar` | Lista propostas `[PROPOSTA]`, usuario escolhe |

---

## Protocolo (10 Passos)

### Passo 1: Entender a Instrucao

Ler o minimo necessario para executar:

1. **Proposta/instrucao** — localizar proposta em propostas.md ou entender instrucao direta do usuario
2. **Se proposta formal:** ler relatorio HTML da proposta para linhagem e detalhes tecnicos
3. **Se alvo e projeto ~/tcu/:** ler CLAUDE.md do projeto-alvo (se existir) para conventions

**SEMPRE rodar /contexto primeiro.** O /executar e braco da autonomia — contexto informa decisoes micro durante a execucao. Mesmo com instrucao direta, o contexto evita erros de escopo e garante coerencia com o estado atual do sistema.

### Passo 2: Gerar PRD e Executar via Task Agents

**SEMPRE usar Ralph (skill /ralph).** Nao perguntar modo, nao implementar direto.

1. **Gerar PRD** seguindo a skill `/prd`:
   - User Stories pequenas (1 por context window)
   - Ordem por dependencia
   - Acceptance criteria com testes
   - Salvar em `~/edge/notes/prd-executar-[slug].md`

2. **Converter para prd.json** usando a skill `/ralph`

3. **Executar via Task agents** (1 agent por User Story, em ordem de dependencia):
   - Cada Task agent recebe: specs da US, arquivos relevantes, acceptance criteria
   - Funciona identico a uma iteracao Ralph — contexto isolado, 1 story por vez
   - **Nota:** `ralph.sh` NAO roda nested dentro de outra sessao Claude Code (env CLAUDECODE bloqueia). Task agents sao o mecanismo correto.

### Passo 3: Derivacao Pre-Execucao (Feynman)

ANTES de executar, derivar expectativas. Pensar em voz alta:

- **Quais arquivos vao mudar?** (listar com base no codigo existente)
- **Quais riscos prevejo?** (conflitos, dependencias, side effects)
- **O que pode dar errado?** (cenarios de falha)

Anotar gaps explicitamente:
```
[GAP: nao sei se X vai conflitar com Y]
[GAP: preciso verificar se Z ja existe no projeto]
```

**Alimenta a secao "Expectativa vs Realidade" do relatorio final.**

### Passo 3.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes executar "[tecnologia/padrao]"` para obter best practices e gotchas de todas as fontes relevantes (Web, X, GitHub).

Incorporar na derivacao pre-execucao (Passo 3) e citar no relatorio (com URL).

### Passo 4: Validar Precondicoes

#### Perfil Projeto (`~/tcu/`)

Verificar TODOS os itens antes de prosseguir:

1. **Projeto-alvo existe:** `ls ~/tcu/[projeto]`
2. **Git status limpo:** `cd ~/tcu/[projeto] && git status --porcelain`
   - Se dirty: **PARAR.** Reportar ao usuario. Nao continuar com working tree suja.
3. **Branch atual:** `git branch --show-current`
   - Se `main` ou `master`: perguntar se quer criar branch nova.
4. **Testes baseline:** Rodar suite ANTES de mudar qualquer coisa
   - Python: `pytest` / Node: `npm test` / Typecheck: `npx tsc --noEmit` ou `mypy .`
5. **Salvar snapshot de rollback:**
   ```
   BRANCH=[branch atual]
   SHA=[ultimo commit SHA]
   TESTES_BASELINE=[resultado]
   ```

**Se precondicao critica falha (projeto nao existe, git sujo): PARAR.**

#### Perfil Sistema (`~/edge/`, `~/.claude/`)

Precondicoes minimas:
1. **Arquivos-alvo existem:** verificar paths
2. **Ler arquivos antes de editar:** entender o que existe antes de mudar
3. **Se server (blog, etc.):** verificar se esta rodando (`systemctl --user status`)

Nao ha git, testes ou rollback formal. O blog + relatorio servem como documentacao da mudanca.

### Passo 5: Executar User Stories

O PRD e prd.json ja foram gerados no Passo 2. A execucao acontece via Task agents (Passo 2.3).

Para cada User Story (em ordem de prioridade):
1. Ler arquivos-alvo que a story vai modificar
2. Lancar Task agent com prompt detalhado (specs, criteria, contexto dos arquivos)
3. Verificar resultado do agent antes de passar para a proxima story
4. Se story falhou: documentar e avaliar se proximas stories dependem dela

### Passo 6: Verificar Resultado

Apos execucao do Ralph:

1. **Rodar testes:**
   ```bash
   cd ~/tcu/[projeto] && pytest  # ou npm test
   ```
2. **Comparar com baseline do Passo 4**
3. **git diff contra snapshot**
4. **Classificar:**
   - **COMPLETA:** tudo OK
   - **PARCIAL:** algo faltou ou quebrou

**Se testes quebraram: NAO fazer push. Alertar usuario.**

### Passo 7: Blog Entry + Relatorio (OBRIGATORIO)

Criar entrada no blog (`~/edge/blog/entries/`) e gerar relatorio numa unica chamada:
- Tag: `execucao`
- Campo `report:` com nome deterministico

```bash
consolidar-estado ~/edge/blog/entries/<slug>.md /tmp/<slug>.yaml
```

Relatorio YAML spec:

```yaml
title: "Execucao: [nome]"
subtitle: "[resumo do que foi feito]"
date: "DD/MM/YYYY"

sections:
  - title: "1. Linhagem"           # De onde veio esta mudanca
  - title: "2. Derivacao Pre-Execucao"  # Expectativas (Passo 3)
  - title: "3. Execucao"           # O que foi feito, arquivo por arquivo
  - title: "4. Expectativa vs Realidade"  # Gaps entre previsto e real
  - title: "5. Testes"             # Baseline vs resultado
  - title: "6. O que Nao Sei"      # Riscos residuais
  - title: "7. Contextualizacao e Glossario"
```

Usar block types do relatorio-tcu (diff-block para mudancas, comparison para antes/depois, etc.).

### Passo 8: Atualizar Estado

1. **`propostas.md`:** marcar como `[CONCLUIDA]` ou `[PARCIAL]` (se veio de proposta)
2. **`breaks-archive.md`:** entrada completa
3. **`breaks-active.md`:** resumo 3-5 linhas
4. **Observações:** `edge-scratch add "resultado da execução"` (estado via meta-report, ver `state-protocol.md`)
5. **Blog:** comment final com resultado + link ao relatorio

### Passo 10: Relatorio ao Usuario

Mensagem final com:
- Resumo do que foi feito
- Diff principal (arquivos criados/modificados)
- Resultado dos testes (baseline vs final)
- Link ao relatorio HTML
- Proximos passos sugeridos

---

## Regras Criticas

1. **So o usuario invoca** — heartbeat NUNCA despacha /executar
2. **SEMPRE usar Ralph** — gerar PRD + prd.json, Ralph executa. Sem modo direto
3. **Nunca implementar diretamente** — o /executar gera PRD e delega pro Ralph
4. **Testes antes E depois** — baseline obrigatorio para perfil projeto. Perfil sistema: verificar que funciona apos mudanca
5. **Blog + Relatorio SEMPRE** — sem excecao, independente do perfil, mesmo para mudancas pequenas
6. **Feynman: derivar ANTES, comparar DEPOIS** — expectativas antes, gaps depois
7. **Parcial e OK** — documentar e parar. Nao forcar completude
8. **Snapshot de rollback** — branch + commit salvos antes de qualquer mudanca (perfil projeto)
9. **Git limpo obrigatorio** — nao executar com working tree suja (perfil projeto)
10. **SEMPRE rodar /contexto** — /executar e braco da autonomia, contexto informa decisoes micro

---

## Tratamento de Falhas

| Cenario | Acao |
|---------|------|
| Testes quebraram | Documentar, NAO fazer push, alertar usuario |
| Conflito de merge | Parar, documentar, usuario resolve |
| Context exhaustion | Blog ja salvo (Passo 7), relatorio na proxima sessao |
| Proposta nao encontrada | Listar propostas, pedir escolha |
| Git sujo | Parar no Passo 4, reportar |
| Task agent falhou em uma story | Documentar, avaliar dependencias, prosseguir ou parar |
| Testes baseline falhando | Reportar antes de prosseguir |

---

## Notas

- `/executar` e o caminho para modificar projetos (`~/tcu/`) e sistema (`~/edge/`, `~/.claude/`). Qualquer mudanca pedida pelo usuario passa por aqui.
- O fluxo pode ser simples (instrucao direta → implementar → verificar → relatorio) ou completo (proposta → PRD → Ralph → testes → relatorio).
- Usar `ultrathink` (thinkmax) nos passos de derivacao (Passo 3) e analise (Passo 6/8).
- Se o projeto tem CLAUDE.md proprio, seguir suas conventions.
- SEMPRE rodar /contexto como primeiro passo. O /executar e braco da autonomia — contexto informa decisoes durante toda a execucao.
