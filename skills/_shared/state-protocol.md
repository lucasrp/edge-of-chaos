# State Protocol — Gestao de Estado entre Skills

Usado por: TODAS as skills que produzem output ou alteram estado.
Cada skill referencia este arquivo em vez de ter suas proprias instrucoes de state management.

**Decisoes de autonomia:** ver `~/edge/autonomy/autonomy-policy.md` (quando executar vs perguntar).
**Ferramenta de auditoria:** `edge-state-audit` (snapshot, propose, audit, scan).
**Tracking de passos:** `edge-skill-step` (registra passos executados/pulados por skill).
**Consistencia de estado:** `edge-state-lint` (detecta drift entre arquivos de memoria).

---

## Step Tracking (OBRIGATORIO em skills com protocolo)

Ao executar uma skill com passos numerados, logar cada passo executado:

```bash
edge-skill-step <skill> <step_id>              # passo executado
edge-skill-step <skill> skip <step_id> [razao]  # passo pulado explicitamente
edge-skill-step <skill> end                     # summary (detecta skips silenciosos)
```

**Regra:** chamar `edge-skill-step <skill> end` ao finalizar a skill. O tool compara passos logados contra o registry (`~/edge/tools/skill-steps-registry.yaml`) e reporta passos silenciosamente pulados.

Se um passo e pulado por razao valida (ex: cache hit, ja rodou nesta sessao), usar `skip` com razao. Passo nao logado nem como skip = **silent skip** = /{{PREFIX}}-reflexao vai flaggear.

---

## Principio Central

**Toda mudanca em arquivo protegido deve ser PROPOSTA antes e AUDITADA depois.**

O agente pode editar seus proprios arquivos de estado — mas cada mudanca precisa ser:
1. **Declarada** (proposta com justificativa ANTES de editar)
2. **Visivel** (auditada automaticamente pelo pipeline)
3. **Rastreavel** (registrada no commit com status ok/partial/failed)

Mudanca nao proposta em arquivo protegido = **violacao fatal** = pipeline abortado.

---

## Arquivos Protegidos

Qualquer mudanca nesses arquivos e monitorada por `edge-state-audit`:

**Memoria:**
- `memory/MEMORY.md`
- `memory/debugging.md`
- `memory/personality.md`
- `memory/insights.md`

**Autonomia:**
- `~/edge/autonomy/capabilities.md`
- `~/edge/autonomy/frontier.md`
- `~/edge/autonomy/workflows.md`
- `~/edge/autonomy/metrics.md`
- `~/edge/autonomy/{{PREFIX}}-log.md`
- `~/edge/autonomy/autonomy-policy.md`

**Skills:**
- `skills/*/SKILL.md`
- `skills/_shared/*.md`

**Excecao:** debugging.md pode ser editado imediatamente quando um erro CRITICO e encontrado (>5min desperdicados, intervencao do usuario, erro que vai recorrer). Registrar a excecao no scratchpad.

---

## Fluxo Completo (com mudancas de estado)

### Passo 1: Executar skill + anotar no scratchpad

```bash
edge-scratch add "o que observei, descobri, ou quero registrar"
```

Acumular observacoes. NAO editar arquivos protegidos ainda.

### Passo 2: Snapshot PRE (antes de qualquer mudanca)

Quando a skill identifica que precisa alterar arquivos protegidos:

```bash
edge-state-audit snapshot --slug <SLUG>
```

Captura SHA256 de todos os arquivos protegidos ANTES de qualquer edicao.
O pipeline (consolidar-estado Phase 0a) pula se o snapshot ja existir.

### Passo 3: Propor mudancas

Declarar EXATAMENTE quais arquivos protegidos serao modificados e por que:

```bash
# Criar YAML com as mudancas propostas
cat > /tmp/state-changes-<SLUG>.yaml <<'EOF'
changes:
  - path: "memory/MEMORY.md"
    action: modify
    reason: "Adicionar insight sobre X confirmado nesta sessao"
    sections: ["Conhecimento Consolidado"]
  - path: "~/edge/autonomy/capabilities.md"
    action: modify
    reason: "Registrar nova capacidade #24"
  - path: "~/edge/autonomy/{{PREFIX}}-log.md"
    action: modify
    reason: "Append entrada de expansao"
EOF

# Registrar proposta
edge-state-audit propose --slug <SLUG> --file /tmp/state-changes-<SLUG>.yaml
```

**Regras da proposta:**
- **Nivel de arquivo + acao + justificativa.** NAO detalhar linhas/hunks.
- Acoes: `add` (arquivo novo), `modify` (alterar existente), `delete` (remover)
- `sections` e opcional — indica quais secoes serao afetadas
- Proposta reflete **intencao original** — NUNCA reescrever apos execucao

### Passo 4: Executar mudancas

Agora sim, editar os arquivos protegidos conforme proposto.

Se durante a edicao perceber que precisa mudar um arquivo NAO proposto:
- **Pare.** Atualize a proposta com `edge-state-audit propose` novamente.
- Ou aceite que a auditoria registrara como violacao.

### Passo 5: Criar blog entry + claims

```yaml
claims:
  - "Fato verificado que aprendi"
  - "!Gap — coisa que ainda nao sei"
threads: [fio-relacionado]
keywords: [kw1, kw2]
```

