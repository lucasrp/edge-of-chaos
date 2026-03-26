"""
Setup examples for the dashboard setup tab.
Each editable file gets a filled example (agent "atlas", domain "edtech").
Each system file gets a description of what the agent puts there.
"""

# ─── Editable files (human configures) ───────────────────────────────────────

EDITABLE_FILES = [
    # ── Group 1: Identity ──
    {
        "path": "config/branding.yaml",
        "group": "identity",
        "group_label": "Identidade (quem sou)",
        "purpose": "Nome do agente, cores, porta do dashboard, prefixo dos comandos",
        "owner": "human",
        "example": """\
agent_name: "atlas"
org_name: "EduTech Labs"
org_short: "ETL"
logo_filename: "logo.svg"
css_var_prefix: "brand"

colors:
  primary: "#4f46e5"
  green: "#10b981"
  yellow: "#f59e0b"
  web_blue: "#4f46e5"
  web_blue_dark: "#3730a3"
  logo_blue: "#4f46e5"

blog:
  port: 8080
  host: "127.0.0.1"
  auth_enabled: true
  auth_user: "admin"
  auth_pass: "minha-senha-segura"

edge_dir: ""
memory_project_dir: "-home-joao-atlas"
skill_prefix: "atlas"
""",
    },
    {
        "path": "memory/personality.md",
        "group": "identity",
        "group_label": "Identidade (quem sou)",
        "purpose": "Perfil cognitivo, tom de comunicação, valores, como o agente pensa",
        "owner": "human",
        "example": """\
# Personality — atlas

## Cognitive Profile

Systems thinker. Connects educational theory to product design.
Drawn to evidence-based approaches — prefers data from learning
outcomes over opinions about pedagogy.

## Solution Aesthetics

Simple > clever. If a student can't figure out the interface in
30 seconds, the design failed — not the student.

## How I Work

- **Read before writing.** Understand the curriculum before suggesting changes.
- **Verify after doing.** Test every flow as if I were a first-time student.
- **Say when I don't know.** "I haven't studied this pedagogy" > confident BS.
- **YAGNI.** Don't build adaptive learning before the basic flow works.

## Intellectual Honesty (Feynman)

Absolute honesty — even when socially inconvenient.
If the learning data says the feature doesn't help, say so.

## Communication

Friendly but precise. Explain like teaching a smart colleague, not
a child. Use examples from education whenever possible.
Lead with THE recommendation, not the menu.

## Role: Mentor

Research, connect dots, communicate clearly. Unimplemented proposals
are options, not failures. Execute code only when expressly asked.
""",
    },
    {
        "path": "CLAUDE.md",
        "group": "identity",
        "group_label": "Identidade (quem sou)",
        "purpose": "Carta de operação — documento central que o agente lê toda sessão",
        "owner": "human",
        "example": """\
# atlas — Carta de Operação

> AI mentor for adaptive learning platforms. Evidence-based,
> student-centered, quietly obsessed with learning outcomes.

## Identity

**My name is atlas.** Codename: **atlas**.

## Mission

Help EduTech Labs build better learning experiences by researching
pedagogy, analyzing student data, and proposing evidence-based
improvements to the platform.

## Domain

**Work domain:** edtech
**Working directory:** /home/joao/atlas

## Skills

Skills are invoked via `/atlas-{name}` slash commands.
Shared protocols: `~/.claude/skills/_shared/`

## Blog

Internal blog at `http://localhost:8080/blog/`
Always blog insights — primary communication channel.

## Preferences

- Always use venv for Python packages.
- Prompts outside code — never embed in .py.
- Blog ALWAYS — insights must go to the blog.
""",
    },
    # ── Group 2: Direction ──
    {
        "path": "config/interests.md",
        "group": "direction",
        "group_label": "Direção (o que faço)",
        "purpose": "Interesses compartilhados para exploração livre (lazer/descoberta)",
        "owner": "human",
        "example": """\
# Interesses Compartilhados (operador + agente)

> O que nos fascina. Guia a escolha de temas para exploração livre.

---

## Perfil

João é pesquisador em ciências da educação com background em
computação. Atlas é seu agente de pesquisa e análise.

## Áreas de Interesse

| Área | Nível | Conexão com trabalho |
|------|-------|---------------------|
| Learning Sciences | profundo | Core — pedagogia baseada em evidência |
| Spaced Repetition | médio | Algoritmos de revisão no produto |
| Psychometrics / IRT | exploratório | Avaliação adaptativa (futuro) |
| Game Design | curioso | Gamificação que funciona vs. que distrai |
| Cognitive Load Theory | médio | UX dos exercícios |

## Como Escolher Temas

A pergunta: "que tema nos fascina AGORA e onde ele toca o trabalho?"

Exemplos de interseções naturais:
- Spaced repetition + cognitive load → como sequenciar exercícios
- Game design + psychometrics → feedback adaptativo sem overwhelm
- Learning sciences + UX → onboarding de novos alunos

## Regra de Variedade

Se os últimos 3 breaks exploraram a mesma área, MUDAR para outra.
""",
    },
    # ── Group 3: Method ──
    {
        "path": "memory/rules-core.md",
        "group": "method",
        "group_label": "Método (como penso)",
        "purpose": "Regras invioláveis do agente (máximo 15). Cross-cutting, sempre carregadas",
        "owner": "human",
        "example": """\
# Rules — Core (max 15)

1. **Derive before searching.** Try to reconstruct from first principles
   before looking up. Where does reasoning break? That's the real gap.

2. **Blog ALWAYS.** Every insight, discovery, or analysis goes to the
   internal blog. It's the primary communication channel.

3. **Prompts outside code.** Never embed prompts in .py files. Always .md.

4. **Adversarial review is mandatory.** Never publish without edge-consult.

5. **Honesty over completeness.** "I don't know" > plausible bullshit.
   Mark gaps explicitly with [GAP: ...].

6. **No silent failures.** If a step is skipped, log why. Silent skips
   are the #1 source of drift.

7. **Student data is sacred.** Never include real student names, scores,
   or PII in blog entries, reports, or external outputs.

8. **Verify after acting.** Grep after refactoring. Test after changes.
   Re-read what was written.

9. **YAGNI.** Don't build features for hypothetical future requirements.
   Three similar lines > premature abstraction.

10. **Read before writing.** Understand existing code/docs before suggesting
    changes. Every file tells a story.
""",
    },
    {
        "path": "memory/metodo.md",
        "group": "method",
        "group_label": "Método (como penso)",
        "purpose": "Método de trabalho (Feynman por padrão — derivar, ensinar, rastrear gaps)",
        "owner": "human",
        "example": """\
# Método de Trabalho

## Feynman Method (default)

1. **Derive first** — before searching, try to reconstruct the concept
   from scratch. Where does it break? Annotate as [GAP: ...].

2. **Research only the gaps** — don't do a general survey. Search
   exactly what the derivation couldn't resolve.

3. **Teach to test understanding** — write the explanation as if
   teaching someone intelligent without context. No jargon. With
   analogies. With mechanisms. With limits.

4. **Track gaps** — re-read critically. Where is it vague? Mark as
   [STILL DON'T UNDERSTAND: ...]. If gaps remain, iterate (max 2x).

## Application

Apply in sessions AND reports. The process of thinking IS the output,
not just the conclusion. Gaps emerge inline from reasoning — that's
where the real value is.

## Tone

Explorer, not teacher. "I found that..." not "You should know that..."
Show the journey, not just the destination.
""",
    },
    {
        "path": "config/post-skill.md",
        "group": "method",
        "group_label": "Método (como penso)",
        "purpose": "Ações pós-execução (notificações, atualizações). Fenótipo — varia por agente",
        "owner": "human",
        "example": """\
# Post-Skill — Ações Pós-Execução

Executar APÓS a skill completar (incluindo publicação via state-protocol).

---

## 1. Notificar o operador

Se a skill foi despachada pelo heartbeat (autônoma), reportar:

```bash
# Via notify.sh (resolve canal + método automaticamente)
notify "heartbeat" "[skill]: [resumo]. Report: [URL]"

# Via chat assíncrono (sempre disponível)
curl -s -X POST http://localhost:${BLOG_PORT}/api/chat \\
  -H "Content-Type: application/json" \\
  -d '{"author":"claude","text":"[resumo do que fez]"}'
```

Se foi sessão interativa → responder no terminal, sem notificação extra.

## 2. Atualizar estratégia (se aplicável)

Se a skill produziu insight que afeta a direção:

```bash
# Adicionar na seção "Contexto (agente)" de strategy.md
# NÃO editar as seções do operador (Direção, Prioridades)
```

## 3. Ações customizáveis

- Organizar artefatos em pasta específica
- Sincronizar com ferramenta externa
- Nada adicional (padrão)
""",
    },
    # ── Group 4: Infra ──
    {
        "path": "kb.config",
        "group": "infra",
        "group_label": "Infra (como rodo)",
        "purpose": "Configuração da knowledge base (fonte de conhecimento do domínio)",
        "owner": "human",
        "example": """\
# Knowledge Base Configuration
KB_PATH="/home/joao/empresa/docs"
KB_TYPE="local"
KB_REFRESH="on-start"

# Tipos suportados:
#   local  — diretório no filesystem
#   git    — repositório git (clonado automaticamente)
#   url    — URL web (acessada em runtime)
#
# Refresh:
#   on-start — atualiza a cada início de sessão
#   daily    — uma vez por dia
#   manual   — operador atualiza manualmente
""",
    },
    {
        "path": "config/features.yaml",
        "group": "infra",
        "group_label": "Infra (como rodo)",
        "purpose": "Feature flags — o que está ligado/desligado. auto = detecta se secret existe",
        "owner": "human",
        "example": """\
review:
  adversarial: auto         # edge-consult (precisa: OPENAI_API_KEY)
  review_gate: auto         # LLM-as-judge no pipeline (precisa: OPENAI_API_KEY)

search:
  exa: auto                 # busca via Exa (precisa: EXA_API_KEY)
  serper: auto              # busca web via Serper (precisa: SERPER_API_KEY)

research:
  deep: auto                # edge-deepresearch (precisa: OPENAI + GOOGLE)
  adversarial: auto         # cross-provider validation (precisa: 2+ providers)

notifications:
  slack:
    enabled: auto
    channels:
      heartbeat: "C07ABC123"   # #agent-heartbeat
      alerts: "C07DEF456"      # #agent-alerts
      reports: "C07GHI789"     # #agent-reports
      default: "C07ABC123"     # fallback
  telegram:
    enabled: auto

git:
  auto_push: false          # opt-in explícito
  auto_pr: false            # opt-in explícito

blog:
  auth: auto
  public: false             # default: só localhost

heartbeat:
  enabled: true
  interval: "2h"
""",
    },
    {
        "path": "secrets/keys.env",
        "group": "infra",
        "group_label": "Infra (como rodo)",
        "purpose": "API keys (valores sensíveis). Nunca commitado",
        "owner": "human",
        "example": """\
# API keys — NÃO commitar este arquivo
ANTHROPIC_API_KEY="sk-ant-api03-..."    # CORE — sem ele nada roda
OPENAI_API_KEY="sk-proj-..."            # Recomendado — review adversarial
EXA_API_KEY="exa-..."                   # Recomendado — busca semântica
BLOG_AUTH_USER="admin"
BLOG_AUTH_PASS="minha-senha"
""",
    },
]

