# REPLICATION BLUEPRINT — Agente edge-of-chaos
> Produzido pela Sessao 2 de investigacao
> Data: 2026-03-15
> Baseado em: AGENT_INVENTORY.md (Sessao 1)

---

## PARTE 1 — O QUE ESTE AGENTE FAZ

### 1.1 Missao e Identidade

O agente **aeita** (codename **edge-of-chaos**) e um agente autonomo de IA que opera "na fronteira do caos — onde ordem encontra complexidade e coisas interessantes emergem". Ele foi construido sobre o Claude Code CLI da Anthropic e funciona como um pesquisador/pensador autonomo que acorda a cada 2 horas via systemd timer, avalia o contexto (sessoes do usuario, erros pendentes, fios de investigacao), e despacha uma skill apropriada — pesquisa, descoberta, lazer criativo, reflexao, estrategia, ou execucao.

O agente segue o Metodo Feynman como principio operacional: derivar antes de pesquisar, mostrar o processo de pensamento (nao conclusoes), gaps emergem inline quando o raciocinio atinge um muro. O tom e explorador, nunca didatico. A honestidade intelectual e absoluta — admitir erro sem defender, desafiar consenso, pushback sem convite.

O agente tem uma personalidade codificada: analitico, busca elegancia e simplicidade, prefere entender antes de agir, YAGNI como instinto. Ele opera como mentor por default (executa apenas quando expressamente pedido), usa primeira pessoa sempre ("eu fiz", "eu nao sei"), e tem um blog interno como canal primario de comunicacao. Toda producao intelectual e publicada no blog — insights, pesquisas, descobertas, reflexoes.

Um aspecto central e o uso de modelos concorrentes (GPT-5.4, Grok) como revisores adversariais do output do Claude. O agente host (Claude) nunca avalia a si mesmo — sempre submete conclusoes a um segundo modelo via `edge-consult` antes de publicar. Isso cria um adversarial review loop que aumenta a qualidade e reduz vieses.

O idioma padrao e Portugues (BR) com acentuacao obrigatoria.

### 1.2 Arquitetura em Uma Frase

Agente autonomo baseado em Claude Code que acorda a cada 2h via systemd timer, despacha skills de pesquisa/exploracao/reflexao, publica resultados num blog interno via pipeline de 8 fases com quality gates automaticos (LLM-as-judge + adversarial cross-model review), e mantém estado persistente via memoria distribuida (regras, topics, claims, threads, events JSONL).

### 1.3 Fluxo Operacional (Diagrama Mermaid)

```mermaid
flowchart TD
    A["Timer systemd (2h)"] --> B["heartbeat.sh (lock + wrapper)"]
    B --> C["claude -p '/aeita-heartbeat' --max-turns 30"]
    C --> D["Passo 0: heartbeat-preflight.sh (determinístico, 0 tokens)"]
    D -->|PREFLIGHT_CLEAN| E["Despachar /aeita-lazer ou /aeita-descoberta"]
    D -->|PREFLIGHT_WORK| F["Passo 1: Olhar (ler sessoes, chat, insights, debugging, threads, tasks)"]
    F --> G["Passo 1.5: Classificar beat (WORK ou EXPLORE)"]
    G --> H["Passo 2: edge-consult sanity check da decisao"]
    H --> I["Despachar UMA skill"]
    I --> J["Skill executa: pesquisa + edge-consult adversarial"]
    J --> K["Gerar YAML spec + review-gate (LLM-as-judge)"]
    K --> L["Escrever blog entry com claims + threads"]
    L --> M["consolidar-estado (8 fases)"]
    M --> N["Phase 0a: state snapshot PRE"]
    N --> O["Phase 0.3: adversarial review gate"]
    O --> P["Phase 0.5: review-gate LLM-as-judge"]
    P --> Q["Phase 1-3: blog publish + HTML report + verificacao"]
    Q --> R["Phase 4: meta-report (state delta + scratchpad)"]
    R --> S["Phase 5: state commit (claims, threads, events, digest)"]
    S --> T["Phase 5b: state audit (PRE vs POST)"]
    T --> U["Phase 6: diffs + git commit estruturado"]
    U --> V["Passo 3: Registrar (log, responder chat, debugging)"]
    V --> W["edge-skill-step end (detectar steps pulados)"]
    E --> J
```

---

## PARTE 2 — COMPONENTES E SEUS PAPEIS

### 2.1 Nucleo (obrigatorio para qualquer replicacao)

| Componente | Arquivo(s) | Papel | Customizacao necessaria |
|------------|-----------|-------|------------------------|
| Instrucoes globais | `templates/CLAUDE.md.template` | Define identidade, memoria, metodo, skills, preferencias | Substituir `{{AGENT_NAME}}`, `{{CODENAME}}`, `{{BIO}}`, `{{DOMAIN}}`, `{{WORK_DIR}}`, `{{PREFIX}}` |
| CLAUDE.md user-level | `~/.claude/CLAUDE.md` | Instrucoes instanciadas para o agente especifico | Gerar a partir do template |
| Memoria persistente | `memory/MEMORY.md.template` | Schema de memoria auto-atualizada | Substituir placeholders, popular com contexto |
| Personalidade | `memory/personality.md` | Perfil cognitivo, estilo de comunicacao, valores | Adaptar personalidade ao novo agente |
| Regras core | `memory/rules-core.md` | Max 15 regras cross-cutting, sempre carregadas | Manter estrutura, adaptar conteudo |
| Metodo | `memory/metodo.md` | Metodo Feynman — como abordar problemas | Reutilizavel sem mudanca |
| Knowledge design | `memory/knowledge-design.md` | Arquitetura de clusters de conhecimento | Reutilizavel sem mudanca |
| Debugging log | `memory/debugging.md` | Log de erros para nao repetir | Iniciar vazio |
| Heartbeat script | `templates/heartbeat.sh.template` | Wrapper para systemd: lock, log, invoca Claude | Substituir `{{WORK_DIR}}`, `{{PREFIX}}` |
| Heartbeat timer | `systemd/claude-heartbeat.timer` | Timer systemd a cada 2h | Ajustar frequencia se necessario |
| Heartbeat service | `systemd/claude-heartbeat.service` | Unidade oneshot que executa o heartbeat | Ajustar paths |
| Skill heartbeat | `skills/aeita-heartbeat/SKILL.md` | Dispatcher autonomo: olhar, decidir, despachar | Adaptar nome da skill, prefixo |
| State protocol | `skills/_shared/state-protocol.md` | Protocolo de gestao de estado entre skills | Ajustar paths de arquivos protegidos |
| Report template | `skills/_shared/report-template.md` | Template compartilhado de relatorios | Reutilizavel, ajustar nome do skill prefix |

### 2.2 Ferramentas (mapa completo)

### edge-fontes
- **Proposito:** Busca unificada em fontes externas (Exa, arXiv, HN, X)
- **Tipo:** busca
- **Inputs:** query, flags (--front-page, filtros de dominio)
- **Outputs:** resultados curados por sinal (engagement, relevancia)
- **APIs externas:** EXA_API_KEY, arXiv API (publica), HN Algolia (publica)
- **Chamada por:** skills (pesquisa, descoberta, lazer, fontes), heartbeat (serendipity scan)
- **Obrigatoria para replicar?** Sim — e o ponto de entrada para informacao externa. Sem ela, o agente fica cego ao mundo.

### edge-consult / edge-consult.py
- **Proposito:** Revisao adversarial cross-model. Encontra furos, steelmans o oposto, detecta vieses.
- **Tipo:** LLM-as-judge
- **Inputs:** texto com conclusoes/analise, --context com arquivos, --mode (adversarial/collab), --model (gpt-*/grok-*)
- **Outputs:** critica estruturada ou sugestoes colaborativas
- **APIs externas:** OPENAI_API_KEY, XAI_API_KEY
- **Chamada por:** TODA skill (obrigatorio antes de publicar), heartbeat (sanity check da decisao)
- **Obrigatoria para replicar?** Sim — e o mecanismo central de qualidade. Sem adversarial review, o agente perde o check de vieses.

### edge-state-audit
- **Proposito:** Snapshot, propor e auditar mudancas de estado em arquivos protegidos
- **Tipo:** estado
- **Inputs:** --slug, modos: snapshot (SHA256 PRE), propose (YAML de mudancas), audit (comparar PRE vs POST)
- **Outputs:** YAML com resultado da auditoria (ok/partial/divergencia/violacao)
- **APIs externas:** nenhuma
- **Chamada por:** consolidar-estado (Phase 0a, 5b), skills com mudanca de estado
- **Obrigatoria para replicar?** Sim — garante que mudancas de estado sao declaradas e auditadas

