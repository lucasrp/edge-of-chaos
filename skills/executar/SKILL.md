---
name: {{PREFIX}}-executar
description: "Execute propostas ou mudancas nos projetos. Implementacao direta ou via task agents. Invocacao manual exclusiva — so quando o usuario pedir expressamente. Triggers on: executar, execute, rodar proposta, implementar proposta, implementar."
user-invocable: true
---

# /{{PREFIX}}-executar — Execucao de Mudancas

Implementacao direta ou via task agents. Sempre gera relatorio. So roda quando o usuario pede expressamente — heartbeat NUNCA despacha.

**Escopo:** qualquer modificacao que o usuario peca — projetos (`~/work/`), sistema (`~/edge/`, `~/.claude/skills/`), ou ambos.

**Dois perfis de execucao:**
- **Projeto (`~/work/`):** protocolo completo — git checks, testes, rollback, branch
- **Sistema (`~/edge/`, `~/.claude/`):** protocolo leve — sem git/testes, mas blog + relatorio SEMPRE

---

## Argumentos

| Argumento | Exemplo | Comportamento |
|-----------|---------|---------------|
| `#N` | `/{{PREFIX}}-executar #22` | Busca proposta #22 em propostas.md |
| Descricao | `/{{PREFIX}}-executar circuit breakers` | Busca por palavra-chave nas propostas |
| Instrucao direta | `/{{PREFIX}}-executar adicionar X no arquivo Y` | Executa sem proposta formal |
| Sem argumento | `/{{PREFIX}}-executar` | Lista propostas `[PROPOSTA]`, usuario escolhe |

---

## Protocolo (10 Passos)

### Passo 1: Entender a Instrucao

**SEMPRE rodar /{{PREFIX}}-contexto primeiro.** O /{{PREFIX}}-executar e braco da autonomia — contexto informa decisoes micro durante a execucao.

### Passo 2: Gerar PRD e Executar via Task Agents

**SEMPRE usar task decomposition.** Nao implementar diretamente.

1. **Gerar PRD** seguindo a skill `/{{PREFIX}}-prd`
2. **Executar via Task agents** (1 agent por User Story, em ordem de dependencia)

### Passo 3: Derivacao Pre-Execucao (Feynman)

ANTES de executar, derivar expectativas. Pensar em voz alta:
- **Quais arquivos vao mudar?**
- **Quais riscos prevejo?**
- **O que pode dar errado?**

### Passo 3.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/{{PREFIX}}-fontes executar "[tecnologia/padrao]"` para best practices e gotchas.

### Passo 4: Validar Precondicoes

#### Perfil Projeto (`~/work/`)
1. Projeto-alvo existe
2. Git status limpo (se dirty: **PARAR**)
3. Branch atual
4. Testes baseline
5. Salvar snapshot de rollback

#### Perfil Sistema (`~/edge/`, `~/.claude/`)
Precondicoes minimas: arquivos existem, ler antes de editar.

### Passo 5: Executar User Stories

Para cada User Story (em ordem de prioridade):
1. Ler arquivos-alvo
2. Lancar Task agent com prompt detalhado
3. Verificar resultado antes de passar para a proxima
4. Se falhou: documentar e avaliar dependencias

### Passo 6: Verificar Resultado

1. Rodar testes
2. Comparar com baseline
3. Classificar: COMPLETA ou PARCIAL

### Passo 7: Blog Entry + Relatorio (OBRIGATORIO)

```bash
consolidar-estado ~/edge/blog/entries/<slug>.md /tmp/<slug>.yaml
```

### Passo 8: Atualizar Estado

1. `propostas.md`: marcar como `[CONCLUIDA]` ou `[PARCIAL]`
2. `breaks-archive.md`: entrada completa
3. `breaks-active.md`: resumo
4. `edge-scratch add "resultado da execucao"`

### Passo 10: Relatorio ao Usuario

---

## Regras Criticas

1. **So o usuario invoca** — heartbeat NUNCA despacha /{{PREFIX}}-executar
2. **SEMPRE usar task decomposition**
3. **Testes antes E depois**
4. **Blog + Relatorio SEMPRE**
5. **Feynman: derivar ANTES, comparar DEPOIS**
6. **Parcial e OK** — documentar e parar
7. **Snapshot de rollback**
8. **Git limpo obrigatorio**
9. **SEMPRE rodar /{{PREFIX}}-contexto**

---

## Notas

- Usar `ultrathink` (thinkmax) nos passos de derivacao e analise
- Se o projeto tem CLAUDE.md proprio, seguir suas conventions
