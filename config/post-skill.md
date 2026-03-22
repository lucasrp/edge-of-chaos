# Post-Skill — Registro e Publicação

Executar APÓS qualquer skill que produza output significativo.

---

## 1. Observações de estado

```bash
edge-scratch add "[skill]: [o que aconteceu, conclusão principal, próximo passo]"
```

Acumular durante a execução. NÃO editar arquivos protegidos diretamente (ver state-protocol.md).

## 2. Registrar no break journal

### breaks-archive.md (entrada completa)

```markdown
## [YYYY-MM-DD] [Tipo] — [Título] [via heartbeat]
- **Tipo:** [pesquisa | descoberta | lazer | estratégia | reflexão | ...]
- **Alvos/Tema:** [o que foi feito]
- **Descobertas:** [o que encontrou]
- **Aplicação:** [como se conecta ao trabalho]
- **Próximo passo:** [o que fazer a seguir]
```

### breaks-active.md (resumo)

Adicionar resumo de 3-5 linhas na seção "Últimos 5 Breaks" (remover o mais antigo se > 5).

## 3. Blog entry

Criar entry .md em `~/edge/blog/entries/` com:
- Frontmatter: title, date, tags, claims (opcionais), keywords
- Conteúdo: reflexivo e direto, o que fez e o que aprendeu
- Tag = tipo da skill (pesquisa, descoberta, lazer, etc.)

**Formato detalhado:** ver `/ed-blog` SKILL.md.

## 4. Relatório HTML (se a skill produziu análise substancial)

1. Gerar YAML spec em `/tmp/spec-[skill]-[slug].yaml`
2. **Block types e regras:** ver `~/.claude/skills/_shared/report-template.md`
3. Seções obrigatórias variam por skill — seguir o SKILL.md da skill executada

## 5. Publicar (atômico)

```bash
# Com report HTML:
consolidar-estado ~/edge/blog/entries/<slug>.md /tmp/spec-[skill]-[slug].yaml

# Sem report (blog-only):
consolidar-estado ~/edge/blog/entries/<slug>.md
```

O pipeline faz: publish blog → gerar HTML → meta-report → state commit → audit → git.

## 6. Verificar

```bash
# Validar SVGs (se report HTML)
validate-svg ~/edge/reports/[arquivo].html 2>/dev/null

# Validar blog entry
python3 ~/edge/blog/validate.py --recent 2>/dev/null
```

## 7. Descobertas (se aplicável)

Se a skill revelou algo novo (ferramenta, padrão, insight):
- Anotar em `~/edge/notes/descoberta-[nome].md`
- Ou adicionar em `descobertas.md` com `[PENDENTE]`
- A `/ed-reflexão` processa na próxima execução

## 8. Sanity check adversarial (OBRIGATÓRIO)

Sintetizar conclusões em 2-3 frases e submeter:

```bash
edge-consult "[Conclusões da skill]. Onde está mais fraco?" --context /tmp/spec-[slug].yaml
```

Ajustar se encontrar furo válido. Se mantiver posição, registrar como callout no relatório.

---

## Quando NÃO executar post-skill completo

- Skill abortou por erro → registrar em debugging.md, pular blog/report
- Skill foi minimal/rápida → edge-scratch + blog entry mínimo, sem report
- Health critical → só registrar o reparo, sem pipeline pesado

---

## Referência: State Protocol

Para skills que modificam arquivos protegidos, seguir `~/.claude/skills/_shared/state-protocol.md` ANTES do consolidar-estado.
