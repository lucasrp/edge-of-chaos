# PRD: Dashboard Setup Tab — Onboarding Visual

## Contexto

O edge-of-chaos tem 15+ arquivos configuráveis (.tpl que viram .md/.yaml após instalação). Após o `install.sh` preencher os placeholders, o operador precisa customizar esses arquivos para seu contexto. Hoje não há nenhuma interface que mostre quais arquivos existem, o que cada um faz, ou como deveria ser preenchido. O operador descobre por tentativa e erro ou lendo o código.

O "blog" na verdade é o **dashboard** do agente. Renomear e adicionar uma tab "setup" que funciona como guia de onboarding visual.

## O que Proponho

Uma nova tab **"setup"** no dashboard (ao lado de feed, chat, ops, knowledge) que:

1. Lista TODOS os arquivos que o operador pode/deve customizar
2. Mostra o conteúdo atual de cada arquivo
3. Mostra um **exemplo preenchido** didático de cada arquivo
4. Agrupa por categoria (identidade, estratégia, memória, infra)
5. Indica status: configurado vs placeholder vs vazio

## Renomeação

- A tab "ops" no header vira referência ao dashboard operacional (já existe)
- Adicionar tab "setup" para a nova funcionalidade
- No código, a variável `BLOG_DIR` e o path `/blog/` podem ficar (é o server Flask) — a mudança é só no UI

## Arquivos (o que a tab mostra)

Dois tipos de arquivo. O dashboard trata cada um diferente:

- **Editável (humano):** textarea editável + botão save. O humano escreve/ajusta. Exemplo preenchido ao lado.
- **Sistema (máquina):** read-only `<pre>`. O agente mantém via skills. O humano só observa.

### Grupo 1: Identidade (quem sou) — EDITÁVEL
| Arquivo | Propósito | Quem edita | Exemplo de |
|---------|-----------|------------|------------|
| `config/branding.yaml` | Nome, cores, porta, prefixo | Humano (install.sh preenche, humano ajusta) | `config/branding.yaml.tpl` |
| `memory/personality.md` | Perfil cognitivo, tom, comunicação | Humano escreve, reflexão pode propor mudanças | `memory/personality.md.tpl` |
| `CLAUDE.md` | Carta de operação (documento central) | Humano escreve, reflexão propõe atualizações | `templates/CLAUDE.md.tpl` |

### Grupo 2: Direção (o que faço) — EDITÁVEL
| Arquivo | Propósito | Quem edita |
|---------|-----------|------------|
| `config/interests.md` | Interesses para lazer/descoberta | Humano define interesses compartilhados |

> **Nota:** Direção e insights do humano → agente são feitos via **chat com pin**. Mensagens pinadas no chat persistem e têm prioridade sobre o ciclo normal (substituem o antigo `insights.md`). O pre-skill.md lê mensagens pinadas em vez de arquivo separado.

### Grupo 3: Método (como penso) — EDITÁVEL
| Arquivo | Propósito | Quem edita |
|---------|-----------|------------|
| `memory/rules-core.md` | Regras invioláveis (max 15) | Humano define. Reflexão pode propor novas regras |
| `memory/metodo.md` | Método de trabalho (Feynman) | Humano ajusta se quiser método diferente |
| `config/post-skill.md` | Ações pós-execução (notificar, Slack, etc.) | Humano configura canais de notificação |

### Grupo 4: Infra (como rodo) — EDITÁVEL
| Arquivo | Propósito | Quem edita |
|---------|-----------|------------|
| `kb.config` | Knowledge base (path, tipo, refresh) | Humano configura fonte de conhecimento |
| `heartbeat.sh` | Script do ciclo autônomo | Humano ajusta prompt e frequência |
| `secrets/keys.env` | API keys (Anthropic, OpenAI, Exa) | Humano fornece credenciais |

### Grupo 5: Estado do agente — SISTEMA (read-only)
| Arquivo | Propósito | Quem mantém |
|---------|-----------|-------------|
| `config/strategy.md` | Direção + prioridades + propostas | Agente (/ed-estrategia). Humano dá direção via `insights.md` |
| `config/pre-skill.md` | Ativação de contexto (instanciado) | Agente (/ed-reflexao mantém atualizado) |
| `MEMORY.md` | Índice de memória persistente | Agente (auto-memory) |
| `memory/debugging.md` | Erros que não podem recorrer | Agente (reflexão + heartbeat) |
| `memory/breaks-active.md` | Últimos 5 breaks | Agente (cada skill atualiza) |
| `briefing.md` | Estado compilado (edge-digest) | Agente (determinístico, zero tokens) |
| `health/current.json` | Saúde do sistema | Agente (edge-check.sh) |

