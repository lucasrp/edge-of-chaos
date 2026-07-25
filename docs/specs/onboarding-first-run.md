# Spec — Onboarding first-run (sem agent.yaml; yaml = output)

**Normative freeze of the approved plan (2026-07-19).** Supersedes #136’s “inject agent.yaml at provision” for the first-run path: phenotype is **emitted after mentor**, not required at install.

## Arc

```
secrets/ delivered by operator
  → edge-bootstrap (no --yaml)
  → assemble (lookback N days) + wake (insumo)
  → mentor (Direction born here)
  → emit agent.yaml + ignition (heartbeat may enable)
```

Beat/heartbeat are **refused** until onboarding is complete. Assemble + wake are **allowed** during onboarding (structure, not production).

## Install knobs (bootstrap)

| Knob | Required | CLI / env | Lands in |
|------|----------|-----------|----------|
| Agent name | **yes** | `--name` / `EDGE_AGENT_NAME` | `name`, `codename`; `graph_group` unless `EDGE_GROUP` |
| Assemble lookback days | **yes** | `--backfill-days N` / `EDGE_ASSEMBLE_BACKFILL_DAYS` | `lentes.backfill_days` |
| Adversarials cast | no (has fallback) | `--adversarial X` repeatable | `adversarials` + `routers.review*` |
| Embeddings key | **no** | present in `secrets/` | `routers.embedding` only if key found |
| Install home | **yes** | `--home` / `EDGE_HOME` | `edge_home` |

**Adversarials fallback:** if no other reviewer is configured or available, **the primary model runs self-adversarial**. Never zero review in silence.

**Secrets path:** `$EDGE_HOME/secrets/` (or `EDGE_SECRETS_DIR`). Bootstrap / assemble / wake / onboarding **read** it (names only in logs). Installer never fetches keys.

Pre-phenotype state: `state/bootstrap.json`.

## Mentor insumo (= wake package, no Direction)

Stamped at `state/onboarding-insumo.md` after assemble+wake:

1. Header: `name`, `lookback_days`, adversarials cast, embedding on|dark  
2. Assemble (inicial, over N-day window)  
3. Secrets inventory  
4. Delta de secrets  
5. Quente (always a chapter; dark ok)  
6. Delta (mundo/sessões)  
7. Recall  
8. **No Direction** (empty-on-fresh; born in mentor)

## Complete predicate

`is_onboarding_complete` when:

- `grill_gate.grill_complete(log) == []` (objective + direction + direcionamento + leveling)
- phenotype `agent.yaml` exists and is thick enough (`name`, `lentes.backfill_days`, …)

Then production (beat/heartbeat) may run.

## Dual-mode

Existing installs with `agent.yaml` keep the legacy apply path. Bootstrap path only when phenotype is absent.

## Multi-CLI (Claude + Codex + Grok)

Install detects which harness homes exist on the host (`~/.claude`, `~/.codex`, `~/.grok`) and:

1. **Provisions skills** into every installed harness (`ed-*` + `edge-*` prefixes).
2. Writes phenotype `surfaces:` enabling those harnesses.
3. **Assemble / sweep / quente** film sessions from every installed surface (not Claude-only).

Same code path on ed, roberto, petertosh — whatever CLIs are present get install + film.
