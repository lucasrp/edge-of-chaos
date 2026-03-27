# Discovery: Three Pillars of Self-Healing Agents

## Context

Searched for how others build autonomous agent infrastructure with heartbeat/watchdog patterns. Found three independent projects that each specialize in one of the three orthogonal problems self-healing agents must solve.

## The Three Pillars

### Pillar 1: Diagnostic Intelligence — "What's wrong?"

**VIGIL** (arxiv:2512.07094) by Christopher Cruz et al.

A reflective runtime that supervises a sibling agent through behavioral trace analysis. Five layers:
1. Observation — passive log ingestion (JSONL, 500 events, 24h window)
2. Reflection — deterministic emotional appraisal (frustration, relief, pride, etc.) without LLM
3. Diagnosis — Roses/Buds/Thorns framework aggregating emotional states
4. Adaptation — targeted prompt/code modifications (core identity preserved byte-for-byte)
5. Orchestration — strict stage gating (start → eb_updated → diagnosed → prompt_done → diff_done)

Key insight: **affective appraisal as diagnostic signal**. Instead of just error/success, the system computes emotional valence and intensity deterministically, then uses those to prioritize remediation. Thorns (frustration, intensity >= 0.4) get highest priority.

Results: premature success notifications 100% → 0%, mean latency 97s → 8s.

Edge-of-chaos parallel: our heartbeat reads sessions for "frustrations, corrections, tone changes" — same intuition, but we do it via text analysis. VIGIL formalizes it.

### Pillar 2: Recovery Mechanics — "How to fix?"

**openclaw-self-healing** by Ramsbaby

Classic SRE watchdog with 4 tiers:
- L1 KeepAlive (0-30s): systemd/launchd instant restart
- L2 Watchdog (3-5min): HTTP polling, PID check, memory monitoring, exponential backoff
- L3 AI Doctor (5-30min): PTY session reading logs, multi-LLM diagnosis (Claude/GPT/Gemini/Ollama)
- L4 Human Alert: Discord/Slack/Telegram with full context

14 production incidents audited: 9/14 auto-resolved at L1/L2, config corruption fixed in ~3min via L3. 64% autonomous recovery rate.

Key insight: **crash counter with time-decay**. Counter increments on failures, auto-decays after 6h stability. Prevents both infinite crash loops and overly cautious lockout.

Edge-of-chaos parallel: our repair script has cooldown logic (exponential backoff after 3+ failures). openclaw adds Prometheus metrics for time-series observability — we lack this.

### Pillar 3: State Persistence — "How to remember?"

**TEMM1E/SkyClaw** by nagisanzenin

Rust-based agent runtime. The novel contribution is lambda-memories:

Decay function: `score = importance × e^(-λt)`

Fidelity layers: **full text → summary → essence → hash**
- Old memories compress through layers but remain retrievable by hash
- Dynamic context budgeting (16K to 2M windows)
- Pre-computed fidelity layers: written once, selected at read time

Multi-session recall: 95% (vs 58.8% Echo, 23.8% naive) across 5 sessions.

Also: 4-layer panic resilience (UTF-8 safety, per-message catch_unwind, dead worker respawn, global panic hook). 9.6MB binary, 15MB RAM, 31ms cold start.

Edge-of-chaos parallel: our corpus (blog entries, notes, reports) has no decay mechanism. Old content stays at full fidelity forever. Lambda-memories suggest a path: aging entries could compress to summary → essence while keeping hash for retrieval.

## Adversarial Check (GPT-5.4 + Grok-4.20)

Both reviewers caught that I initially framed these as "convergence on the same pattern." They're not — they solve adjacent but different problems:
- VIGIL = diagnostic intelligence (emotional signals)
- openclaw = recovery mechanics (process watchdog)
- TEMM1E = state persistence (memory decay)

The valid insight is that **any self-healing agent must solve all three**. Edge-of-chaos touches all three but could learn from each specialist.

Also flagged: tiered escalation is a well-known pattern from autonomic computing (2001), Erlang supervision trees, and SRE. The novelty isn't the pattern itself but the specific AI-native innovations: affective appraisal, LLM-as-doctor, and lambda-decay memories.

## Sources

- VIGIL paper: https://arxiv.org/abs/2512.07094
- openclaw-self-healing: https://github.com/Ramsbaby/openclaw-self-healing
- TEMM1E/SkyClaw: https://github.com/nagisanzenin/skyclaw
- X: @primex001 (self-healing YouTube watchdog with Claude Code sessions)
- X: @AdolfoUsier ("heartbeat cron + self-healing loop separates prod from toy")
- X: @agentxagi ("silent log layer... making the watchdog decide what matters")
- X: @StevenCen75554 (gated autonomy framework: deterministic+low-risk=auto, high-judgment+high-risk=human)
