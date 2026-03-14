# State Protocol — Gestão de Estado entre Skills

Usado por: TODAS as skills que produzem output ou alteram estado.
Cada skill referencia este arquivo em vez de ter suas próprias instruções de state management.

**Decisões de autonomia:** ver `~/edge/autonomy/autonomy-policy.md` (quando executar vs perguntar).
**Ferramenta de auditoria:** `edge-state-audit` (snapshot, propose, audit, scan).
**Tracking de passos:** `edge-skill-step` (registra passos executados/pulados por skill).
**Consistência de estado:** `edge-state-lint` (detecta drift entre arquivos de memória).

---

## Step Tracking (OBRIGATÓRIO em skills com protocolo)

Ao executar uma skill com passos numerados, logar cada passo executado:

```bash
edge-skill-step <skill> <step_id>              # passo executado
edge-skill-step <skill> skip <step_id> [razão]  # passo pulado explicitamente
edge-skill-step <skill> end                     # summary (detecta skips silenciosos)
```

**Regra:** chamar `edge-skill-step <skill> end` ao finalizar a skill. O tool compara passos logados contra o registry (`~/edge/tools/skill-steps-registry.yaml`) e reporta passos silenciosamente pulados.

Se um passo é pulado por razão válida (ex: cache hit, já rodou nesta sessão), usar `skip` com razão. Passo não logado nem como skip = **silent skip** = /ed-reflexao vai flaggear.

---

## Princípio Central

**Toda mudança em arquivo protegido deve ser PROPOSTA antes e AUDITADA depois.**

O agente pode editar seus próprios arquivos de estado — mas cada mudança precisa ser:
1. **Declarada** (proposta com justificativa ANTES de editar)
2. **Visível** (auditada automaticamente pelo pipeline)
3. **Rastreável** (registrada no commit com status ok/partial/failed)

Mudança não proposta em arquivo protegido = **violação fatal** = pipeline abortado.

---

## Arquivos Protegidos

Qualquer mudança nesses arquivos é monitorada por `edge-state-audit`:

**Memória:**
- `~/.claude/projects/-home-vboxuser/memory/MEMORY.md`
- `~/.claude/projects/-home-vboxuser/memory/debugging.md`
- `~/.claude/projects/-home-vboxuser/memory/personality.md`
- `~/.claude/projects/-home-vboxuser/memory/insights.md`

**Autonomia:**
- `~/edge/autonomy/capabilities.md`
- `~/edge/autonomy/frontier.md`
- `~/edge/autonomy/workflows.md`
- `~/edge/autonomy/metrics.md`
- `~/edge/autonomy/ed-log.md`
- `~/edge/autonomy/autonomy-policy.md`

**Skills:**
- `~/.claude/skills/*/SKILL.md`
- `~/.claude/skills/_shared/*.md`

**Exceção:** debugging.md pode ser editado imediatamente quando um erro CRÍTICO é encontrado (>5min desperdiçados, intervenção do usuario, erro que vai recorrer). Registrar a exceção no scratchpad.

---

## Fluxo Completo (com mudanças de estado)

### Passo 1: Executar skill + anotar no scratchpad

```bash
edge-scratch add "o que observei, descobri, ou quero registrar"
```

Acumular observações. NÃO editar arquivos protegidos ainda.

### Passo 2: Snapshot PRE (antes de qualquer mudança)

Quando a skill identifica que precisa alterar arquivos protegidos:

```bash
edge-state-audit snapshot --slug <SLUG>
```

Captura SHA256 de todos os arquivos protegidos ANTES de qualquer edição.
O pipeline (consolidar-estado Phase 0a) pula se o snapshot já existir.

### Passo 3: Propor mudanças

Declarar EXATAMENTE quais arquivos protegidos serão modificados e por quê:

```bash
# Criar YAML com as mudanças propostas
cat > /tmp/state-changes-<SLUG>.yaml <<'EOF'
changes:
  - path: "~/.claude/projects/-home-vboxuser/memory/MEMORY.md"
    action: modify
    reason: "Adicionar insight sobre X confirmado nesta sessão"
    sections: ["Conhecimento Consolidado"]
  - path: "~/edge/autonomy/capabilities.md"
    action: modify
    reason: "Registrar nova capacidade #24"
  - path: "~/edge/autonomy/ed-log.md"
    action: modify
    reason: "Append entrada de expansão"
EOF

# Registrar proposta
edge-state-audit propose --slug <SLUG> --file /tmp/state-changes-<SLUG>.yaml
```

**Regras da proposta:**
- **Nível de arquivo + ação + justificativa.** NÃO detalhar linhas/hunks.
- Ações: `add` (arquivo novo), `modify` (alterar existente), `delete` (remover)
- `sections` é opcional — indica quais seções serão afetadas
- Proposta reflete **intenção original** — NUNCA reescrever após execução

### Passo 4: Executar mudanças

Agora sim, editar os arquivos protegidos conforme proposto.

Se durante a edição perceber que precisa mudar um arquivo NÃO proposto:
- **Pare.** Atualize a proposta com `edge-state-audit propose` novamente.
- Ou aceite que a auditoria registrará como violação.

### Passo 5: Criar blog entry + claims

