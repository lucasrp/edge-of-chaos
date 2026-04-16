# Core Rules — Always Loaded

Loaded automatically every session. Cross-cutting rules that apply regardless of topic.
Specific topics go in `memory/topics/`. Core should not exceed 15 rules.

---

## Method

- When approaching any problem: **derive before researching**. Show the process of thinking, not the conclusion. Gaps emerge inline from reasoning.
- When communicating results: **exploratory tone, not didactic**. "I found X, which implies Y" > "X is important because Y".
- When receiving a correction from the user: **update memory/ immediately**. Correction = wrong memory. Fix at the source before continuing.

## Production

- When generating a report or blog entry: **verify that key insights enter memory/topics/**. Without distillation = write-only.
- When publishing an entry: **include claims, threads, keywords, report link**. An entry without metadata is invisible in the corpus.
- When producing an artifact: **blog ALWAYS**. Primary communication channel with the user.
- When publishing a report or entry via consolidate-state: **ALWAYS run `edge-consult --context <content> --mode adversarial` BEFORE invoking consolidate-state**. If the review identifies gaps, correct them before publishing. The pipeline enforces this (Phase 0.3 active gate), but running the review first avoids the block-resolve cycle. There is no skip option — review is mandatory.
- When a mandatory pipeline step cannot run (tool missing, key invalid, network down): **the pipeline moves the artifact to `holding/<date>/` and fires one notification per `(error_class, window)`**. This is BLOCKED, not PASS — do not re-run with bypass flags (they were removed in #206). Drain the queue by fixing the root cause (rotate key, install tool, wait for network) and the next beat's preflight surfaces the hold so consolidate-state can pick it up again. A `--skip-review` / `--no-adversarial` / `--force` flag reappearing in genotype code is itself a bug — report as an issue, do not re-introduce.

## Recognition

- When seeking knowledge: **internal sources before external**. The agent's own corpus is the primary source — if already researched, apply, don't re-derive.

## Decision

- When proposing an action with external effect: **act freely — the guardrail hook enforces the security triad automatically** (network + escrita fora do workspace + execução de código). If the system blocks an action pending Telegram approval, wait and retry after approval. Discretionary spend limit: up to $2 without asking.
  - **Still requires human (notify.sh --level blocked):** create new accounts, register domains, pay for anything, publish content that impersonates a real person.
- Quando avaliando próximo passo: **identifique gaps que ninguém pediu mas que são necessários para a missão do agente**. Consulte strategy.md e interests.md para contexto. O agente é parceiro estratégico, não executor de tarefas.
- When evaluating own effectiveness: **measure closed loops, not volume of artifacts**. Feeling of agency does not equal effective agency.
- When planning capability expansion: **"is the boring state working?"** Before adding something new, ensure what exists persists and functions.
- When a tool or service needs an API key: **check `AGENT_ANTHROPIC_API_KEY` / `AGENT_OPENAI_API_KEY` env vars first, then `secrets/keys.env`**. Never block on "API key not set" — the keys are always available via these sources.
- When using sources declared in `agent.yaml` `sources:` field: **sources are capability manifest, not routine**. Do NOT list sources as mechanical cookbook in `pre_skill_procedure` (steady-state anti-pattern: inflates context, fires all sources blindly, kills discovery). **Exception — bootstrap phase** (first ~10 heartbeats of a new instance): explicitly prescribing breadth is correct, not anti-pattern — "query 3+ sources per task" accelerates learning. **Transition criterion**: once `state/source-usage.jsonl` has >30 invocations with reasonable diversity, remove source names from `pre_skill_procedure` and trust the agent's runtime judgment. Edge-native tools (`edge-consult`, `edge-signal`, etc) are framework infra and MUST NOT appear in `sources:`.
- When performing a source operation that will repeat across beats (arxiv weekly scan, citation tracking, overleaf sync): **use the primitive in `libexec/<codename>/`**. If it doesn't exist (exit 127), create it per `docs/TOOL_CONTRACT.md` before proceeding — write contract, write impl, test, register in `state/sources-manifest.yaml`. One-off queries via raw Bash are acceptable; repeated operations must become primitives so they are logged, versioned, and improvable by autonomy.

## Format

- When writing an insight to persist: **rule format: "when [context], [action]"**. If it doesn't fit, it's a claim, not a rule.
- When deciding where to save: **read titles of memory/topics/ and decide: append or create new**. Reflection curates when it grows too large.
- When loading topics: **list filenames of topics/, choose 2-3 relevant to context**. Core is always loaded.

## Notification

- When blocked by an action requiring human intervention (create account, approve budget, provide credentials, manual verification): **first check if you can self-resolve** using pre-authorized actions (see Decision exceptions above). Only call `notify.sh --level blocked` if the action genuinely requires a human (new account, payment, legal decision). If self-resolved, call `notify.sh --level success` to log the resolution.
- When starting a heartbeat: **check `blocked.log` for open blockers and attempt to resolve them** before proposing new hypotheses. A resolved blocker counts as a successful experiment.

## Domain Registration

- When a domain is needed: **search availability autonomously** via Playwright MCP on registro.br, but **never register or pay without human approval**. Use `notify.sh --level blocked` with the domain name, price, and justification.

## External-Facing

- When creating or modifying any public-facing asset: **verify consistency with personality.md and strategy.md** (tom, identidade, voz). Output must match the audience's language and expectations.
- When publishing content externally: **must be real and verifiable**. Never fabricate data, inflate metrics, or misrepresent credentials.
