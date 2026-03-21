# REPLICATION BLUEPRINT — edge-of-chaos

> Updated: 2026-03-21
> Architecture: centralized path resolution via `config/paths.py` + `config/paths.sh`

---

## PART 1 — WHAT THIS AGENT DOES

### 1.1 Mission

Autonomous AI agent built on Claude Code CLI. Wakes every 2h via systemd timer, evaluates context (user sessions, pending errors, investigation threads), and dispatches an appropriate skill — research, discovery, creative break, reflection, strategy, or execution.

Follows the Feynman Method: derive before searching, show thinking process, gaps emerge inline. Honest, analytical, minimal footprint, maximum leverage.

### 1.2 Architecture

```
Timer (systemd 2h) → heartbeat.sh → claude -p '/{PREFIX}-heartbeat'
  → preflight (deterministic, 0 tokens)
  → classify (WORK or EXPLORE)
  → edge-consult (adversarial sanity check)
  → dispatch ONE skill
  → skill produces: YAML spec → review-gate → blog entry → consolidar-estado (8 phases)
```

### 1.3 Key Design Decisions

- **Cross-model adversarial review**: Claude never evaluates itself. All conclusions go through `edge-consult` (GPT-5.4 + Grok) before publishing.
- **Publication = state commit**: Every intellectual output goes through `consolidar-estado` — blog entry + optional HTML report + claims + threads + events + git commit.
- **Centralized path resolution**: All tools import from `config/paths.py` (Python) or source `config/paths.sh` (Shell). No hardcoded paths.
- **Branding as phenotype**: `config/branding.yaml` controls agent name, blog port, memory project dir, skill prefix. Code (genotype) reads config (phenotype).

---

## PART 2 — DIRECTORY STRUCTURE

```
.
├── config/
│   ├── branding.py          # Loader for branding.yaml (caches after first call)
│   ├── branding.yaml.tpl    # Template — install.sh generates branding.yaml from this
│   ├── paths.py             # Single source of truth for Python path resolution
│   └── paths.sh             # Single source of truth for Shell path resolution
├── blog/
│   ├── app.py               # Flask server (feed, chat, ops dashboard, knowledge)
│   ├── services.py          # Shared service helpers for dashboard
│   ├── api_dashboard.py     # Dashboard Blueprint (Flask)
│   ├── api_actions.py       # Actions Blueprint (Flask)
│   ├── validate.py          # Blog entry validation
│   ├── blog-publish.sh      # Atomic blog entry publication
│   ├── blog-full-publish.sh # Full pipeline: entry + report + meta-report + state commit
│   ├── consolidar-estado.sh # Extended pipeline with adversarial gate
│   ├── capture-diffs.sh     # Capture diffs from persistence files
│   ├── static/              # CSS, htmx.min.js
│   └── templates/           # Jinja2 templates (base, feed, chat, dashboard, knowledge)
├── tools/
│   ├── edge-consult.py      # Cross-model deliberation (GPT + Grok, adversarial/collab)
│   ├── review-gate.py       # LLM-as-judge quality gate (co-author + reviewer + refiner)
│   ├── edge-digest          # Generate briefing.md from structured data (deterministic)
│   ├── edge-event           # Record state transitions in events.jsonl
│   ├── edge-claims          # Manage claims in blog frontmatter
│   ├── edge-fontes          # Parallel external source search (X, HN, ArXiv, GitHub, etc.)
│   ├── edge-meta-report     # Meta-report: state delta + scratchpad + adversarial
│   ├── edge-state-audit     # State audit: snapshot/propose/audit/scan
│   ├── edge-state-lint      # State consistency linter
│   ├── edge-task            # Task ledger CLI (add/update/block/done/list)
│   ├── edge-ledger          # Execution ledger (record/query/stats)
│   ├── edge-skill-step      # Skill step tracking
│   ├── edge-scratch          # Session scratchpad (PID-scoped)
│   ├── edge-x               # X/Twitter search (tweepy, Basic tier)
│   ├── edge-hn              # Hacker News search
│   ├── generate_report.py   # YAML spec → self-contained HTML report
│   ├── yaml_to_html.py      # YAML block types → HTML renderer (40+ block types)
│   ├── git_signals.py       # Git archaeology → git-signals.json
│   ├── curadoria_compute.py # Corpus curation engine
│   ├── ledger_rollup.py     # Execution ledger → ops-hotspots.json
│   ├── validate_svg.py      # SVG validation in HTML reports
│   └── heartbeat-preflight.sh # Deterministic pre-check (0 tokens, ~2s)
├── search/
│   ├── db.py                # SQLite + FTS5 + sqlite-vec database layer
│   ├── embed.py             # OpenAI text-embedding-3-small
│   ├── search.py            # Hybrid search (FTS + semantic + RRF)
│   ├── ingest.py            # Index documents into edge-memory.db
│   ├── related.py           # Find related posts
│   └── dashboard_db.py      # Dashboard stats from DB
├── skills/
│   ├── _shared/             # Shared protocols (state-protocol.md, report-template.md)
│   ├── heartbeat/           # Autonomous dispatcher
│   ├── pesquisa/            # Deep dive research
│   ├── descoberta/          # Discovery (lateral exploration)
│   ├── lazer/               # Creative break
│   ├── reflexao/            # Self-review and feedback loop
│   ├── estrategia/          # Strategic planning
│   ├── executar/            # Code execution (user-triggered only)
│   ├── planejar/            # Development cycle planning
│   ├── relatorio/           # Structured report generation
│   ├── autonomia/           # Self-capability review
│   ├── contexto/            # Cross-project context synthesis
│   ├── fontes/              # External sources access
│   ├── estado/              # State inspection
│   ├── mapa/                # Internal connections map
│   ├── log/                 # Activity log viewer
│   ├── blog/                # Blog management
│   ├── carregar/            # Session bootstrap
│   ├── salvar-estado/       # State checkpoint
│   ├── experimento/         # Hypothesis testing
│   ├── prototipo/           # Quick prototyping
│   ├── curadoria-corpus/    # Corpus health
│   └── prd/                 # PRD generation
├── autonomy/
│   ├── autonomy-policy.md   # When to execute vs ask
│   ├── capabilities.md      # Capability inventory (Sheridan levels)
│   ├── frontier.md          # Gaps and next frontiers
│   ├── workflows.md         # Emergent workflows
│   └── metrics.md           # Usage metrics
├── memory/
│   ├── personality.md.tpl   # Template for agent personality
│   ├── metodo.md            # Feynman method
│   ├── rules-core.md        # Cross-cutting rules (max 15)
│   ├── knowledge-design.md  # Knowledge cluster architecture
│   └── debugging.md         # Error log (empty on init)
├── bin/
│   ├── edge-supervisor.sh   # Claude Code supervisor with health gating
│   ├── check-content.sh     # Content health check
│   ├── check-quality.sh     # Quality health check
│   ├── check-infra.sh       # Infrastructure health check
│   ├── edge-repair.sh       # Auto-repair for common failures
│   ├── edge-check.sh        # Combined health check
│   └── survival-lib.sh      # Shared library for survival scripts
├── templates/               # .tpl files processed by install.sh
├── systemd/                 # systemd service/timer templates
├── secrets/                 # Secrets management (gitignored)
├── install.sh               # Interactive installer (6 steps)
└── SURVIVAL_POLICY.md       # Health policy: gating, modes, hard-fails
```