Claims sao o conhecimento duravel. O que sobrevive sem reler o texto inteiro.

### Passo 6: Publicar via consolidar-estado

```bash
# Com content report
consolidar-estado ~/edge/blog/entries/<slug>.md /tmp/spec-<skill>.yaml

# Sem content report (meta-only)
consolidar-estado ~/edge/blog/entries/<slug>.md
```

O pipeline faz automaticamente:
- **Phase 0a:** Snapshot PRE (pula se ja existe — Passo 2)
- **Phase 1-4:** Entry, report, verificacao, meta-report
- **Phase 5:** State commit (claims + threads + event)
- **Phase 5b:** **State audit** — compara snapshot PRE vs estado atual vs proposta
  - `exit 0` = OK (tudo proposto e executado)
  - `exit 2` = partial (proposto mas nao executado — WARN)
  - `exit 4` = divergencia (acao diferente da proposta — **ABORT**)
  - `exit 5` = violacao (mudanca nao proposta — **ABORT**)
- **Phase 6:** Diffs + git commit com `[state:ok|partial|failed]`

### Passo 7: Ler meta-report

O pipeline imprime o path. Ler antes de continuar.

---

## Fluxo Simplificado (sem mudancas de estado)

Se a skill NAO altera nenhum arquivo protegido (ex: blog entry puro, pesquisa):

1. Executar skill
2. Anotar no scratchpad
3. Criar blog entry com claims
4. `consolidar-estado` (Phase 0a captura snapshot, Phase 5b confirma que nada mudou — OK)

Sem proposta necessaria. O pipeline e backwards-compatible.

---

## Politica de Resultados da Auditoria

| Caso | Resultado | Acao |
|------|-----------|------|
| Proposto e executado conforme | OK | Pipeline continua |
| Proposto mas nao executado | WARN (exit 2) | Pipeline continua, commit registra `partial` |
| Executado sem proposta | VIOLACAO (exit 5) | **Pipeline ABORTADO** |
| Acao diferente da proposta | DIVERGENCIA (exit 4) | **Pipeline ABORTADO** |
| Nenhuma proposta, nenhuma mudanca | OK | Pipeline continua |

**Regra principal:** para arquivos protegidos, qualquer mudanca NAO proposta e falha fatal.

---

## O Que Substituiu o Que

| Antes | Agora |
|-------|-------|
| Append 3-5 linhas no working-state.md Timeline | `edge-scratch add "observacao"` |
| Ler working-state.md para contexto | Ler `~/edge/briefing.md` (gerado por edge-digest) |
| Atualizar "Threads Ativos" manualmente | Threads em `~/edge/threads/`, atualizados pelo pipeline |
| Editar MEMORY.md/debugging.md ad-hoc | Proposta → edicao → auditoria |
| breaks-archive.md / breaks-active.md | Continua igual (registro de breaks, nao de estado) |

---

## Registro de Breaks (preservado)

Skills que fazem breaks (/{{PREFIX}}-lazer, /{{PREFIX}}-pesquisa, /{{PREFIX}}-descoberta, /{{PREFIX}}-planejar) continuam registrando em:

1. **breaks-archive.md** — entrada completa com metadados
2. **breaks-active.md** — resumo dos ultimos 5 breaks

Isto NAO muda. Breaks sao registro de atividade, nao gestao de estado.

---

## Glossario

| Termo | Definicao |
|-------|-----------|
| **scratchpad** | Arquivo temporario (`/tmp/edge-scratch-*.md`) para observacoes mid-sessao |
| **meta-report** | Markdown em `~/edge/meta-reports/` com state delta + scratchpad + adversarial |
| **content report** | HTML em `~/edge/reports/` — artefato analitico pesado (opcional) |
| **briefing.md** | `~/edge/briefing.md` — estado compactado, gerado por edge-digest |
| **claims** | Conhecimento duravel no frontmatter. `!` = gap aberto |
| **threads** | Fios de investigacao em `~/edge/threads/` |
| **events** | Transicoes de estado em `~/edge/logs/events.jsonl` |
| **state commit** | Phase 5 do consolidar-estado: claims + threads + events + digest |
| **state proposal** | YAML em `~/edge/meta-reports/<slug>.state-proposal.yaml` com mudancas pretendidas |
| **state audit** | YAML em `~/edge/meta-reports/<slug>.state-audit.yaml` com resultado PRE vs POST |
| **snapshot PRE** | YAML em `~/edge/state-snapshots/<slug>.pre.yaml` com SHA256 antes das mudancas |

---

## Referencia Rapida para Skills

Adicionar no SKILL.md de cada skill:

```markdown
**Seguir `skills/_shared/state-protocol.md` para gestao de estado.**
```

### Se a skill modifica arquivos protegidos:
```markdown
### Gestao de Estado
1. `edge-state-audit snapshot --slug <SLUG>` (antes de editar)
2. `edge-state-audit propose --slug <SLUG> --file /tmp/state-changes.yaml`
3. Editar arquivos protegidos
4. `consolidar-estado` audita automaticamente (Phase 5b)
```

### Se a skill NAO modifica arquivos protegidos:
```markdown
### Registrar observacoes
`edge-scratch add "o que aconteceu e por que"` durante execucao.
Estado e processado na publicacao (meta-report → state commit).
```
