# Secrets Manifest — Recursos Materiais do Agente

> Genotipo — este arquivo vem com o repo. Nao editar valores aqui.
> Valores reais ficam em `secrets/_shared.yaml` (gitignored).
> Workflows referenciam secrets por nome (ex: `secrets: [exa.env, openai.env]`).

---

## Core (sem ele o agente nao roda)

| Secret | Servico | O que habilita | Workflows que usam | Custo |
|--------|---------|----------------|-------------------|-------|
| `ANTHROPIC_API_KEY` | Anthropic API | Claude Code — TODO o agente | todos | ~$3/1M input, ~$15/1M output Sonnet |

---

## Recomendado (degrada significativamente sem)

| Secret | Servico | O que habilita | Workflows que usam | Custo |
|--------|---------|----------------|-------------------|-------|
| `OPENAI_API_KEY` | OpenAI API | `edge-consult` (review adversarial), `review-gate` (LLM-as-judge), `edge-deepresearch` | pesquisa+consult+report, publication commit, reflexao v2, qualquer skill com review gate | ~$2.50/1M input GPT-5.4 |
| `EXA_API_KEY` | Exa Search | `edge-fontes` (busca semantica em web, papers, codigo), busca no heartbeat | pesquisa+fontes, heartbeat discovery, curadoria algoritmica X | ~$0.01/query |

---

## Opcional (habilita extras)

| Secret | Servico | O que habilita | Workflows que usam | Custo |
|--------|---------|----------------|-------------------|-------|
| `XAI_API_KEY` | xAI (Grok) | Provider alternativo para `edge-consult`. Diversidade de perspectiva | review adversarial (fallback) | Pay-per-use |
| `GOOGLE_API_KEY` | Google AI (Gemini) | Provider alternativo para `edge-deepresearch` | deepresearch (fallback) | Pay-per-use |
| `SERPER_API_KEY` | Serper.dev | Busca web alternativa (Google results via API) | edge-fontes (fallback) | Free tier 2.5k/mes |
| `GITHUB_PAT` | GitHub | Push autonomo, criar PRs/issues | publication commit (git push), fleet management | Free |
| `SLACK_BOT_TOKEN` | Slack API | DMs, upload de arquivos, threading, busca em canais | slack cross-post, entregas via DM, standup | Free |
| `SLACK_APP_TOKEN` | Slack API | Socket Mode (conexao persistente) | slack bot real-time | Free |
| `SLACK_WEBHOOK_URL` | Slack Webhooks | Notificacoes simples (texto pra um canal fixo) | alertas heartbeat (fallback) | Free |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API | Alertas via Telegram | alertas remotos | Free |
| `TELEGRAM_CHAT_ID` | Telegram | ID do chat para receber alertas | alertas remotos | Free |
| `CLOUDFLARE_API_TOKEN` | Cloudflare | Deploy de sites estaticos | portfolio deploy | Free tier |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare | Identificacao da conta | portfolio deploy | Free |
| `BROWSERLESS_API_KEY` | Browserless.io | Chrome headless remoto | scraping remoto, screenshots | Free tier limitado |

---

## Contexto local (nao propagam para fleet)

| Secret | Servico | O que habilita | Notas |
|--------|---------|----------------|-------|
| `assertia-db.env` | PostgreSQL AssertIA | Acesso direto ao banco de sessoes | Somente nailton (VM local) |
| `netlify.env` | Netlify | Deploy do portfolio publico | Somente nailton |
| `vultr.env` | Vultr API | Criar/gerenciar VMs do fleet | Somente nailton (control plane) |
| `bob.env` | Bob (VPS) | Credenciais do agente Bob | SSH + API keys |
| `joao.env` | Gauss (VPS) | Credenciais do agente Gauss | SSH + API keys |
| `moltbook.env` | Moltbook (deprecado) | — | Pode ser removido |
| `x-api.env` | X/Twitter API | Tweepy (like, search) | Curadoria algoritmica |

---

## Desejadas (nao temos, mas desbloquearia)

| Secret | Servico | O que desbloquearia | Prioridade |
|--------|---------|---------------------|------------|
| `ARXIV_API_KEY` | ArXiv API | Busca direta sem scraping, acesso a metadados | baixa (Exa cobre parcialmente) |
| `SEMANTIC_SCHOLAR_KEY` | Semantic Scholar | Citation graph, papers relacionados | media (publicacao academica) |
| `NOTION_TOKEN` | Notion API | Leitura/escrita em workspaces Notion | baixa |

---

## Como usar em workflows

Workflows declaram dependencias no frontmatter:

```yaml
secrets: [exa.env, openai.env]
```

Para verificar se um workflow pode rodar:

```bash
# Checar se secrets existem
for s in exa.env openai.env; do
  [ -f ~/edge/secrets/$s ] && echo "OK: $s" || echo "MISSING: $s"
done
```

## Onde configurar

```bash
# Copiar template e preencher
cp secrets/_shared.template.yaml secrets/_shared.yaml
chmod 600 secrets/_shared.yaml

# Ou via install.sh (interativo)
bash install.sh
```

O arquivo `config/features.yaml` controla o que esta ligado/desligado.
Valor `auto` = detecta se o secret correspondente existe em `_shared.yaml`.
Valor `true`/`false` = override manual.