### Grupo 6: Produção do agente — SISTEMA (read-only)
| Arquivo/Dir | Propósito | Quem mantém |
|-------------|-----------|-------------|
| `blog/entries/` | Entradas do blog (markdown) | Agente (cada skill publica) |
| `reports/` | Relatórios HTML | Agente (consolidar-estado) |
| `notes/` | Notas de pesquisa/descoberta | Agente (skills de pesquisa) |
| `threads/` | Fios de investigação (YAML) | Agente (pipeline de claims) |
| `state/` | JSON de estado (tasks, hotspots, git-signals) | Agente (tools de telemetria) |
| `logs/` | Heartbeat logs, ledger, events | Agente (automático) |

### Grupo 7: Autonomia — SISTEMA (read-only)
| Arquivo | Propósito | Quem mantém |
|---------|-----------|-------------|
| `autonomy/capabilities.md` | Inventário de capacidades (Sheridan) | Agente (/ed-autonomia) |
| `autonomy/frontier.md` | Gaps — o que falta | Agente (/ed-autonomia) |
| `autonomy/workflows.md` | Workflows emergentes | Agente (/ed-autonomia) |
| `autonomy/autonomy-policy.md` | Quando executar vs perguntar | Humano define, agente consulta |

### Grupo 8: Protocolos compartilhados — SISTEMA (read-only)
| Arquivo | Propósito | Quem mantém |
|---------|-----------|-------------|
| `skills/_shared/state-protocol.md` | Gestão de estado entre skills | Genótipo (código) |
| `skills/_shared/report-template.md` | Block types e regras de relatório | Genótipo (código) |

## User Stories

### US-1: Backend — API `/api/setup/files` + `/api/setup/save`
**Como** dashboard, **quero** endpoints que listem arquivos com conteúdo/exemplo e permitam salvar edições, **para** renderizar a tab setup.

**Acceptance Criteria:**
- GET `/api/setup/files` retorna JSON com lista de arquivos agrupados
- Cada arquivo tem: `path`, `group`, `purpose`, `content` (atual), `example` (preenchido), `status`, `editable` (bool), `owner` (human/agent/genotype)
- Status: "configured" (existe, sem placeholders), "placeholder" (contém `{{` ou `PLACEHOLDER`), "empty" (existe mas vazio), "missing" (não existe)
- POST `/api/setup/save` com `{path, content}` — SÓ aceita arquivos com `editable: true`. Rejeita com 403 se read-only
- Faz backup antes de salvar (`{path}.bak`)
- Exemplos hardcoded em `blog/setup_examples.py`

### US-2: Frontend — Template `setup.html`
**Como** operador, **quero** ver todos os arquivos organizados por grupo, editar os meus e observar os do sistema, **para** configurar e monitorar o agente.

**Acceptance Criteria:**
- Nova tab "setup" no `base.html` (entre "ops" e "knowledge")
- 8 grupos, cada um colapsável
- Grupos 1-4 (editável): cada arquivo mostra nome, propósito, status badge, owner badge "humano"
  - Ao expandir: textarea à esquerda (conteúdo atual, editável) + `<pre>` à direita (exemplo preenchido)
  - Botão "save" por arquivo. Feedback visual (saved/error)
  - Se status=placeholder: borda amarela de alerta
- Grupos 5-8 (sistema): cada arquivo mostra nome, propósito, owner badge "agente" ou "genótipo"
  - Ao expandir: `<pre>` read-only com conteúdo atual (sem exemplo — o conteúdo É o estado real)
  - Para diretórios (blog/entries/, reports/, threads/): mostrar contagem + últimos 5 nomes
- Responsivo: painéis empilhados em mobile

### US-3: Rota Flask `/setup` + registrar no app
**Como** servidor Flask, **quero** servir a tab setup.

**Acceptance Criteria:**
- GET `/setup` renderiza `setup.html` com `tab='setup'`
- Renderização server-side (Python lê arquivos, passa pro template — mais simples que fetch API)
- Tab "setup" adicionada ao `base.html`
- Registrar rota no app.py

