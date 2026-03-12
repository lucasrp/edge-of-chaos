# Tag and Keyword Vocabulary

Metadata schema for reports, blog entries, notes, and memory artifacts.
Evolves over time — add terms as they arise, consolidate during reflection.

## Schema

```yaml
tags: [type, domain, concept]      # 3-5, controlled vocabulary, for FILTERING
keywords: [tech, concept, ref, ...]  # 5-15, semi-free, for RETRIEVAL
```

**tags** = few, normalized, answer "what type? about which project? which theme?"
**keywords** = granular, answer "which technologies? which concepts? which references?"

## Tags — Controlled Vocabulary

### Type (inherited from the skill that generated the artifact)
research, reflection, planning, discovery, strategy,
break, training, report, retrospective, execute

### Domain (project/area)
_(customize per agent — add your project names here)_

### Concept (broad theme)
multi-agent, prompt-engineering, calibration, pipeline,
eval, observability, ux, memory

## Keywords — Retrieval Vocabulary

Canonical keyword first, aliases in parentheses.
Check before creating a new keyword — if the concept already exists, use the canonical.

### Technologies
_(add as you encounter them — format: canonical (alias1, alias2))_

### Technical Concepts
- structured-extraction (json-extraction)
- semantic-compression
- prompt-specialization (multi-persona, persona-prompts)
- eval-pipeline (evaluation-pipeline)
- golden-set (ground-truth, test-set, benchmark)
- implicit-feedback (user-signals)
- data-flywheel (flywheel, improvement-loop)
- circuit-breaker (circuit-breakers, safety-patterns)
- rag (retrieval-augmented-generation)
- streaming (streaming-llm, server-sent-events, sse)
- routing (agent-routing)
- handoff (agent-handoff)
- theory-of-constraints (toc, bottleneck)

### References (people, theories)
- feynman (feynman-method, first-principles)
- turing (turing-patterns, turing-machine)

## Format in Artifacts

### Blog entries (YAML frontmatter)
```yaml
---
title: "..."
date: YYYY-MM-DD
tags: [research, project-name, concept]
keywords: [tech1, tech2, concept1]
report: YYYY-MM-DD-slug.html
---
```

### Reports (YAML header)
```yaml
title: "..."
subtitle: "..."
date: "DD/MM/YYYY"
tags: [research, project-name, concept]
keywords: [tech1, tech2, concept1]
```

## Rules

1. **Check this file** before creating a new keyword
2. **Type tag is mandatory** — every artifact has at least one
3. **Keywords are case-insensitive** — always lowercase, hyphenated
4. **Don't retroact** — apply going forward, don't update existing artifacts
5. **Evolve** — add terms when they arise, consolidate duplicates during reflection
6. **Centralized index** — future (INDEX.json), when volume justifies it