### edge-state-lint
- **Proposito:** Linter de consistencia de estado. Detecta drift entre arquivos de memoria.
- **Tipo:** estado
- **Inputs:** arquivos de memoria
- **Outputs:** gaps, threads inconsistentes, referencias quebradas, breaks stale
- **APIs externas:** nenhuma
- **Chamada por:** agente autonomo, reflexao
- **Obrigatoria para replicar?** Sim — detecta degradacao silenciosa do estado

### edge-digest
- **Proposito:** Gera briefing.md a partir de dados estruturados. Deterministico. Zero tokens.
- **Tipo:** utilitario
- **Inputs:** events.jsonl, threads/*.md, claims abertas, ultimos beats, erros ativos
- **Outputs:** ~/edge/briefing.md (estado compactado)
- **APIs externas:** nenhuma
- **Chamada por:** consolidar-estado (Phase 5), heartbeat (leitura de contexto)
- **Obrigatoria para replicar?** Sim — resume o estado sem gastar tokens

### edge-claims
- **Proposito:** Buscar e listar claims extraidas de artefatos (conhecimento duravel)
- **Tipo:** busca
- **Inputs:** --thread, --open (gaps), --search, --stats
- **Outputs:** lista de claims verificadas e gaps abertos (prefixo `!`)
- **APIs externas:** nenhuma
- **Chamada por:** heartbeat (para informar decisao), skills
- **Obrigatoria para replicar?** Sim — claims sao o conhecimento destilado do agente

### edge-task
- **Proposito:** Task ledger CLI. Event-sourced, append-only JSONL + snapshot materializado.
- **Tipo:** estado
- **Inputs:** add, update, block, done, drop, list, show, stats
- **Outputs:** estado das tasks (doing, blocked, stale, todo)
- **APIs externas:** nenhuma
- **Chamada por:** heartbeat (Passo 1f, 3d), usuario
- **Obrigatoria para replicar?** Sim — tracking de trabalho do agente

### edge-event
- **Proposito:** Log e consulta de eventos de estado do sistema
- **Tipo:** estado
- **Inputs:** log (tipo, sumario, skill, thread, artifacts), recent, stats
- **Outputs:** eventos estruturados em events.jsonl
- **APIs externas:** nenhuma
- **Chamada por:** heartbeat (Passo 3e), consolidar-estado
- **Obrigatoria para replicar?** Sim — telemetria operacional

### edge-scratch
- **Proposito:** Scratchpad de sessao para observacoes mid-sessao
- **Tipo:** utilitario
- **Inputs:** add, show, path, list
- **Outputs:** arquivo temporario /tmp/edge-scratch-*.md
- **APIs externas:** nenhuma
- **Chamada por:** todas as skills (acumular observacoes)
- **Obrigatoria para replicar?** Sim — alimenta o meta-report

### edge-meta-report
- **Proposito:** Gera meta-report para mudancas de estado. Captura state delta, le scratchpad, roda desafio adversarial.
- **Tipo:** publicacao
- **Inputs:** slug, scratchpad, state delta
- **Outputs:** ~/edge/meta-reports/{slug}-meta.md
- **APIs externas:** nenhuma (usa edge-consult internamente)
- **Chamada por:** consolidar-estado (Phase 4)
- **Obrigatoria para replicar?** Sim — espelho cognitivo de cada publicacao

### edge-skill-step
- **Proposito:** Rastrear execucao de passos de skills. Detecta passos silenciosamente pulados.
- **Tipo:** utilitario
- **Inputs:** skill, step_id, skip (com razao), end (gera report)
- **Outputs:** report de steps executados vs registry
- **APIs externas:** nenhuma
- **Chamada por:** todas as skills (obrigatorio chamar `end`)
- **Obrigatoria para replicar?** Sim — detecta degradacao de execucao

### review-gate.py
- **Proposito:** Quality gate para YAML specs. Pipeline de 3 fases: co-author (GPT + tools) → reviewer (avalia cego) → refiner (aplica feedback). 2 rounds.
- **Tipo:** LLM-as-judge
- **Inputs:** YAML spec, --skill
- **Outputs:** YAML melhorado, score em 6 dimensoes (threshold 3.5/5)
- **APIs externas:** OPENAI_API_KEY
- **Chamada por:** consolidar-estado (Phase 0.5), skills (antes de publicar)
- **Obrigatoria para replicar?** Sim — quality gate automatico. Sem ele, qualidade cai silenciosamente.

### consolidar-estado
- **Proposito:** Pipeline completo de 8 fases: publicacao atomica (blog + report + meta-report + state commit + git)
- **Tipo:** publicacao + estado
- **Inputs:** blog entry .md, YAML spec (opcional)
- **Outputs:** entry publicada, HTML report, meta-report, claims/threads/events atualizados, git commit estruturado
- **APIs externas:** BLOG_PORT, BLOG_AUTH_USER, BLOG_AUTH_PASS (blog server)
- **Chamada por:** todas as skills de producao
- **Obrigatoria para replicar?** Sim — e O pipeline. Sem ele, publicacao e estado ficam dessincronizados.

### heartbeat-preflight.sh
- **Proposito:** Checagem deterministica antes de invocar LLM. Zero tokens. ~3 segundos.
- **Tipo:** utilitario
- **Inputs:** estado local (chat, events, threads, debugging, breaks, tasks)
- **Outputs:** PREFLIGHT_CLEAN ou PREFLIGHT_WORK com sinais detectados
- **APIs externas:** localhost:8766 (blog server chat API)
- **Chamada por:** heartbeat (Passo 0)
- **Obrigatoria para replicar?** Sim — evita gastar tokens quando nao ha trabalho urgente

### edge-hn
- **Proposito:** Busca inteligente no Hacker News via Algolia API
- **Tipo:** busca
- **Inputs:** query, --comments, --min-points, --days, --front-page
- **Outputs:** resultados filtrados por qualidade
- **APIs externas:** HN Algolia (publica)
- **Chamada por:** edge-fontes, usuario
- **Obrigatoria para replicar?** Opcional — util para pesquisa tech, mas substituivel

### edge-x
- **Proposito:** Busca inteligente no X/Twitter para insights de practitioners
- **Tipo:** busca
- **Inputs:** query, --max, --json
- **Outputs:** tweets filtrados por qualidade/engagement
- **APIs externas:** X_BEARER_TOKEN + credenciais X API
- **Chamada por:** heartbeat (serendipity scan), edge-fontes
- **Obrigatoria para replicar?** Opcional — requer API do X (paga). Substituivel por outras fontes.

### edge-dialogue.py
- **Proposito:** Dialogo multi-turno com modelos GPT via Responses API
- **Tipo:** LLM-as-judge
- **Inputs:** prompt, --model
- **Outputs:** conversa logada em ~/edge/logs/dialogue/
- **APIs externas:** OPENAI_API_KEY
- **Chamada por:** usuario
- **Obrigatoria para replicar?** Opcional — util para deliberacao profunda, nao critico

### edge-ledger
- **Proposito:** Telemetria de execucao. Registra cada tentativa de tool como evento estruturado.
- **Tipo:** estado
- **Inputs:** record, query, stats
- **Outputs:** execution-ledger.jsonl
- **APIs externas:** nenhuma
- **Chamada por:** agente (automatico)
- **Obrigatoria para replicar?** Opcional — util para diagnostico, nao critico

### ledger_rollup.py
- **Proposito:** Agrega execution ledger em ops-hotspots.json (incidents, top_pain, recovered_but_unstable)
- **Tipo:** utilitario
- **Inputs:** execution-ledger.jsonl, debugging.md
- **Outputs:** ops-hotspots.json
- **APIs externas:** nenhuma
- **Chamada por:** reflexao
- **Obrigatoria para replicar?** Opcional — analise pos-hoc

### curadoria_compute.py
- **Proposito:** Motor de curadoria de corpus. Self-probes, clustering, classificacao.
- **Tipo:** utilitario
- **Inputs:** modos: stats, lite, full
- **Outputs:** curadoria-candidates.json
- **APIs externas:** nenhuma (usa edge-search internamente)
- **Chamada por:** skill curadoria-corpus
- **Obrigatoria para replicar?** Opcional — util quando corpus cresce. Nao necessario no inicio.

### git_signals.py
- **Proposito:** Extrair sinais estruturados do git log para reflexao
- **Tipo:** utilitario
- **Inputs:** git log
- **Outputs:** git-signals.json (fix chains, duplicate slugs, pipeline failures)
- **APIs externas:** nenhuma
- **Chamada por:** reflexao
- **Obrigatoria para replicar?** Opcional — enriquece reflexao, nao critico

### generate_report.py
- **Proposito:** Gera HTML autocontido a partir de YAML spec
- **Tipo:** publicacao
- **Inputs:** YAML spec ou HTML cru
- **Outputs:** ~/edge/reports/relatorio.html
- **APIs externas:** nenhuma
- **Chamada por:** consolidar-estado (Phase 2). NUNCA chamar diretamente.
- **Obrigatoria para replicar?** Sim — parte do pipeline de publicacao

### yaml_to_html.py
- **Proposito:** Converte YAML estruturado para HTML (conteudo do `<main>`)
- **Tipo:** publicacao
- **Inputs:** YAML com sections e blocks
- **Outputs:** HTML do corpo do report
- **APIs externas:** nenhuma
- **Chamada por:** generate_report.py
- **Obrigatoria para replicar?** Sim — parte do pipeline de publicacao

### validate_svg.py
- **Proposito:** Validar elementos SVG dentro de HTML reports
- **Tipo:** utilitario
- **Inputs:** arquivo HTML
- **Outputs:** erros de SVG (XML, viewBox, dimensoes, elementos visiveis)
- **APIs externas:** nenhuma
- **Chamada por:** validacao pos-publicacao
- **Obrigatoria para replicar?** Opcional — qualidade visual

### edge-search / edge-index
- **Proposito:** Busca hibrida (FTS5 + vector) e indexacao no corpus local
- **Tipo:** busca
- **Inputs:** query, -k (top results)
- **Outputs:** resultados rankeados do corpus local
- **APIs externas:** nenhuma (SQLite local)
- **Chamada por:** heartbeat (corpus check), skills, review-gate
- **Obrigatoria para replicar?** Sim — evita redescobrir temas. Essencial quando corpus cresce.

### 2.3 Skills Claude Code (mapa completo)

| Skill | Proposito | Trigger | Despachada por Heartbeat? |
|-------|----------|---------|---------------------------|
| `aeita-heartbeat` | Dispatcher autonomo: olhar, decidir, despachar | Timer systemd (2h) | N/A (e o proprio heartbeat) |
| `aeita-pesquisa` | Pesquisa profunda sobre tema especifico | Heartbeat ou usuario | Sim |
| `aeita-descoberta` | Exploracao lateral, conexoes inesperadas | Heartbeat | Sim |
| `aeita-lazer` | Break criativo: builds, derivacoes, haikus | Heartbeat | Sim |
| `aeita-reflexao` | Auto-reflexao, processar feedback, atualizar CLAUDE.md | Heartbeat (cada ~5 beats) | Sim |
| `aeita-estrategia` | Planejamento estrategico, avaliacao de prioridades | Heartbeat (cada ~5 beats) | Sim |
| `aeita-planejar` | Transformar insights em propostas concretas | Heartbeat | Sim |
| `aeita-executar` | Implementar mudancas em projetos | NUNCA por heartbeat, so usuario | Nao |
| `aeita-blog` | Criar blog entry | Skills de producao | Nao (sub-skill) |
| `aeita-relatorio` | Gerar relatorio HTML | Skills de producao | Nao (sub-skill) |
| `aeita-fontes` | Buscar fontes externas | Skills de producao | Nao (sub-skill) |
| `aeita-contexto` | Sintetizar estado atual do trabalho | Skills (passo preparatorio) | Nao (sub-skill) |
| `aeita-carregar` | Carregar contexto/estado | Inicio de sessao | Nao |
| `aeita-estado` | Gerenciar estado do agente | Skills | Nao (sub-skill) |
| `aeita-salvar-estado` | Salvar estado persistente | Skills | Nao (sub-skill) |
| `aeita-autonomia` | Expandir capacidades autonomas | Heartbeat ou usuario | Sim (raro) |
| `aeita-curadoria-corpus` | Curadoria do corpus de conhecimento | Heartbeat (periodico) | Sim (raro) |
| `aeita-experimento` | Rodar experimentos | Heartbeat ou usuario | Sim |
| `aeita-log` | Logging de atividades | Skills | Nao (sub-skill) |
| `aeita-mapa` | Mind mapping | Usuario | Nao |
| `aeita-prd` | Product Requirements Document | Usuario | Nao |
| `aeita-prototipo` | Prototipagem rapida | Usuario | Nao |

### 2.4 Plugins Claude Code (relevantes)

| Plugin | Papel |
|--------|-------|
| `learning-output-style` | Hook SessionStart que injeta modo de aprendizado interativo |
| `security-guidance` | Hook PreToolUse (Edit/Write) que detecta padroes inseguros |
| `feature-dev` | 7-phase feature development com sub-agentes (code-reviewer, code-architect) |
| `claude-md-management` | Comando /revise-claude-md para atualizar CLAUDE.md com learnings |
| `pr-review-toolkit` | Agente silent-failure-hunter para audit de error handling |

---

## PARTE 3 — CHECKLIST DE INSTALACAO

### 3.1 Pre-requisitos de Sistema

- [ ] Claude Code CLI instalado (`claude --version` >= 2.1.x)
- [ ] Node.js >= 22.x (para Claude Code)
- [ ] Python >= 3.10 com pip e venv
- [ ] GitHub CLI instalado e autenticado (`gh auth status`)
- [ ] Git configurado
- [ ] systemd disponivel (Linux) — ou launchd (macOS) — ou Task Scheduler (Windows)
- [ ] curl disponivel
- [ ] Blog server Python (Flask/similar) — ver secao 5.1
- [ ] SQLite com extensao FTS5 (para edge-search)
- [ ] Acesso a internet (para APIs externas)

### 3.2 API Keys Necessarias

| Variavel | Servico | Obrigatoria? | Onde obter | Usada por |
|----------|---------|--------------|------------|-----------|
| `ANTHROPIC_API_KEY` | Anthropic | Sim | console.anthropic.com | Claude Code (agente host) |
| `OPENAI_API_KEY` | OpenAI | Sim | platform.openai.com | review-gate, edge-consult, edge-dialogue |
| `EXA_API_KEY` | Exa.ai | Sim | exa.ai | edge-fontes (busca web) |
| `XAI_API_KEY` | xAI | Opcional | x.ai | edge-consult (modelo Grok alternativo) |
| `X_BEARER_TOKEN` | X/Twitter | Opcional | developer.x.com | edge-x (busca X) |
| `X_API_KEY` | X/Twitter | Opcional | developer.x.com | edge-x |
| `X_API_SECRET` | X/Twitter | Opcional | developer.x.com | edge-x |
| `X_ACCESS_TOKEN` | X/Twitter | Opcional | developer.x.com | edge-x |
| `X_ACCESS_TOKEN_SECRET` | X/Twitter | Opcional | developer.x.com | edge-x |
| `BLOG_PORT` | Blog server | Sim | Configuracao local | consolidar-estado |
| `BLOG_AUTH_USER` | Blog server | Sim | Configuracao local | consolidar-estado |
| `BLOG_AUTH_PASS` | Blog server | Sim | Configuracao local | consolidar-estado |

### 3.3 Dependencias Python

```
PyYAML>=6.0
requests>=2.28
tweepy>=4.14       # opcional: so se usar edge-x
openai>=1.0        # obrigatorio: review-gate, edge-consult
# sqlite-vec       # opcional: busca vetorial
# exa-py           # opcional: se usar Exa SDK
```

### 3.4 Arquivos a Copiar para Novo Repositorio

```bash
# Estrutura minima de diretorios
mkdir -p .claude/skills/_shared
mkdir -p .claude/skills/{PREFIX}-heartbeat
mkdir -p .claude/skills/{PREFIX}-pesquisa
mkdir -p .claude/skills/{PREFIX}-descoberta
mkdir -p .claude/skills/{PREFIX}-lazer
mkdir -p .claude/skills/{PREFIX}-reflexao
mkdir -p .claude/skills/{PREFIX}-estrategia
mkdir -p .claude/skills/{PREFIX}-planejar
mkdir -p .claude/skills/{PREFIX}-executar
mkdir -p .claude/skills/{PREFIX}-blog
mkdir -p .claude/skills/{PREFIX}-relatorio
mkdir -p .claude/skills/{PREFIX}-fontes
mkdir -p .claude/skills/{PREFIX}-contexto
mkdir -p .claude/skills/{PREFIX}-estado
mkdir -p .claude/skills/{PREFIX}-salvar-estado
mkdir -p .claude/skills/{PREFIX}-autonomia
mkdir -p .claude/skills/{PREFIX}-curadoria-corpus
mkdir -p .claude/skills/{PREFIX}-experimento
mkdir -p .claude/skills/{PREFIX}-log
mkdir -p memory/topics
mkdir -p tools
mkdir -p systemd
mkdir -p templates
mkdir -p secrets
mkdir -p blog/entries
mkdir -p reports
mkdir -p meta-reports
mkdir -p logs
mkdir -p notes
mkdir -p threads
mkdir -p state
mkdir -p state-snapshots
mkdir -p builds
mkdir -p lab
mkdir -p autonomy

# Nucleo — copiar e editar
cp templates/CLAUDE.md.template novo-repo/CLAUDE.md           # EDITAR placeholders
cp memory/MEMORY.md.template novo-repo/memory/MEMORY.md       # EDITAR placeholders
cp templates/heartbeat.sh.template novo-repo/heartbeat.sh     # EDITAR placeholders
cp memory/personality.md novo-repo/memory/personality.md       # EDITAR personalidade
cp memory/rules-core.md novo-repo/memory/rules-core.md        # EDITAR regras
cp memory/metodo.md novo-repo/memory/metodo.md                # REUTILIZAR
cp memory/knowledge-design.md novo-repo/memory/knowledge-design.md  # REUTILIZAR
cp memory/debugging.md novo-repo/memory/debugging.md          # INICIAR VAZIO

# Skills compartilhadas
cp skills/_shared/state-protocol.md novo-repo/.claude/skills/_shared/
cp skills/_shared/report-template.md novo-repo/.claude/skills/_shared/

# Todas as skills (copiar SKILL.md de cada uma e adaptar)
# [ver lista na secao 2.3]

# Ferramentas obrigatorias
cp tools/edge-fontes novo-repo/tools/
cp tools/edge-consult.py novo-repo/tools/
cp tools/edge-state-audit novo-repo/tools/
cp tools/edge-state-lint novo-repo/tools/
cp tools/edge-digest novo-repo/tools/
cp tools/edge-claims novo-repo/tools/
cp tools/edge-task novo-repo/tools/
cp tools/edge-event novo-repo/tools/
cp tools/edge-scratch novo-repo/tools/
cp tools/edge-meta-report novo-repo/tools/
cp tools/edge-skill-step novo-repo/tools/
cp tools/review-gate.py novo-repo/tools/
cp tools/generate_report.py novo-repo/tools/
cp tools/yaml_to_html.py novo-repo/tools/
cp tools/heartbeat-preflight.sh novo-repo/tools/
cp tools/skill-steps-registry.yaml novo-repo/tools/
cp tools/assets/base.css novo-repo/tools/assets/
cp tools/assets/logo.svg novo-repo/tools/assets/

# Pipeline principal
cp bin/consolidar-estado novo-repo/bin/

# Ferramentas opcionais
cp tools/edge-hn novo-repo/tools/          # HN search
cp tools/edge-x novo-repo/tools/            # X/Twitter search
cp tools/edge-dialogue.py novo-repo/tools/  # Multi-turn dialogue
cp tools/edge-ledger novo-repo/tools/       # Telemetria
cp tools/ledger_rollup.py novo-repo/tools/  # Agregacao
cp tools/curadoria_compute.py novo-repo/tools/  # Curadoria corpus
cp tools/git_signals.py novo-repo/tools/    # Git signals
cp tools/validate_svg.py novo-repo/tools/   # SVG validation

# systemd
cp systemd/claude-heartbeat.service novo-repo/systemd/
cp systemd/claude-heartbeat.timer novo-repo/systemd/
cp systemd/blog-server.service novo-repo/systemd/

# Templates cross-platform
cp templates/heartbeat.ps1.template novo-repo/templates/

# Env examples
cp .env.example novo-repo/
cp models.env.example novo-repo/
```

### 3.5 Sequencia de Configuracao

1. [ ] Criar/clonar repositorio do novo agente
2. [ ] Copiar arquivos do nucleo (secao 3.4)
3. [ ] Editar CLAUDE.md — substituir todos os `{{placeholders}}`
4. [ ] Editar memory/MEMORY.md — substituir placeholders, definir identidade
5. [ ] Editar memory/personality.md — definir perfil cognitivo do novo agente
6. [ ] Editar memory/rules-core.md — adaptar regras ao novo dominio
7. [ ] Criar `~/edge/secrets/` com API keys:
   ```bash
   mkdir -p ~/edge/secrets && chmod 700 ~/edge/secrets
   echo "OPENAI_API_KEY=sk-..." > ~/edge/secrets/openai.env
   echo "EXA_API_KEY=..." > ~/edge/secrets/exa.env
   chmod 600 ~/edge/secrets/*.env
   ```
8. [ ] Instalar dependencias Python:
   ```bash
   cd ~/edge/tools && python3 -m venv venv
   source venv/bin/activate && pip install -r requirements.txt
   ```
9. [ ] Configurar blog server (ver secao 5.1)
10. [ ] Instalar e ativar servicos systemd:
    ```bash
    cp systemd/claude-heartbeat.service ~/.config/systemd/user/
    cp systemd/claude-heartbeat.timer ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now claude-heartbeat.timer
    ```
11. [ ] Configurar Claude Code settings:
    ```bash
    cat > ~/.claude/settings.json <<'EOF'
    {
      "permissions": {
        "allow": [
          "Bash(*)", "Read(*)", "Write(*)", "Edit(*)",
          "Glob(*)", "Grep(*)", "NotebookEdit(*)",
          "WebSearch(*)", "WebFetch(*)"
        ]
      },
      "effortLevel": "high"
    }
    EOF
    ```
12. [ ] Testar heartbeat manual:
    ```bash
    cd ~/edge && claude -p "/aeita-heartbeat" --max-turns 5
    ```
13. [ ] Verificar primeiro ciclo autonomo:
    ```bash
    systemctl --user status claude-heartbeat.timer
    tail -f ~/.claude/heartbeat-output.log
    ```

---

## PARTE 4 — TEMPLATES PRONTOS PARA USO

### 4.1 CLAUDE.md Minimo Viavel

```markdown
# {{AGENT_NAME}} — Global Instructions

> {{BIO}}

Details: `~/edge/memory/personality.md`. Visual: `~/edge/avatar/identity.md`.

## Memory

Auto-memory in `~/edge/memory/MEMORY.md`.

### Required Reading (every session)

| File | When | Contents |
|------|------|----------|
| `~/edge/memory/rules-core.md` | **Every session** | Cross-cutting rules (max 15). Always loaded. |
| `~/edge/memory/personality.md` | Every session | Identity, cognitive profile, communication style |
| `~/edge/memory/debugging.md` | Autonomous sessions | Errors that must not recur |
| `~/edge/autonomy/autonomy-policy.md` | Every session | When to execute vs ask |

### Knowledge Clusters

Topic files in `~/edge/memory/topics/` — load 2-3 relevant ones per session.
Design: `~/edge/memory/knowledge-design.md`

## Identity

**My name is {{AGENT_NAME}}.** Codename: **{{CODENAME}}**.

> {{BIO}}

## Method

File: `~/edge/memory/metodo.md`
Summary: Derive before searching. Show thinking process, not conclusions. Gaps emerge inline. Exploratory tone, not didactic.

## Skills

Skills are invoked via `/{{PREFIX}}-{name}` slash commands in Claude Code.
Shared protocols: `~/.claude/skills/_shared/`

## Blog

Internal blog at `http://localhost:{{BLOG_PORT}}/blog/`
- Entries: `~/edge/blog/entries/*.md` (markdown with YAML frontmatter)
- Chat API: `GET/POST /api/chat`
- Always blog insights — primary communication channel.

## Tools

CLI tools in `~/edge/tools/`:
- `edge-fontes` — Unified external source search (USE instead of direct WebSearch)
- `edge-consult` — Cross-model adversarial review
- `edge-state-lint` — State consistency linter
- `edge-state-audit` — State audit and snapshot
- `consolidar-estado` — 8-phase publication pipeline (THE pipeline)

## Domain

**Work domain:** {{DOMAIN}}
**Working directory:** {{WORK_DIR}}

## Preferences

- **Always use venv** for Python packages. Never `--break-system-packages`.
- **Prompts outside code** — never embed prompts in .py. Isolate in .md.
- **Execution > planning** — when action is needed, act now.
- **Blog ALWAYS** — insights must go to the blog. Primary channel.
- **Generalize > special-case** — no hard-coded behavior for specific situations.

## Pipeline consolidar-estado (MANDATORY)
1. Research and synthesize
2. edge-consult (adversarial cross-model review)
3. Generate YAML spec
4. review-gate → adjust until PASS
5. Write blog entry
6. consolidar-estado [entry.md] [spec.yaml]
7. Verify meta-report

**NEVER call generate_report.py directly.**
```

**Placeholders a substituir:**
- `{{AGENT_NAME}}` — nome do agente (ex: "aeita", "ralph")
- `{{CODENAME}}` — codename do agente (ex: "edge-of-chaos")
- `{{BIO}}` — bio em 1-2 frases
- `{{DOMAIN}}` — dominio de trabalho
- `{{WORK_DIR}}` — diretorio de trabalho (ex: `~/edge`)
- `{{PREFIX}}` — prefixo das skills (ex: "aeita")
- `{{BLOG_PORT}}` — porta do blog server (ex: 8766)

### 4.2 MEMORY.md Minimo Viavel

```markdown
# Memory — {{AGENT_NAME}}

## Agent Profile
- Name: {{AGENT_NAME}}
- Codename: {{CODENAME}}
- Domain: {{DOMAIN}}
- Language: {{LANGUAGE}}

## Required Reading (every session)
| File | When | Contents |
|------|------|----------|
| `~/edge/memory/rules-core.md` | **Every session** | Cross-cutting rules |
| `~/edge/memory/personality.md` | Every session | Identity and method |
| `~/edge/memory/debugging.md` | Autonomous sessions | Error prevention |
| `~/edge/autonomy/autonomy-policy.md` | Every session | Autonomy boundaries |

## Identity
**My name is {{AGENT_NAME}}.** Codename: **{{CODENAME}}**.
> {{BIO}}
Details: `~/edge/memory/personality.md`

## Blog
Internal blog: `http://localhost:{{BLOG_PORT}}/blog/`
Entries: `~/edge/blog/entries/*.md`
Chat: `GET/POST /api/chat`

## Debugging and Operational Patterns
Rule: save ANY error that could recur (2+ times, >5min wasted, user intervention, silent error).

## Skills Available
{{SKILL_LIST}}

## Consolidated Knowledge (update via reflection)
_(empty — populate as the agent works)_

## Active Blockers
_(none)_

## Preferences
- Always use venv for Python
- Prompts outside code (in .md files)
- Blog ALWAYS — primary communication channel
- Execution > planning
```

### 4.3 heartbeat.sh Minimo Viavel (Linux/Mac)

```bash
#!/bin/bash
# Claude Code Heartbeat — wrapper for systemd/launchd
# Runs /{{PREFIX}}-heartbeat from {{WORK_DIR}}

set -euo pipefail

LOG="$HOME/.claude/heartbeat-output.log"
LOCK="/tmp/claude-heartbeat.lock"

# Avoid overlap: if another heartbeat is running, skip
if [ -f "$LOCK" ]; then
  pid=$(cat "$LOCK" 2>/dev/null || echo "")
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "--- skipped $(date -Iseconds) (pid $pid still running) ---" >> "$LOG"
    exit 0
  fi
  rm -f "$LOCK"
fi

echo $$ > "$LOCK"
trap "rm -f $LOCK" EXIT

echo "--- heartbeat $(date -Iseconds) ---" >> "$LOG"

cd {{WORK_DIR}}

if claude -p "/{{PREFIX}}-heartbeat" \
  --max-turns 30 \
  --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*),WebSearch(*),WebFetch(*),Task(*),Skill(*)" \
  >> "$LOG" 2>&1; then
  echo "--- done $(date -Iseconds) ---" >> "$LOG"
else
  echo "--- failed $(date -Iseconds) (exit code $?) ---" >> "$LOG"
fi

# Sync RAG index (if search system is installed)
if [ -f "$HOME/edge/search/ingest.py" ]; then
  python3 "$HOME/edge/search/ingest.py" \
    "$HOME/edge/reports/" "$HOME/edge/notes/" "$HOME/edge/blog/entries/" \
    --no-embed --quiet 2>/dev/null || true
fi
```

**Substituir:** `{{WORK_DIR}}` (ex: `$HOME/edge` ou `$HOME`), `{{PREFIX}}` (ex: `aeita`).
**Tornar executavel:** `chmod +x heartbeat.sh`

### 4.4 heartbeat.ps1 Minimo Viavel (Windows)

```powershell
# Claude Code Heartbeat — Windows wrapper
# Runs /{{PREFIX}}-heartbeat from {{WORK_DIR}}

$ErrorActionPreference = "Continue"

$LogFile = Join-Path $env:USERPROFILE ".claude\heartbeat-output.log"
$LockFile = Join-Path $env:TEMP "claude-heartbeat.lock"

# Avoid overlap: if another heartbeat is running, skip
if (Test-Path $LockFile) {
    $lockContent = Get-Content $LockFile -ErrorAction SilentlyContinue
    if ($lockContent) {
        try {
            $proc = Get-Process -Id ([int]$lockContent) -ErrorAction Stop
            if ($proc -and -not $proc.HasExited) {
                $ts = Get-Date -Format "o"
                Add-Content $LogFile "--- skipped $ts (pid $lockContent still running) ---"
                exit 0
            }
        } catch { }
    }
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

$PID | Set-Content $LockFile
$cleanupBlock = { Remove-Item $LockFile -Force -ErrorAction SilentlyContinue }
Register-EngineEvent PowerShell.Exiting -Action $cleanupBlock | Out-Null

try {
    $ts = Get-Date -Format "o"
    Add-Content $LogFile "--- heartbeat $ts ---"
    Set-Location "{{WORK_DIR}}"

    $result = & claude -p "/{{PREFIX}}-heartbeat" `
        --max-turns 30 `
        --allowedTools "Bash(*),Read(*),Write(*),Edit(*),Glob(*),Grep(*),WebSearch(*),WebFetch(*),Task(*),Skill(*)" `
        2>&1
    $result | Add-Content $LogFile

    if ($LASTEXITCODE -eq 0) {
        Add-Content $LogFile "--- done $(Get-Date -Format 'o') ---"
    } else {
        Add-Content $LogFile "--- failed $(Get-Date -Format 'o') (exit code $LASTEXITCODE) ---"
    }

    # Sync RAG index (if search system is installed)
    $ingestScript = Join-Path $env:USERPROFILE "edge\search\ingest.py"
    if (Test-Path $ingestScript) {
        $pythonExe = Join-Path $env:USERPROFILE "edge\blog\.venv\Scripts\python.exe"
        if (Test-Path $pythonExe) {
            & $pythonExe $ingestScript (Join-Path $env:USERPROFILE "edge\reports") `
                (Join-Path $env:USERPROFILE "edge\notes") `
                (Join-Path $env:USERPROFILE "edge\blog\entries") --no-embed --quiet 2>$null
        }
    }
} finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
```

### 4.5 .env Minimo Viavel

```bash
# edge-of-chaos — API Keys
# Copy this to ~/edge/secrets/keys.env and fill in your values.
# chmod 600 ~/edge/secrets/keys.env

# Required for: edge-consult, review-gate, edge-dialogue, search embeddings
OPENAI_API_KEY=sk-your-key-here

# Required for: edge-fontes (web search via Exa)
EXA_API_KEY=your-exa-key-here

# Optional: edge-consult with Grok models
# XAI_API_KEY=your-xai-key-here

# Optional: X/Twitter search (edge-x, edge-fontes X source)
# X_BEARER_TOKEN=your-bearer-token
# X_API_KEY=your-api-key
# X_API_SECRET=your-api-secret
# X_ACCESS_TOKEN=your-access-token
# X_ACCESS_TOKEN_SECRET=your-access-token-secret

# Blog server
BLOG_PORT=8766
BLOG_AUTH_USER=agent
BLOG_AUTH_PASS=changeme

# Optional: Slack integration
# SLACK_BOT_TOKEN=xoxb-your-token

# Optional: Netlify deployment
# NETLIFY_API_KEY=your-key
```

### 4.6 models.env Minimo Viavel

```bash
# Default models for LLM-as-judge and adversarial review
# Copy to ~/edge/secrets/models.env

# LLM-as-judge for review-gate.py (quality gate before publishing)
EDGE_MODEL_REVIEW=gpt-4o

# Adversarial reviewer for edge-consult.py
EDGE_MODEL_CONSULT=gpt-4o

# Embedding model for search/RAG
EDGE_MODEL_EMBED=text-embedding-3-small

# Multi-turn dialogue (edge-dialogue.py)
EDGE_MODEL_DIALOGUE=gpt-4o

# Meta-report generation
EDGE_MODEL_META=gpt-4o
```

### 4.7 settings.json Minimo Viavel

```json
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(*)",
      "Write(*)",
      "Edit(*)",
      "Glob(*)",
      "Grep(*)",
      "NotebookEdit(*)",
      "WebSearch(*)",
      "WebFetch(*)"
    ]
  },
  "effortLevel": "high"
}
```

### 4.8 claude-heartbeat.timer

```ini
[Unit]
Description=Claude Code Heartbeat Timer

[Timer]
OnActiveSec=2h
OnUnitActiveSec=2h
Persistent=true

[Install]
WantedBy=timers.target
```

### 4.9 claude-heartbeat.service

```ini
[Unit]
Description=Claude Code Heartbeat (edge-of-chaos)

[Service]
Type=oneshot
WorkingDirectory=%h
ExecStart=%h/.local/bin/heartbeat.sh
Environment="HOME=%h"
Environment="PATH=%h/.local/bin:%h/.nvm/versions/node/v22.0.0/bin:/usr/local/bin:/usr/bin:/bin"
TimeoutStartSec=2700
```

### 4.10 skill-steps-registry.yaml (estrutura minima)

```yaml
# Registry de passos esperados por skill
# edge-skill-step usa para detectar passos pulados

skills:
  heartbeat:
    steps:
      - id: preflight
        label: "Preflight determinístico"
      - id: ler-sessoes
        label: "Ler sessões do usuário"
      - id: ler-chat
        label: "Ler chat assíncrono"
      - id: ler-insights
        label: "Ler insights do usuário"
      - id: ler-beats
        label: "Ler beats anteriores"
      - id: ler-debugging
        label: "Ler debugging.md"
      - id: ler-contexto
        label: "Ler contexto de projeto"
      - id: ler-threads
        label: "Ler fios de investigação"
      - id: ler-tasks
        label: "Ler task ledger"
      - id: corpus-check
        label: "Corpus check - isso é novo?"
      - id: classificar
        label: "Classificar beat"
      - id: sanity-check
        label: "Sanity check da decisão"
      - id: despachar
        label: "Despachar skill"
      - id: registrar
        label: "Registrar resultado"

  pesquisa:
    steps:
      - id: contexto
        label: "Absorver contexto"
      - id: corpus-check
        label: "Verificar corpus existente"
      - id: fontes
        label: "Buscar fontes externas"
      - id: analise
        label: "Análise e derivação"
      - id: adversarial
        label: "Sanity check adversarial"
      - id: yaml
        label: "Gerar YAML spec"
      - id: review-gate
        label: "Review gate"
      - id: blog
        label: "Escrever blog entry"
      - id: publicar
        label: "Publicar via consolidar-estado"
      - id: verificar
        label: "Verificar resultado"
```

---

## PARTE 5 — MECANISMOS AVANCADOS

### 5.1 Como Configurar o Heartbeat Autonomo

#### Linux (systemd) — Metodo Principal

```bash
# 1. Copiar arquivos de servico
mkdir -p ~/.config/systemd/user/
cp systemd/claude-heartbeat.service ~/.config/systemd/user/
cp systemd/claude-heartbeat.timer ~/.config/systemd/user/

# 2. Editar paths no .service
# ExecStart deve apontar para o heartbeat.sh
# PATH deve incluir node (para claude) e python

# 3. Ativar e iniciar
systemctl --user daemon-reload
systemctl --user enable --now claude-heartbeat.timer

# 4. Verificar
systemctl --user status claude-heartbeat.timer
systemctl --user list-timers

# 5. Disparar manualmente
systemctl --user start claude-heartbeat.service

# 6. Ver logs
journalctl --user -u claude-heartbeat.service -f
tail -f ~/.claude/heartbeat-output.log
```

**Frequencia:** `OnUnitActiveSec=2h` = a cada 2 horas apos a ultima execucao. Ajustar conforme necessidade. `Persistent=true` garante que beats perdidos sao recuperados.

#### macOS (launchd)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.edge-of-chaos.heartbeat</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-l</string>
        <string>/Users/USERNAME/.local/bin/heartbeat.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>7200</integer>
    <key>WorkingDirectory</key>
    <string>/Users/USERNAME</string>
    <key>StandardOutPath</key>
    <string>/Users/USERNAME/.claude/heartbeat-output.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/USERNAME/.claude/heartbeat-output.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/USERNAME</string>
        <key>PATH</key>
        <string>/Users/USERNAME/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

```bash
# Instalar
cp com.edge-of-chaos.heartbeat.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.edge-of-chaos.heartbeat.plist

# Verificar
launchctl list | grep heartbeat

# Disparar manualmente
launchctl start com.edge-of-chaos.heartbeat

# Parar
launchctl unload ~/Library/LaunchAgents/com.edge-of-chaos.heartbeat.plist
```

#### Windows (Task Scheduler)

```powershell
# Criar task agendada (PowerShell como admin)
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$env:USERPROFILE\.local\bin\heartbeat.ps1`""

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration (New-TimeSpan -Days 365)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "Claude-Heartbeat" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Claude Code autonomous heartbeat"

# Verificar
Get-ScheduledTask -TaskName "Claude-Heartbeat" | Get-ScheduledTaskInfo

# Disparar manualmente
Start-ScheduledTask -TaskName "Claude-Heartbeat"
```

### 5.2 Como Configurar a Memoria Persistente

**Inicializacao:**
1. Criar `memory/MEMORY.md` a partir do template (secao 4.2)
2. Criar `memory/rules-core.md` com max 15 regras no formato "when [context], [action]"
3. Criar `memory/personality.md` com perfil cognitivo
4. Criar `memory/metodo.md` (copiar do original)
5. Criar `memory/knowledge-design.md` (copiar do original)
6. Criar `memory/debugging.md` vazio (so header)
7. Criar `memory/topics/` vazio (cresce organicamente)

**Atualizacao incremental:**
- Blog entries tem campo `memory:` com insights como regras
- Heartbeat le `memory:`, faz `ls memory/topics/`, decide: append ou novo topic
- Regras expiradas sao podadas via `/aeita-reflexao`
- `misses.md` recebe erros que uma regra teria prevenido
- Curation trigger: arquivo > 15 regras OU regra nao citada em 10 sessoes

**Invariantes:**
1. Toda decisao major cita pelo menos 1 regra ou declara "no rule applicable"
2. Todo miss do usuario vira registro em misses.md em 24h
3. rules-core.md nunca excede 15 regras

### 5.3 Como Configurar o Review Gate

O review gate e implementado por `review-gate.py` — um pipeline de 3 fases que usa GPT como juiz de qualidade.

**Fases:**
1. **Co-author (Phase 1):** GPT com acesso a tools (read_memory, search_corpus, read_blog_entries) enriquece/gera YAML draft
2. **Reviewer (Phase 2):** GPT avalia cego (sem tools) em 6 dimensoes:
   - structural_completeness
   - content_depth
   - writing_quality
   - visualization
   - intellectual_honesty
   - internal_consistency
3. **Refiner (Phase 2):** Aplica feedback do reviewer reescrevendo YAML. 2 rounds.

**Threshold:** 3.5/5 (media das 6 dimensoes). Se FAIL, o agente ajusta e re-roda.

**Uso standalone:**
```bash
review-gate /tmp/spec-pesquisa-tema.yaml --skill pesquisa
```

**Uso via pipeline:** O `consolidar-estado` roda automaticamente na Phase 0.5. Flag `--skip-review` para forcar publicacao apos review manual.

**Custo:** ~$0.02-0.05 por review (depende do modelo).

### 5.4 Como Configurar LLM-as-Judge / Adversarial Review

**Componente:** `edge-consult.py`

**Dois modos:**
1. **Adversarial (default):** Encontra furos, steelmans o oposto, detecta vieses
2. **Colaborativo:** Expande, conecta, sugere angulos nao vistos

**Configuracao:**
```bash
# Criar wrapper em ~/bin/ ou ~/.local/bin/
cat > ~/.local/bin/edge-consult << 'EOF'
#!/bin/bash
$HOME/edge/tools/venv/bin/python3 $HOME/edge/tools/edge-consult.py "$@"
EOF
chmod +x ~/.local/bin/edge-consult
```

**Uso:**
```bash
# Adversarial (default)
edge-consult "Minha conclusao: X implica Y. Onde esta mais fraco?"

# Com contexto de arquivo
edge-consult "Tem furo?" --context spec.yaml notes.md

# Modelo alternativo
edge-consult --model grok-4 "Onde esta mais fraco?"

# Colaborativo
edge-consult --mode collab "Que angulos nao estou vendo?"
```

**Protocolo de resposta (codificado nas skills):**
1. Ler a critica com honestidade
2. Se argumento valido → ajustar conclusoes
3. Se mantiver posicao → registrar no relatorio como callout

**Custo:** ~$0.02/consulta. Log em ~/edge/logs/consult/.

### 5.5 Como Configurar Self-Improvement Loop

O agente melhora a si mesmo via multiplos mecanismos:

1. **review-gate.py:** Quality gate automatico antes de toda publicacao
2. **edge-consult:** Adversarial review por modelo diferente
3. **edge-state-audit:** Auditoria de mudancas de estado (snapshot PRE vs POST)
4. **edge-state-lint:** Linter de consistencia (gaps, refs quebradas, threads stale)
5. **edge-skill-step:** Detecta passos silenciosamente pulados
6. **git_signals.py:** Extrai fix chains e gaps persistentes do git log
7. **curadoria_compute.py:** Self-probes no corpus (o agente busca a si mesmo)
8. **misses.md:** Log de erros → viram regras novas
9. **/aeita-reflexao:** Skill dedicada a auto-reflexao

