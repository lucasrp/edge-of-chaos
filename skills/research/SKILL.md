---
name: ed-research
description: "Deep dive research on a specific topic or problem. Directed study with actionable output. Triggers on: research, pesquise, estude, deep dive, aprofunde, feynman, entenda, derive, first principles, explique de verdade, explain for real."
user-invocable: true
---

# Research — Directed Deep Dive

Use this skill when the target is known and the job is to understand it deeply enough to decide what to do.

Unlike `ed-discovery`, which explores freely, `ed-research` starts from a question, topic, or problem.

Examples:

- `/ed-research DSPy`
- `/ed-research how to reduce token cost`
- `/ed-research pipeline patterns`

## Method

Research always uses Feynman mode.

Produce a self-contained explanation first, then derive recommendations from that understanding.

Feynman cycle:

1. Derive first from scratch.
2. Mark where reasoning stalls as `[GAP: ...]`.
3. Research only the gaps.
4. Teach the concept plainly, with mechanics and limits.
5. Re-read and mark remaining `[STILL DON'T UNDERSTAND: ...]` gaps.

Run at most two gap-resolution loops before publishing the remaining uncertainty.

Do not pause after the first gap pass to ask whether to continue. A direct
`/ed-research` dispatch already authorizes the bounded Feynman cycle. If the
topic is underspecified, infer a reasonable scope from current context and say
what you assumed in the final artifact. Ask the operator only when the target
cannot be inferred enough to begin, required access is missing, or the next
step requires an external/destructive mutation rather than research.

## Boundary

Do not manage lifecycle, publication, postflight, or generic artifact rites inside this skill.

## Research Method

### 1. Scope The Target

If the user supplied a topic or problem, use it directly.

If no argument was supplied, infer 1-3 concrete research targets from current context friction.

Prefer targets with practical downstream value:

- prompt and evaluation quality;
- code quality and refactoring safety;
- tooling and ecosystem choices;
- architecture and pipeline patterns;
- applied domain knowledge needed for current projects.

### 2. Check Existing Knowledge

Search the internal corpus before external research:

```bash
edge-search "[research topic]" -k 8
```

Use complementary searches when the topic has multiple facets:

```bash
edge-search "[technical facet]" -k 5 --type note
edge-search "[conceptual facet]" -k 5 --type report
```

Use prior work to decide whether this is:

- an update to known material;
- a deeper pass on a superficial topic;
- a new area with no useful antecedent.

The final output should state what existing material was found and how it changed the scope.

### 3. Investigate

Research with depth, not breadth.

Look for:

- concrete mechanisms;
- recent or authoritative sources;
- real examples and benchmarks;
- failure modes and limitations;
- trade-offs between alternatives;
- implications for current projects.

For external context, use the source/search capability appropriate to the question. Cite URLs, repositories, papers, docs, posts, or other source identifiers in the final artifact.

### 4. Synthesize

Synthesis must include:

- the actual question researched;
- what prior corpus knowledge already said;
- initial derivation;
- gap list;
- what resolved each gap;
- discoveries organized by insight, not by source;
- plain-language explanation;
- actionable recommendations with concrete implementation detail;
- applications to current work;
- risks, caveats, and open questions;
- next steps.

## Quality Criteria

- Recommendations must be executable, not vague. Prefer "install X, configure Y, expect Z" over "consider X".
- Each important concept should be explained with a practical definition and an analogy.
- Each technical mechanism should include a concrete input-to-output example when possible.
- Each recommendation should show before/after or "how it is / how it would be".
- Do not hide uncertainty. Mark weak evidence, disagreement between sources, and unresolved gaps.
- Do not rediscover previous work without saying what changed.

## Output Contract

Produce a research artifact suitable for the uniform report pipeline.

Recommended sections:

1. Research Target
2. Existing Knowledge
3. Initial Derivation
4. Gaps and Resolutions
5. Explanation
6. Recommendations
7. Applications to Work
8. Risks and Open Questions
9. Next Steps
10. References

## Privacy Rule

For external posts or public communication, do not identify private organizations, owners, project names, or data that can trace the human operator.