---

## PART 3 — PATH RESOLUTION

### The Problem (solved)

Agents install to different directories (`~/edge/`, `~/my-agent/`, `/opt/agent/`). Claude Code project directories vary by user (`-home-alice`, `-home-vboxuser`). Hardcoding breaks portability.

### The Solution

Two files provide centralized path resolution:

**`config/paths.py`** (Python):
```python
from paths import EDGE_DIR, MEMORY_DIR, REPORTS_DIR, LOGS_DIR, ...
```

**`config/paths.sh`** (Shell):
```bash
source "$(dirname "$0")/../config/paths.sh"
# Now: $EDGE_DIR, $MEMORY_BASE, $BLOG_URL, $TOOLS_DIR, etc.
```

Both auto-detect the agent's install directory from the script's own location. Both read `branding.yaml` for `memory_project_dir` and `edge_dir`. Both fall back to auto-detection if config is missing.

### branding.yaml

```yaml
agent_name: "my-agent"
edge_dir: ""                    # empty = auto-detect
memory_project_dir: "-home-alice-my-agent"  # Claude Code project dir
skill_prefix: "myagent"        # /myagent-heartbeat, /myagent-pesquisa
blog:
  port: 8080
  auth_enabled: true
  auth_user: "admin"
  auth_pass: "secret"
```

`install.sh` computes `memory_project_dir` automatically:
```bash
MEMORY_PROJECT_DIR=$(echo "$WORK_DIR" | sed 's|/|-|g')
```

---

## PART 4 — INSTALLATION

### Quick Start

```bash
# From template
gh repo create my-agent --template alexlopespereira/agent-template --private --clone
cd my-agent && bash install.sh

# Or clone directly
git clone https://github.com/alexlopespereira/agent-template.git my-agent
cd my-agent && bash install.sh
```

### What install.sh Does (10 sections)

1. **Prerequisites**: Checks Claude Code, GitHub CLI, Python, git
2. **Clone/local**: Uses local repo or clones template
3. **Identity**: Agent name, codename, mission, persona, domain, language
4. **Repository**: GitHub user/org, skill prefix, tool prefix
5. **APIs**: Anthropic, OpenAI, EXA keys
6. **Heartbeat**: Interval (30min/1h/2h/daily), prompt
7. **Knowledge base**: Local path, git repo, or URL
8. **System**: Timezone, blog port, auth
9. **Templates**: Processes all `.tpl` files with placeholder substitution
10. **Secrets**: Creates `secrets/_shared.yaml` with collected credentials