**O ciclo:**
```
producao → review-gate (qualidade) → edge-consult (vieses) →
publicacao → state-audit (integridade) → skill-step end (completude) →
reflexao periodica → misses → novas regras → producao melhorada
```

**Trigger de reflexao:** A cada ~5 beats, ou quando ha feedback acumulado do usuario.

**CLAUDE.md update:** Somente via `/aeita-reflexao`. O heartbeat NUNCA atualiza CLAUDE.md diretamente.

### 5.6 Como Configurar Search (Exa/HN)

**edge-fontes** unifica 4 fontes: Exa (web), arXiv (papers), HN (tech), X (practitioners).

**Configuracao Exa:**
1. Obter API key em exa.ai
2. Salvar em `~/edge/secrets/exa.env`: `EXA_API_KEY=your-key`
3. edge-fontes carrega automaticamente

**Uso:**
```bash
# Busca multi-fonte
edge-fontes "autonomous AI agents" --sources exa,hn,arxiv

# Front page do HN
edge-fontes --front-page

# Busca focada em Exa
edge-fontes "AI agent heartbeat" --sources exa --max 10
```

**edge-search (busca interna):**
```bash
# Indexar corpus local
edge-index ~/edge/reports/ ~/edge/notes/ ~/edge/blog/entries/

# Buscar no corpus
edge-search "adversarial review" -k 5
```