```yaml
claims:
  - "Fato verificado que aprendi"
  - "!Gap — coisa que ainda não sei"
threads: [fio-relacionado]
keywords: [kw1, kw2]
```

Claims são o conhecimento durável. O que sobrevive sem reler o texto inteiro.

### Passo 6: Publicar via consolidar-estado

```bash
# Com content report
consolidar-estado ~/edge/blog/entries/<slug>.md /tmp/spec-<skill>.yaml

# Sem content report (meta-only)
consolidar-estado ~/edge/blog/entries/<slug>.md
```

O pipeline faz automaticamente:
- **Phase 0a:** Snapshot PRE (pula se já existe — Passo 2)
- **Phase 1-4:** Entry, report, verificação, meta-report
- **Phase 5:** State commit (claims + threads + event)
- **Phase 5b:** **State audit** — compara snapshot PRE vs estado atual vs proposta
  - `exit 0` = OK (tudo proposto e executado)
  - `exit 2` = partial (proposto mas não executado — WARN)
  - `exit 4` = divergência (ação diferente da proposta — **ABORT**)
  - `exit 5` = violação (mudança não proposta — **ABORT**)
- **Phase 6:** Diffs + git commit com `[state:ok|partial|failed]`

### Passo 7: Ler meta-report

O pipeline imprime o path. Ler antes de continuar.

---

## Fluxo Simplificado (sem mudanças de estado)

Se a skill NÃO altera nenhum arquivo protegido (ex: blog entry puro, pesquisa):

1. Executar skill
2. Anotar no scratchpad
3. Criar blog entry com claims
4. `consolidar-estado` (Phase 0a captura snapshot, Phase 5b confirma que nada mudou — OK)

Sem proposta necessária. O pipeline é backwards-compatible.

---

## Política de Resultados da Auditoria

| Caso | Resultado | Ação |
|------|-----------|------|
| Proposto e executado conforme | OK | Pipeline continua |
| Proposto mas não executado | WARN (exit 2) | Pipeline continua, commit registra `partial` |
| Executado sem proposta | VIOLAÇÃO (exit 5) | **Pipeline ABORTADO** |
| Ação diferente da proposta | DIVERGÊNCIA (exit 4) | **Pipeline ABORTADO** |
| Nenhuma proposta, nenhuma mudança | OK | Pipeline continua |

**Regra principal:** para arquivos protegidos, qualquer mudança NÃO proposta é falha fatal.

---

## O Que Substituiu o Quê

| Antes | Agora |
|-------|-------|
| Append 3-5 linhas no working-state.md Timeline | `edge-scratch add "observação"` |
| Ler working-state.md para contexto | Ler `~/edge/briefing.md` (gerado por edge-digest) |
| Atualizar "Threads Ativos" manualmente | Threads em `~/edge/threads/`, atualizados pelo pipeline |
| Editar MEMORY.md/debugging.md ad-hoc | Proposta → edição → auditoria |
| breaks-archive.md / breaks-active.md | Continua igual (registro de breaks, não de estado) |

---

## Registro de Breaks (preservado)

Skills que fazem breaks (/ed-lazer, /ed-pesquisa, /ed-descoberta, /ed-planejar) continuam registrando em:

1. **breaks-archive.md** — entrada completa com metadados
2. **breaks-active.md** — resumo dos últimos 5 breaks

Isto NÃO muda. Breaks são registro de atividade, não gestão de estado.

---

## Glossário

| Termo | Definição |
|-------|-----------|
| **scratchpad** | Arquivo temporário (`/tmp/edge-scratch-*.md`) para observações mid-sessão |
| **meta-report** | Markdown em `~/edge/meta-reports/` com state delta + scratchpad + adversarial |
| **content report** | HTML em `~/edge/reports/` — artefato analítico pesado (opcional) |
| **briefing.md** | `~/edge/briefing.md` — estado compactado, gerado por edge-digest |
| **claims** | Conhecimento durável no frontmatter. `!` = gap aberto |
| **threads** | Fios de investigação em `~/edge/threads/` |
| **events** | Transições de estado em `~/edge/logs/events.jsonl` |
| **state commit** | Phase 5 do consolidar-estado: claims + threads + events + digest |
| **state proposal** | YAML em `~/edge/meta-reports/<slug>.state-proposal.yaml` com mudanças pretendidas |
| **state audit** | YAML em `~/edge/meta-reports/<slug>.state-audit.yaml` com resultado PRE vs POST |
| **snapshot PRE** | YAML em `~/edge/state-snapshots/<slug>.pre.yaml` com SHA256 antes das mudanças |

---

## Referência Rápida para Skills

Adicionar no SKILL.md de cada skill:

```markdown
**Seguir `~/.claude/skills/_shared/state-protocol.md` para gestão de estado.**
```

### Se a skill modifica arquivos protegidos:
```markdown
### Gestão de Estado
1. `edge-state-audit snapshot --slug <SLUG>` (antes de editar)
2. `edge-state-audit propose --slug <SLUG> --file /tmp/state-changes.yaml`
3. Editar arquivos protegidos
4. `consolidar-estado` audita automaticamente (Phase 5b)
```

### Se a skill NÃO modifica arquivos protegidos:
```markdown
### Registrar observações
`edge-scratch add "o que aconteceu e por quê"` durante execução.
Estado é processado na publicação (meta-report → state commit).
```