### US-4: Exemplos preenchidos (editáveis) + descrições (sistema)
**Como** operador novo, **quero** ver exemplos realistas dos arquivos que devo editar e descrições claras dos que o agente gerencia.

**Acceptance Criteria:**
- Arquivos editáveis (grupos 1-4): exemplo preenchido com dados fictícios de um agente "atlas" no domínio "edtech" (agent_name="atlas", skill_prefix="atlas", blog_port=8080, domain="edtech")
- Arquivos de sistema (grupos 5-8): sem exemplo. Descrição de 1-2 frases explicando o que o agente coloca ali e quando
- Tudo em `blog/setup_examples.py` como dicionário Python
- Cada entry: `{path, example_content (ou None pra sistema), description}`

### US-5: Chat com pin (substituir insights.md)
**Como** operador, **quero** pinar mensagens no chat para que persistam como direção ao agente, **para** ter um canal único (chat) com dois níveis (transacional + direcional).

**Acceptance Criteria:**
- Cada mensagem no chat tem botão "pin" (toggle)
- POST `/api/chat` com `{action: "pin", id: MSG_ID}` e `{action: "unpin", id: MSG_ID}`
- Mensagens pinadas: campo `pinned: true` no JSON, NÃO são marcadas como `processed`
- GET `/api/chat?pinned=true` retorna só as pinadas (para o pre-skill.md consumir)
- No template do chat: mensagens pinadas ficam no topo, visual diferenciado (borda ou ícone)
- pre-skill.md.tpl atualizado: lê pinned messages via curl em vez de `cat insights.md`
- Heartbeat e carregar leem pinned messages em vez de insights.md

## Escopo

**DENTRO:**
- Nova tab setup com 8 grupos de arquivos
- Arquivos editáveis (grupos 1-4): textarea + save + exemplo preenchido
- Arquivos de sistema (grupos 5-8): read-only + descrição
- Status badges (configured/placeholder/missing) + owner badges (humano/agente/genótipo)
- Backup antes de salvar

**FORA:**
- Validação de conteúdo (v2 — ex: verificar YAML válido)
- Wizard step-by-step (v2)
- Diff visual entre atual e exemplo (v2)
- Renomear "blog" no código Python (cosmético, não funcional)

## Plano de Execução

| US | Dependência | Estimativa |
|----|-------------|------------|
| US-4 | nenhuma | ~20min (exemplos editáveis + descrições sistema) |
| US-1 | US-4 | ~15min (endpoints GET + POST com backup) |
| US-3 | US-1 | ~5min (rota + tab no base.html) |
| US-2 | US-1, US-3 | ~20min (template HTML + CSS: textarea vs pre, save) |
| US-5 | nenhuma | ~15min (pin no chat API + UI + pre-skill.md.tpl) |

### US-6: secrets/MANIFEST.md + config/features.yaml
**Como** operador, **quero** ver quais secrets habilitam quais capabilities e controlar o que está ligado, **para** ter visibilidade e controle sobre o que o agente pode fazer.

**Acceptance Criteria:**

**MANIFEST.md** (genótipo — read-only, vem com o repo):
- Uma tabela por tier (core, recomendado, opcional)
- Cada secret tem: nome, serviço, o que habilita, o que degrada sem ele, custo
- Tiers:
  - **Core:** ANTHROPIC_API_KEY (sem ele nada roda)
  - **Recomendado:** OPENAI_API_KEY (review adversarial, deepresearch), EXA_API_KEY (busca)
  - **Opcional:** XAI_API_KEY (provider alternativo), GOOGLE_API_KEY (Gemini deepresearch), GITHUB_PAT (push autônomo), SERPER_API_KEY (busca web), SLACK_BOT_TOKEN (notificações ricas), TELEGRAM_BOT_TOKEN (alertas), CLOUDFLARE_API_TOKEN (deploy)