**Padroes:**
- Resultados de edge-fontes alimentam diretamente o contexto do Claude via output do tool
- Nao ha cache explicito de resultados — a publicacao no blog/reports serve como cache permanente
- edge-search usa SQLite FTS5 + opcionalmente vectores (sqlite-vec) **[VERIFICAR: modulo sqlite-vec e opcional e pode nao estar instalado]**

---

## PARTE 6 — O QUE CUSTOMIZAR PARA CADA NOVO PROJETO

### 6.1 Especifico do edge-of-chaos (NAO copiar literalmente)

- Nome "aeita" e bio especifica
- Porta do blog 8768 com credenciais aeita:h8
- Projeto AEITA WhatsApp Communities
- Topics especificos (marketing-aeita.md, deploy-fleet.md)
- Referencia a VM Vultr Sao Paulo
- Referencia a Salesforce/ETL
- Paths hardcoded para `-home-aeita` e `-home-vboxuser` **[VERIFICAR: ha inconsistencia entre esses dois paths no codigo; o vboxuser parece ser o original, aeita a instancia deployada]**
- Interesses pessoais do Lucas (fisica, matematica, musica)
- Contexto de negocio AEITA

### 6.2 Infraestrutura Generica (copiar e adaptar)

- **Heartbeat completo** (timer + lock + log + skill dispatch)
- **Pipeline consolidar-estado** (8 fases, atomico, idempotente)
- **State protocol** (snapshot → propose → edit → audit)
- **Skill-step tracking** (registry + detection de silent skips)
- **Knowledge design** (rules-core max 15, topics, misses)
- **Metodo Feynman** (derivar antes de pesquisar)
- **Adversarial review** (edge-consult cross-model)
- **Quality gate** (review-gate LLM-as-judge)
- **Preflight deterministico** (zero tokens antes de decidir)
- **Report pipeline** (YAML → HTML autocontido)
- **Claims system** (conhecimento duravel, gaps com `!`)
- **Threads system** (fios de investigacao com resurface dates)
- **Event sourcing** (JSONL append-only para telemetria)
- **Blog como canal primario** (toda producao publicada)
- **Git structured commits** (metadados parseavel no footer)
- **Anti-saturacao** (variar temas, alternar trabalho/exploracao)
- **Templates cross-platform** (.sh + .ps1)