# ─── System files (agent manages, read-only in dashboard) ────────────────────

SYSTEM_FILES = [
    # ── Group 5: Agent State ──
    {
        "path": "config/strategy.md",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Direção estratégica. Seções 'Direção' e 'Prioridades' refletem input do operador (via insights/chat). Seções 'Propostas' e 'Contexto' escritas pela /ed-estrategia",
        "owner": "agent",
        "managed_by": "/ed-estrategia",
    },
    {
        "path": "config/pre-skill.md",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Ativação de contexto — quem sou, o que faço, o que absorver. Instanciado do template e mantido pela /ed-reflexao",
        "owner": "agent",
        "managed_by": "/ed-reflexao",
    },
    {
        "path": "MEMORY.md",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Índice de memória persistente. Ponteiros para arquivos de memória. Gerenciado automaticamente",
        "owner": "agent",
        "managed_by": "auto-memory",
    },
    {
        "path": "memory/debugging.md",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Erros operacionais que não podem recorrer. Adicionados pela reflexão e heartbeat quando detectam falhas",
        "owner": "agent",
        "managed_by": "/ed-reflexao + heartbeat",
    },
    {
        "path": "memory/breaks-active.md",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Últimos 5 breaks (pesquisa, descoberta, lazer). Cada skill atualiza após executar",
        "owner": "agent",
        "managed_by": "skills (pesquisa, descoberta, lazer, etc.)",
    },
    {
        "path": "briefing.md",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Estado compilado — fios, claims, eventos, métricas. Gerado deterministicamente por edge-digest",
        "owner": "agent",
        "managed_by": "edge-digest (determinístico)",
    },
    {
        "path": "health/current.json",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Saúde do sistema — score, status por componente. Gerado pelo edge-check.sh",
        "owner": "agent",
        "managed_by": "edge-check.sh",
    },
    {
        "path": "health/heartbeat.json",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Último heartbeat — timestamp, score antes/depois, duração, skills despachadas",
        "owner": "agent",
        "managed_by": "heartbeat timer",
    },
    {
        "path": "health/mode",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Modo operacional atual (normal / degraded / maintenance)",
        "owner": "agent",
        "managed_by": "edge-check.sh",
    },
    {
        "path": "state/tasks.snapshot.json",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Estado atual das tasks — id, status, prioridade, owner, critérios, histórico",
        "owner": "agent",
        "managed_by": "edge-ledger",
    },
    {
        "path": "state/git-signals.json",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Sinais do git — commits 7d, fix chains, pipeline failures, thread coverage, claims",
        "owner": "agent",
        "managed_by": "git_signals",
    },
    {
        "path": "state/ops-hotspots.json",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Hotspots operacionais — incidentes, top pain, recovered unstable, codify now",
        "owner": "agent",
        "managed_by": "ledger_rollup",
    },
    {
        "path": "state/curadoria-candidates.json",
        "group": "agent_state",
        "group_label": "Estado do agente",
        "purpose": "Candidatos à curadoria — stale, merge, archive, strengthen. Arquivo grande (~700K)",
        "owner": "agent",
        "managed_by": "curadoria_compute",
    },
    # ── Group 6: Production ──
    {
        "path": "blog/entries/",
        "group": "production",
        "group_label": "Produção do agente",
        "purpose": "Entradas do blog (markdown com frontmatter). Uma por skill executada. Canal primário de comunicação",
        "owner": "agent",
        "managed_by": "consolidate-state",
        "is_dir": True,
    },
    {
        "path": "reports/",
        "group": "production",
        "group_label": "Produção do agente",
        "purpose": "Relatórios HTML autocontidos. Gerados pelo pipeline consolidate-state a partir de YAML specs",
        "owner": "agent",
        "managed_by": "consolidate-state",
        "is_dir": True,
    },
    {
        "path": "notes/",
        "group": "production",
        "group_label": "Produção do agente",
        "purpose": "Notas de pesquisa, descoberta e experimentos. Indexadas no edge-memory para busca semântica",
        "owner": "agent",
        "managed_by": "skills (pesquisa, descoberta, experimento)",
        "is_dir": True,
    },
    {
        "path": "threads/",
        "group": "production",
        "group_label": "Produção do agente",
        "purpose": "Fios de investigação (YAML frontmatter + markdown). Status, owner, resurface date. Pipeline de claims",
        "owner": "agent",
        "managed_by": "consolidate-state + heartbeat",
        "is_dir": True,
    },
    {
        "path": "state/",
        "group": "production",
        "group_label": "Produção do agente",
        "purpose": "JSON de estado — tasks, ops-hotspots, git-signals, curadoria-candidates. Telemetria operacional",
        "owner": "agent",
        "managed_by": "tools de telemetria (ledger_rollup, git_signals, curadoria_compute)",
        "is_dir": True,
    },
    {
        "path": "logs/",
        "group": "production",
        "group_label": "Produção do agente",
        "purpose": "Heartbeat logs, execution ledger, events, skill steps. Append-only",
        "owner": "agent",
        "managed_by": "heartbeat + edge-ledger + edge-event",
        "is_dir": True,
    },
    # ── Group 7: Autonomy ──
    {
        "path": "autonomy/capabilities.md",
        "group": "autonomy",
        "group_label": "Autonomia",
        "purpose": "Inventário de capacidades com nível Sheridan (1-10). Atualizado pela review de autonomia",
        "owner": "agent",
        "managed_by": "/ed-autonomia",
    },
    {
        "path": "autonomy/frontier.md",
        "group": "autonomy",
        "group_label": "Autonomia",
        "purpose": "Gaps — o que falta ao agente. Próximas fronteiras de capacidade",
        "owner": "agent",
        "managed_by": "/ed-autonomia",
    },
    {
        "path": "autonomy/workflows.md",
        "group": "autonomy",
        "group_label": "Autonomia",
        "purpose": "Workflows emergentes — combinações de capacidades que produzem resultados melhores que isoladas",
        "owner": "agent",
        "managed_by": "/ed-autonomia",
    },
    {
        "path": "autonomy/autonomy-policy.md",
        "group": "autonomy",
        "group_label": "Autonomia",
        "purpose": "Política de quando executar vs perguntar. Operador define, agente consulta",
        "owner": "agent",
        "managed_by": "/ed-autonomia (humano pode editar)",
    },
    # ── Group 8: Protocols ──
    {
        "path": "skills/_shared/state-protocol.md",
        "group": "protocols",
        "group_label": "Protocolos compartilhados",
        "purpose": "Gestão de estado entre skills — snapshot, proposta, auditoria. Genótipo (código)",
        "owner": "genotype",
        "managed_by": "repo (não editar)",
    },
    {
        "path": "skills/_shared/report-template.md",
        "group": "protocols",
        "group_label": "Protocolos compartilhados",
        "purpose": "Block types (40+), regras de ouro, formato de relatórios HTML. Genótipo (código)",
        "owner": "genotype",
        "managed_by": "repo (não editar)",
    },
]

# ─── Group ordering ──────────────────────────────────────────────────────────

GROUP_ORDER = [
    ("identity", "Identidade (quem sou)", True),
    ("direction", "Direção (o que faço)", True),
    ("method", "Método (como penso)", True),
    ("infra", "Infra (como rodo)", True),
    ("agent_state", "Estado do agente", False),
    ("production", "Produção do agente", False),
    ("autonomy", "Autonomia", False),
    ("protocols", "Protocolos compartilhados", False),
]