**features.yaml** (fenótipo — editável pelo humano):
```yaml
review:
  adversarial: auto       # edge-consult (precisa: OPENAI_API_KEY)
  review_gate: auto       # LLM-as-judge no pipeline (precisa: OPENAI_API_KEY)

search:
  exa: auto               # busca via Exa (precisa: EXA_API_KEY)
  serper: auto             # busca web via Serper (precisa: SERPER_API_KEY)

research:
  deep: auto              # edge-deepresearch (precisa: OPENAI + GOOGLE)
  adversarial: auto       # cross-provider validation (precisa: 2+ providers)

notifications:
  slack:
    enabled: auto         # auto = enabled if bot_token in secrets
    channels:
      heartbeat: ""       # Channel ID — onde o heartbeat reporta
      alerts: ""          # Channel ID — erros e alertas críticos
      reports: ""         # Channel ID — entrega de relatórios
      default: ""         # Channel ID — fallback pra tudo
  telegram:
    enabled: auto         # auto = enabled if bot_token in secrets

git:
  auto_push: false        # push autônomo — opt-in explícito
  auto_pr: false          # criar PRs — opt-in explícito

blog:
  auth: auto              # autenticação no blog (precisa: BLOG_AUTH_USER)
  public: false           # expor na rede — opt-in explícito

heartbeat:
  enabled: true
  interval: "2h"
```
- `auto` = detecta se o secret correspondente existe em _shared.yaml. Resolve pra true/false em runtime
- `true`/`false` = override manual
- features.yaml adicionado ao grupo 4 (Infra) dos editáveis no setup tab
- Template: `config/features.yaml.tpl` com defaults seguros (tudo auto, git/public false)

**No setup tab:**
- MANIFEST.md no grupo 8 (protocolos, read-only) com status ao vivo por secret (verde=configurado, vermelho=missing)
- features.yaml no grupo 4 (infra, editável) — idealmente com toggles visuais em vez de textarea

### US-7: Slack nativo com roteamento por canal
**Como** agente, **quero** enviar notificações para canais Slack específicos conforme o tipo, **para** o operador receber heartbeats, alertas e relatórios nos canais certos.

**Acceptance Criteria:**

**secrets/_shared.template.yaml** — expandir seção slack:
```yaml
communication:
  slack:
    bot_token: ""          # xoxb-... (Slack Bot Token — DMs, upload, threading)
    app_token: ""          # xapp-... (Socket Mode, opcional)
    webhook_url: ""        # fallback simples se não tiver bot token
```

**Roteamento (lê de features.yaml):**
- Se `notifications.slack.enabled` = true e bot_token presente:
  - Heartbeat → canal `channels.heartbeat` (ou `channels.default`)
  - Erros/alertas → canal `channels.alerts` (ou `channels.default`)
  - Relatórios → upload no canal `channels.reports` (ou `channels.default`)
  - Sem canal configurado → skip silencioso com log
- Se só webhook_url presente (sem bot_token):
  - Tudo vai pro webhook (texto simples, sem threading, sem upload)

**post-skill.md** atualizado:
- Em vez de `curl ${SLACK_WEBHOOK_URL}` hardcoded, ler features.yaml e rotear
- Helper script `tools/notify.sh` que abstrai: `notify "heartbeat" "mensagem"` → resolve canal + método (bot vs webhook)

**blog/app.py** — endpoint de status:
- GET `/api/setup/secrets-status` retorna status de cada secret (present/missing) sem expor valores
- Setup tab usa isso pra colorir o MANIFEST

## Plano de Execução

| US | Dependência | Estimativa |
|----|-------------|------------|
| US-4 | nenhuma | ~20min (exemplos editáveis + descrições sistema) |
| US-6 | nenhuma | ~15min (MANIFEST.md + features.yaml + template) |
| US-1 | US-4, US-6 | ~15min (endpoints GET + POST + secrets-status) |
| US-3 | US-1 | ~5min (rota + tab no base.html) |
| US-2 | US-1, US-3 | ~20min (template HTML + CSS) |
| US-5 | nenhuma | ~15min (chat pin API + UI + pre-skill.md.tpl) |
| US-7 | US-6 | ~15min (notify.sh + post-skill.md + _shared.template) |

Ordem: US-6 → US-4 → US-1 → US-3 → US-2 (tab setup) | US-5 (chat pin) | US-7 (slack, paralelo com US-5)

## Riscos

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| Arquivos não existem no repo template | Baixa | Fallback: mostrar "não instalado" |
| CSS conflita com dashboard existente | Baixa | Classes prefixadas `setup-*` |
| Exemplos ficam desatualizados vs templates | Média | Review na reflexão — exemplos são estáticos |