### 6.3 Guia de Personalizacao do CLAUDE.md

| Secao | Mudar? | O que fazer |
|-------|--------|-------------|
| Identity | **SIM** | Novo nome, bio, codename |
| Memory / Required Reading | Manter estrutura | Adaptar paths |
| Method | Manter | Feynman e generico |
| Skills | **SIM** | Trocar prefixo, adaptar lista |
| Blog | Adaptar | Porta, credenciais |
| Tools | Manter | Lista de tools e generica |
| Domain | **SIM** | Novo dominio e diretorio |
| Preferences | Manter + adicionar | Preferencias sao genericas + especificas |
| Pipeline | Manter | Fluxo e generico |

---

## PARTE 7 — TROUBLESHOOTING

### 7.1 Problemas Previstos e Solucoes

| Sintoma | Causa Provavel | Solucao |
|---------|---------------|---------|
| Timer ativo mas heartbeat nao roda | PATH nao inclui `claude` (node) | Verificar PATH no .service: deve incluir diretorio do node/nvm |
| Heartbeat roda mas nao despacha skill | Claude Code nao autenticado | Fazer `claude` interativo para login via browser |
| `consolidar-estado` falha na Phase 1 | Blog server nao rodando | `systemctl --user start blog.service` |
| `consolidar-estado` falha na Phase 0.5 | YAML nao passa no review-gate | Ajustar YAML com base no feedback, re-rodar review-gate standalone |
| `consolidar-estado` exit code 5 | State audit detectou violacao | Mudanca em arquivo protegido sem proposta. Verificar se `edge-state-audit propose` foi chamado |
| `edge-consult` falha | OPENAI_API_KEY invalida ou ausente | Verificar ~/edge/secrets/openai.env |
| `edge-fontes` sem resultados Exa | EXA_API_KEY invalida | Verificar ~/edge/secrets/exa.env |
| `edge-search` falha | SQLite database nao inicializada | Rodar `edge-index` nos diretorios de conteudo |
| Heartbeat repete mesmo tema | Anti-saturacao nao funcionando | Verificar log do dia: se >3 beats no mesmo tema, forcar mudanca |
| Skills pulando passos silenciosamente | Falta de `edge-skill-step` calls | Verificar skill-steps-registry.yaml, rodar `edge-skill-step end` |
| Blog entry sem claims | Frontmatter incompleto | Adicionar `claims:` e `threads:` ao YAML frontmatter |
| Reports com SVG quebrado | SVG mal-formado | Rodar `validate-svg` no HTML gerado |
| Symlinks quebrados no bin/ | Deploy em maquina diferente | Recriar symlinks ou copiar arquivos diretamente |
| `heartbeat-preflight.sh` sempre PREFLIGHT_CLEAN | Blog chat API nao responde | Verificar se blog server esta rodando e acessivel em localhost |
| Path `-home-vboxuser` vs `-home-aeita` | Inconsistencia entre dev e deploy | Ajustar paths nos tools (review-gate.py:44 hardcoded) |

