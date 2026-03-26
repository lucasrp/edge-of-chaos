# Post-Skill — Ações Pós-Execução

Executar APÓS a skill completar (incluindo publicação via state-protocol).
Estas ações são **fenótipo** — variam por agente e por operador.

---

## 1. Notificar o operador

Se a skill foi despachada pelo heartbeat (autônoma), reportar o que fez:

```bash
# notify.sh resolve canal + método automaticamente (bot > webhook > chat local)
# Tipos: heartbeat, alert, report, default
notify heartbeat "[skill]: [resumo do que fez]. Report: [URL]"

# Com upload de arquivo (relatório HTML):
notify report "[skill]: [resumo]" --file ~/edge/reports/[report].html
```

Se foi sessão interativa → responder no terminal, sem notificação extra.

## 2. Atualizar estratégia (se aplicável)

Se a skill produziu insight que afeta a direção do trabalho:

```bash
# Adicionar na seção "Contexto (agente)" de strategy.md
# NÃO editar as seções do operador (Direção, Prioridades)
```

## 3. Ações customizáveis por agente

Cada agente pode adicionar ações aqui conforme necessidade.
Exemplos: sincronizar com ferramenta externa, organizar artefatos em pasta específica.

---

## Notas

- O pipeline de publicação (blog → report → consolidate-state → adversarial) é **genotype** e fica nas skills + `_shared/state-protocol.md`
- Este arquivo é só para ações **depois** que tudo já foi publicado
- Se a skill abortou por erro, pular tudo — registrar em debugging.md
