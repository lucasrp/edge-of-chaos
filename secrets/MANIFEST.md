# Secrets Manifest — O que cada credencial habilita

> Genótipo — este arquivo vem com o repo. Não editar.
> Valores reais ficam em `secrets/_shared.yaml` (gitignored).

---

## Core (sem ele o agente não roda)

| Secret | Serviço | O que habilita | Sem ele | Custo |
|--------|---------|----------------|---------|-------|
| `ANTHROPIC_API_KEY` | Anthropic API | Claude Code — TODO o agente | Nada funciona | Pay-per-use (~$3/1M input, ~$15/1M output Sonnet) |

---

## Recomendado (degrada significativamente sem)

| Secret | Serviço | O que habilita | Sem ele | Custo |
|--------|---------|----------------|---------|-------|
| `OPENAI_API_KEY` | OpenAI API | `edge-consult` (review adversarial), `review-gate` (LLM-as-judge no pipeline), `edge-deepresearch` (pesquisa profunda com web_search) | Sem review adversarial — skills publicam sem sanity check. Sem deepresearch. Pipeline perde uma camada de qualidade | Pay-per-use (~$2.50/1M input GPT-4o) |
| `EXA_API_KEY` | Exa Search | `edge-fontes` (busca semântica em web, papers, código), busca no heartbeat | Sem busca externa — agente opera só com conhecimento interno e WebSearch básico | Pay-per-use (~$0.01/query) |

---

## Opcional (habilita extras)

| Secret | Serviço | O que habilita | Sem ele | Custo |
|--------|---------|----------------|---------|-------|
| `XAI_API_KEY` | xAI (Grok) | Provider alternativo para `edge-consult` e `edge-adversarial-research`. Diversidade de perspectiva no review | Review adversarial funciona com OpenAI apenas. Menos diversidade | Pay-per-use |
| `GOOGLE_API_KEY` | Google AI (Gemini) | Provider alternativo para `edge-deepresearch` (google_search). Cross-provider validation | Deepresearch funciona com OpenAI apenas | Pay-per-use |
| `SERPER_API_KEY` | Serper.dev | Busca web alternativa (Google results via API) | `edge-fontes` usa Exa e WebSearch. Sem fallback Serper | Free tier 2.5k queries/mês |
| `GITHUB_PAT` | GitHub | Push autônomo, criar PRs/issues, acesso a repos privados via API | Agente não pode fazer push nem criar PRs sozinho. Precisa do operador | Free |
| `SLACK_BOT_TOKEN` | Slack API | Notificações ricas (DMs, upload de arquivos, threading), roteamento por canal, busca em canais | Sem notificações Slack. Fallback: webhook (texto simples) ou chat local | Free |
| `SLACK_APP_TOKEN` | Slack API | Socket Mode (conexão persistente, sem endpoint público) | Bot funciona via HTTP normal. Precisa de URL público para events | Free |
| `SLACK_WEBHOOK_URL` | Slack Webhooks | Notificações simples (texto pra um canal fixo) — fallback se não tiver bot_token | Sem notificações Slack | Free |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API | Alertas via Telegram (mensagens, arquivos) | Sem alertas Telegram | Free |
| `TELEGRAM_CHAT_ID` | Telegram | ID do chat para receber alertas | Bot não sabe pra onde enviar | Free |
| `CLOUDFLARE_API_TOKEN` | Cloudflare | Deploy de sites estáticos (portfolio, builds interativos) | Sem deploy automático. Upload manual | Free tier disponível |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare | Identificação da conta para deploy | Deploy Cloudflare não funciona | Free |
| `BROWSERLESS_API_KEY` | Browserless.io | Chrome headless remoto (scraping, screenshots) | Sem browser remoto. Chrome local se disponível | Free tier limitado |

---

## Onde configurar

```bash
# Copiar template e preencher
cp secrets/_shared.template.yaml secrets/_shared.yaml
chmod 600 secrets/_shared.yaml

# Ou via install.sh (interativo)
bash install.sh
```

## Como as features usam os secrets

O arquivo `config/features.yaml` controla o que está ligado/desligado.
Valor `auto` = detecta se o secret correspondente existe em `_shared.yaml`.
Valor `true`/`false` = override manual.

Exemplo: se `OPENAI_API_KEY` está vazio mas `features.yaml` tem `review.adversarial: true`, o agente tenta e falha. Se tem `review.adversarial: false`, pula silenciosamente com log.