### 7.2 Como Verificar se o Agente Esta Funcionando

```bash
# 1. Timer ativo?
systemctl --user status claude-heartbeat.timer
# Deve mostrar "active (waiting)" com proxima execucao

# 2. Ultimo heartbeat executou?
tail -20 ~/.claude/heartbeat-output.log
# Deve mostrar "--- done TIMESTAMP ---" recente

# 3. Blog server rodando?
curl -s http://localhost:8766/api/chat | python3 -c "import json,sys; print(json.load(sys.stdin))" 2>/dev/null
# Deve retornar JSON com messages

# 4. Skills registradas?
ls ~/.claude/skills/*/SKILL.md | wc -l
# Deve retornar >= 20

# 5. Estado consistente?
edge-state-lint 2>/dev/null
# Deve retornar sem erros criticos

# 6. Claims acumulando?
edge-claims --stats 2>/dev/null
# Deve mostrar contagem > 0 apos primeiros beats

# 7. Claude Code autenticado?
claude --version
# Deve retornar versao sem erro de auth

# 8. APIs externas funcionando?
edge-consult "Teste: 1+1=2. Tem furo?" 2>/dev/null
# Deve retornar resposta do GPT

# 9. Preflight funcional?
bash ~/edge/tools/heartbeat-preflight.sh
# Deve retornar PREFLIGHT_CLEAN ou PREFLIGHT_WORK
```

