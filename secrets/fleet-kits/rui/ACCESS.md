# Rui — Access & Setup Instructions

## Environment

- **User:** `vboxuser`
- **Home:** `/home/vboxuser`
- **Edge dir:** `/home/vboxuser/edge` (symlink: `~/edge`)
- **OS:** Linux (VirtualBox guest)
- **Shell:** bash

## Credentials

All credentials are in `keys.env` (same directory as this file). Source it:

```bash
source ~/edge/secrets/fleet-kits/rui/keys.env
```

### What's available

| Key | Service | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | OpenAI | GPT-5.4 via edge-consult (adversarial review) |
| `EXA_API_KEY` | Exa | Semantic web search via edge-sources |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare | Account: `a0d284dc4c75066bae6b7ad1535e37a7` |
| `CLOUDFLARE_API_TOKEN` | Cloudflare | Zones: acessoverde.com, edgeofchaos.net, edgesofchaos.org. Has DNS read/write. |
| `X_API_KEY` + secrets | X/Twitter | Basic tier ($200/mo, 15K reads). Used by edge-x. |
| `X_BEARER_TOKEN` | X/Twitter | Bearer token for search API. |
| `MOLTBOOK_API_KEY` | Moltbook | Social network for AI agents. Agent ID: `de9d4322-1321-4823-9653-507de9dc8df8` |
| `BLOG_AUTH_USER/PASS` | Blog dashboard | `admin` / (empty) — local access only |
| `ANTHROPIC_API_KEY` | Anthropic | (empty — provided by Claude Code session) |

## GitHub

- **Account:** `lucasrp` (fine-grained PAT scoped to `lucasrp/edge-of-chaos`)
- **SSH alias:** `github-edge-of-chaos`
- **Repo:** `lucasrp/edge-of-chaos`

## Key Paths

| Path | What |
|------|------|
| `~/edge/` | Main repo — blog, tools, reports, notes, skills |
| `~/edge/blog/entries/` | Blog entries (markdown + YAML frontmatter) |
| `~/edge/reports/` | HTML reports |
| `~/edge/tools/` | CLI tools (edge-x, edge-consult, etc.) |
| `~/edge/secrets/` | All credentials (gitignored) |
| `~/edge/config/` | Agent config (strategy.md, pre-skill.md, etc.) |
| `~/edge/health/` | Health check data |
| `~/.claude/skills/` | Skill definitions (ed-research, ed-heartbeat, etc.) |
| `~/.claude/projects/-home-vboxuser/memory/` | Persistent memory (MEMORY.md, rules-core.md, etc.) |

## Blog / Dashboard

```bash
# Blog runs on port 8766
curl http://localhost:8766/blog/
```

## Key Tools

```bash
edge-x "topic"                    # X/Twitter search
edge-x "topic" --light            # Budget-friendly mode (2 API calls)
edge-consult "question"           # Adversarial review (GPT-5.4 + Grok)
edge-search "query" -k 5          # Semantic search in corpus
edge-index ~/edge/notes/file.md   # Index a file
consolidate-state entry.md        # Publish pipeline (blog + report + meta)
review-gate spec.yaml --skill X   # LLM-as-judge quality gate
```

## Shared with

Same credentials as `donald` and `bob`. All three agents share:
- Same machine (vboxuser@localhost)
- Same edge repo
- Same API keys
- Same blog/dashboard

## Notes

- `ANTHROPIC_API_KEY` is empty in keys.env — it's injected by the Claude Code session via `AGENT_ANTHROPIC_API_KEY` env var
- TCU GitHub account (`lucasrp_TCU`) is deliberately logged out — no gov repo access
- Cloudflare token was refreshed 2026-03-27 — old token is invalid
