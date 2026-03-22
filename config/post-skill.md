# Post-Skill — Ações Pós-Execução

Executar APÓS a skill completar (incluindo publicação via state-protocol).
Estas ações são **fenótipo** — variam por agente e por operador.

---

## 1. Notificar o operador

Se a skill foi despachada pelo heartbeat (autônoma), reportar o que fez:

```bash
# Via Slack (se configurado)
curl -s -X POST "${SLACK_WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"[skill]: [resumo do que fez]. Report: [URL]\"}" 2>/dev/null

# Via chat assíncrono (sempre disponível)
curl -s -X POST http://localhost:${BLOG_PORT}/api/chat \
  -H "Content-Type: application/json" \
  -d '{"author":"claude","text":"[resumo do que fez]"}'
```

Se foi sessão interativa → responder no terminal, sem notificação extra.

## 2. Atualizar estratégia (se aplicável)

Se a skill produziu insight que afeta a direção do trabalho:

```bash
# Adicionar na seção "Contexto (agente)" de strategy.md
# NÃO editar as seções do operador (Direção, Prioridades)
```

## 3. Ações customizáveis por agente

Cada agente pode adicionar ações aqui conforme necessidade:

- **bob**: organizar artefatos no Google Drive
- **gauss**: sincronizar com Overleaf
- **ed**: nada adicional (Slack já configurado via MCP)

---

## Notas

- O pipeline de publicação (blog → report → consolidar-estado → adversarial) é **genotype** e fica nas skills + `_shared/state-protocol.md`
- Este arquivo é só para ações **depois** que tudo já foi publicado
- Se a skill abortou por erro, pular tudo — registrar em debugging.md