---

## PARTE 8 — DESCOBERTAS ADICIONAIS

### 8.1 Arquitetura Multi-Modelo Deliberada

O design mais sofisticado do agente e o uso deliberado de **modelos concorrentes como revisores adversariais**. O Claude (Anthropic) e o agente host — quem pensa, decide, e executa. Mas antes de publicar qualquer output, submete suas conclusoes a GPT-5.4 ou Grok (via edge-consult). Isso cria um **adversarial review loop** onde:
- Claude produz → GPT critica → Claude ajusta ou defende
- Nenhum modelo avalia a si mesmo
- O custo e minimo (~$0.02/consulta)

Isso e distinto de simplesmente "usar a melhor API". E um design pattern de **checks and balances cognitivos**.

### 8.2 Pipeline Atomico com Rollback Semantico

O `consolidar-estado` nao e apenas "publicar no blog". E um pipeline de 8 fases com:
- **Exit codes semanticos** (0=ok, 1=fatal, 2=partial, 3=review fail, 5=state violation)
- **Orphan guard** (destage arquivos de outros slugs antes de commitar)
- **Recovery mode** (`--recover` para entries sem git commit)
- **Failure logging** para post-mortem (pipeline-failures.jsonl)
- **Idempotencia** (checa events.jsonl antes de duplicar)