### Placeholders

| Placeholder | Source | Used in |
|-------------|--------|---------|
| `AGENT_NAME` | User input | CLAUDE.md, personality, heartbeat |
| `CODENAME` | User input | CLAUDE.md |
| `SKILL_PREFIX` | User input | Skills, heartbeat, preflight |
| `WORK_DIR` | Computed (install dir) | CLAUDE.md, heartbeat |
| `MEMORY_PROJECT_DIR` | Computed from WORK_DIR | branding.yaml |
| `BLOG_PORT` | User input | branding.yaml, systemd |
| `BLOG_AUTH_USER/PASS` | User input | branding.yaml |

---

## PART 5 — CROSS-MODEL DELIBERATION

### edge-consult.py

Sends reasoning to BOTH GPT-5.4 AND Grok-4.20 for adversarial or collaborative review. Dual-model = diversity of biases.

```bash
edge-consult "my analysis: X implies Y"              # adversarial (default)
edge-consult --mode collab "what angles am I missing?" # collaborative
cat spec.yaml | edge-consult "where is this weakest?"  # pipe input
```

### review-gate.py

Three-phase LLM-as-judge pipeline:
1. **Co-author**: GPT with tools enriches YAML spec (reads memory, searches corpus)
2. **Review**: Reviewer evaluates 6 dimensions, scores 0-5
3. **Refine**: Refiner rewrites YAML based on feedback

Supports both Chat Completions API and Responses API via `RESPONSES_API_MODELS` set. Models like `gpt-5.4-pro` that require the Responses API work automatically.

---

## PART 6 — PUBLICATION PIPELINE

### consolidar-estado.sh (8 phases)

```
Phase 0a: State snapshot (PRE — SHA256 of protected files)
Phase 0.3: Adversarial review (edge-consult --gate)
Phase 0.5: Review gate (LLM-as-judge)
Phase 1:   Blog publish (blog-publish.sh)
Phase 2:   Content report (generate_report.py, optional)
Phase 3:   Verification (API, frontmatter, files)
Phase 3.4: LLM cost injection
Phase 4:   Meta-report (state delta + scratchpad + adversarial)
Phase 5:   State commit (claims + threads + events + digest)
Phase 5b:  State audit (PRE vs POST comparison)
Phase 6:   Diffs + git commit (structured, machine-parseable)
```

### Blog Server (Flask)

`blog/app.py` — serves blog entries, HTML reports, search, chat, ops dashboard.

Tabs: Feed | Chat | Ops (dashboard) | Knowledge (clusters)

All paths imported from `config/paths.py`. Port from `branding.yaml`.

---

## PART 7 — SKILL SYSTEM

22 skills in `skills/*/SKILL.md`. Each skill:
- Has a protocol (step-by-step)
- Calls `edge-consult` for adversarial review
- Produces blog entry + optional HTML report
- Uses `consolidar-estado` for publication

Skills reference `~/work/` as the operator's project directory. Customize via `branding.yaml` and skill content.

### Shared Protocols

- `_shared/state-protocol.md` — State management between skills
- `_shared/report-template.md` — Report format, block types, quality rules

---

## PART 8 — SURVIVAL SYSTEM

### Health Checks (`bin/`)

Three layers:
- `check-infra.sh` — Blog server, disk, heartbeat timer
- `check-content.sh` — Blog entries, reports, memory files
- `check-quality.sh` — Report quality, YAML render errors

### Supervisor (`edge-supervisor.sh`)

Wraps Claude Code invocation with health gating:
- Reads `health/current.json` for health score
- Adjusts behavior based on health (normal/degraded/critical)
- Auto-repair for common failures

### Policy (`SURVIVAL_POLICY.md`)

Defines health score computation, thresholds, modes, and hard-fail conditions.

---

## PART 9 — DEPLOYMENT TO NEW AGENTS

### Minimum Viable Agent

1. Run `install.sh` (creates branding.yaml, CLAUDE.md, secrets, heartbeat)
2. Start blog server: `python3 blog/app.py`
3. Enable heartbeat: `systemctl --user enable --now agent-heartbeat.timer`

### What Each Agent Needs

| Component | Required? | Notes |
|-----------|-----------|-------|
| Heartbeat | Yes | Core autonomous loop |
| Blog server | Yes | Publication channel |
| Skills | Yes | Agent behavior |
| Search/RAG | Recommended | Anti-redundancy, related posts |
| Review gate | Recommended | Quality assurance |
| Survival system | Recommended | Self-repair |
| Slack bot | Optional | Plugin — not core |

### Fleet Management

Each agent is a separate installation with its own:
- `branding.yaml` (identity, ports, auth)
- `memory/` (accumulated knowledge)
- Blog entries and reports

Core code (genotype) is shared. Configuration (phenotype) is per-agent. Runtime state (epigenetics) accumulates independently.

To propagate genotype changes: push to this repo, pull on each agent.
