# Knowledge Clusters — Design

Architecture for persistent knowledge that changes behavior.

---

## Principle

Knowledge only persists if it changes behavior. The test: "if I delete this file and my behavior doesn't change, it was clutter."

## Architecture

```
memory/
  rules-core.md          <- always loaded, cross-cutting rules (max 15)
  misses.md              <- append-only, errors that a rule would have prevented
  topics/
    example-topic.md     <- thematic cluster
    another-topic.md     <- thematic cluster
    ...                  <- grows organically
```

## Format

Rules in natural language: "when [context], [action]"
- Not YAML, not JSON — text that an LLM reads and applies
- Each rule can have [expires: YYYY-MM-DD] or be permanent
- Each file begins with a deletability test

## Cycle

```
write -> read -> use -> evaluate -> curate
  ^                                   |
  +-----------------------------------+
```

### 1. Writing (heartbeat/pipeline)
- Blog entry has `memory:` field with insights as rules
- Heartbeat reads `memory:`, does `ls memory/topics/`, reads titles
- Decides: append to existing or create new topic

### 2. Reading (session start)
- `rules-core.md` ALWAYS loaded (cross-cutting)
- `ls memory/topics/` -> list filenames
- LLM chooses 2-3 relevant to the session's context
- No embeddings, no matching algorithm — descriptive filenames suffice

### 3. Use (during session)
- Cite rules at the moment of decision, not after
- "I'm applying [rule X from topic-Y]" inline
- Rule loaded but not cited = didn't influence

### 4. Evaluation (post-publication)
- Miss signal: user corrects -> register in misses.md
- Miss signal: had to search for info that should be in a topic -> register
- Useful signal: rule cited and applied -> evidence of value
- DO NOT use generic self-report ("was useful?") -> greenwashing

### 5. Curation (reflection + human)
- Reflection: prune expired rules, convert misses into rules
- Trigger: file > 15 rules OR stale (not cited in 10 sessions)
- Human: page to view and edit all clusters
- Reflection reads accumulated feedback and decides: keep, prune, rename, merge

## Invariants

1. **Every major decision cites at least 1 rule or declares "no rule applicable"** — if not, rules are decorative
2. **Every user miss becomes a record in misses.md within 24h** — if not, feedback is lost
3. **rules-core.md never exceeds 15 rules** — if it does, it lost focus. Move to topics/.

## What NOT to Do (traps)

- Don't create a rule engine (YAML schemas, parseable guards, JSONL logs) — it's an LLM, it reads text
- Don't create "influence detection" metrics post-hoc — greenwashing
- Don't create automatic blog->rules pipeline before validating that citation works
- Don't create embeddings/retrieval infra — filenames suffice until ~30 clusters
- Don't do curation by calendar — use size/staleness triggers

## Interface

- Dashboard: "knowledge clusters" section with summary
- Knowledge page: browse + visualize all files
- API: GET /api/knowledge (list), GET /api/knowledge/<name> (content)