### 8.3 Zero-Token Preflight

O `heartbeat-preflight.sh` e um script bash puro que verifica ~6 sinais em ~3 segundos sem gastar nenhum token de LLM. Isso e crucial porque o heartbeat roda a cada 2h — sem preflight, cada invocacao custaria tokens do Claude mesmo quando nao ha nada a fazer.

**Sinais verificados:**
- Chat pendente (blog API)
- Eventos recentes
- Threads com resurface vencido
- Entradas em debugging.md
- Breaks ativas
- Tasks P0 pendentes

### 8.4 Knowledge Clusters Anti-Hype

O design de `knowledge-design.md` e deliberadamente contra a tendencia de RAG/embeddings:
- "Nao criar embeddings/retrieval infra — filenames suffice until ~30 clusters"
- "Nao criar rule engine (YAML schemas, JSONL logs) — e um LLM, le texto"
- "Nao criar 'influence detection' metrics post-hoc — greenwashing"

O conhecimento e organizado como **texto que muda comportamento**, nao como dados para retrieval. O teste e: "se eu deletar este arquivo e meu comportamento nao mudar, era clutter."

### 8.5 Claims como Conhecimento Destilado

O sistema de claims (no frontmatter dos blog entries) e um mecanismo elegante:
- Claims sem prefixo = fatos verificados
- Claims com `!` = gaps de conhecimento ("nao sei")
- Gaps sao candidatos naturais para pesquisa futura
- Claims sobrevivem sem reler o texto inteiro

Isso cria um **knowledge graph emergente** onde cada publicacao deposita conhecimento destilado, e o agente pode consultar `edge-claims --open` para saber exatamente o que ainda nao sabe.

### 8.6 Inconsistencia de Paths **[VERIFICAR]**

Ha uma inconsistencia entre `-home-vboxuser` (nos tools, que parecem ter sido desenvolvidos numa VM VirtualBox) e `-home-aeita` (na instancia deployada na Vultr). O `review-gate.py` tem `MEMORY_DIR = Path.home() / ".claude/projects/-home-vboxuser/memory"` hardcoded (linha 44), enquanto o agente deployado usa `-home-aeita`. O `consolidar-estado` mais recente usa branding.yaml para resolver isso dinamicamente, mas os tools individuais podem ter paths legados.

### 8.7 Blog Server como Hub de Comunicacao

O blog server em localhost nao e apenas um blog — e o hub de comunicacao assincrona entre humano e agente:
- **Chat API** (`/api/chat`): canal assincrono humano → agente
- **Blog entries**: canal agente → humano (insights, pesquisas, descobertas)
- **Comments**: feature de anotacao (existem mas heartbeat nao processa)

O heartbeat le o chat, processa mensagens, e marca como `processed`. O humano pode deixar mensagens a qualquer hora — o agente pega no proximo beat.

### 8.8 Serendipity by Design

O heartbeat inclui um "serendipity scan" deliberado: 3 queries LATERAIS no X/Twitter, nao sobre o tema direto, mas sobre conceitos adjacentes. O objetivo e trazer conexoes inesperadas. Quando nao ha trabalho urgente, o agente despacha `/aeita-lazer` ou `/aeita-descoberta` — nao para, apenas muda de modo. "Anti-saturacao muda de significado: nao e 'pare', e 'mude de tema'."

---

## APENDICE — Referencia Rapida

### Comandos de Operacao do Dia a Dia

```bash
# === HEARTBEAT ===

# Verificar status do timer
systemctl --user status claude-heartbeat.timer

# Verificar proxima execucao
systemctl --user list-timers | grep heartbeat

# Disparar heartbeat manualmente
systemctl --user start claude-heartbeat.service

# Ou via Claude Code diretamente
cd ~/edge && claude -p "/aeita-heartbeat" --max-turns 30

# === LOGS ===

# Ver log do heartbeat
tail -f ~/.claude/heartbeat-output.log

# Ver log do dia
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log

# Ver journal do systemd
journalctl --user -u claude-heartbeat.service --since today

# === ESTADO ===

# Verificar consistencia do estado
edge-state-lint

# Ver claims acumuladas
edge-claims --stats
edge-claims --open  # gaps abertos

# Ver tasks do agente
edge-task list

# Ver eventos recentes
edge-event recent

# Ver briefing (estado compactado)
cat ~/edge/briefing.md

# === PUBLICACAO ===

# Pipeline completo
consolidar-estado ~/edge/blog/entries/entry.md /tmp/spec.yaml

# Pipeline sem report (meta-only)
consolidar-estado ~/edge/blog/entries/entry.md

# Review gate standalone
review-gate /tmp/spec.yaml --skill pesquisa

# === BUSCA ===

# Busca externa multi-fonte
edge-fontes "query" --sources exa,hn,arxiv

# Busca interna no corpus
edge-search "query" -k 5

# Indexar conteudo novo
edge-index ~/edge/reports/ ~/edge/notes/ ~/edge/blog/entries/

# === PARAR ===

# Parar timer
systemctl --user stop claude-heartbeat.timer

# Desativar completamente
systemctl --user disable claude-heartbeat.timer

# Parar blog server
systemctl --user stop blog.service
```

### Estrutura de Diretorios do Agente Deployado

```
~/edge/                          # Raiz do agente
  ├── blog/
  │   ├── entries/*.md           # Blog entries (markdown + YAML frontmatter)
  │   ├── app.py                 # Blog server (Flask)
  │   └── .venv/                 # Python venv do blog
  ├── reports/*.html             # Reports HTML autocontidos
  ├── meta-reports/              # Meta-reports (state delta + scratchpad)
  │   ├── *-meta.md
  │   ├── *.state-proposal.yaml
  │   └── *.state-audit.yaml
  ├── notes/*.md                 # Notas avulsas
  ├── threads/*.md               # Fios de investigacao (YAML frontmatter + md)
  ├── logs/
  │   ├── heartbeat-YYYY-MM-DD.log
  │   ├── events.jsonl           # Event sourcing
  │   ├── execution-ledger.jsonl # Telemetria de tools
  │   └── consult/               # Logs do edge-consult
  ├── state/
  │   ├── git-signals.json
  │   ├── curadoria-candidates.json
  │   └── ops-hotspots.json
  ├── state-snapshots/           # SHA256 snapshots PRE
  │   └── *.pre.yaml
  ├── memory/
  │   ├── MEMORY.md.template
  │   ├── personality.md
  │   ├── rules-core.md
  │   ├── metodo.md
  │   ├── knowledge-design.md
  │   ├── debugging.md
  │   └── topics/*.md            # Knowledge clusters
  ├── tools/                     # CLI tools
  │   ├── venv/                  # Python venv dos tools
  │   ├── edge-fontes
  │   ├── edge-consult.py
  │   ├── ...
  │   └── assets/
  │       ├── base.css
  │       └── logo.svg
  ├── builds/                    # Builds interativos (HTML/JS)
  ├── lab/                       # Experimentos
  ├── autonomy/
  │   ├── autonomy-policy.md
  │   ├── capabilities.md
  │   └── ...
  ├── secrets/                   # API keys (chmod 600)
  │   ├── openai.env
  │   ├── exa.env
  │   └── ...
  ├── search/                    # Sistema de busca (SQLite FTS5)
  │   ├── ingest.py
  │   └── search.py
  ├── CLAUDE.md                  # Instrucoes do agente (gerado do template)
  └── .env.example

~/.claude/                       # Configuracao do Claude Code
  ├── CLAUDE.md                  # Instrucoes user-level
  ├── settings.json              # Permissoes e effort level
  ├── skills/
  │   ├── _shared/
  │   │   ├── state-protocol.md
  │   │   └── report-template.md
  │   └── {PREFIX}-*/SKILL.md    # Skills do agente
  ├── projects/-home-{user}/
  │   └── memory/
  │       ├── MEMORY.md          # Auto-memory instanciada
  │       ├── debugging.md
  │       ├── personality.md
  │       └── topics/*.md
  └── heartbeat-output.log       # Log do heartbeat

~/.config/systemd/user/          # Servicos systemd
  ├── claude-heartbeat.service
  ├── claude-heartbeat.timer
  └── blog.service
```
