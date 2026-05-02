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
what you assumed in the final artifact. Do not close by listing candidate
topics and asking the operator to choose when the runtime frame contains enough
signal to pick one. Ask the operator only when no defensible research target can
be inferred, required access is missing, or the next step requires an
external/destructive mutation rather than research.

## Boundary

Do not manage lifecycle, publication, postflight, or generic artifact rites inside this skill.
Do use the shared uniform report pipeline as the publication path for every
research deliverable. A stdout-only research answer is not a completed
`/ed-research` run. Before drafting, read `skills/_shared/report-template.md`
from the active edge repo, write a YAML report spec and a light staging blog
entry in `/tmp`, validate both files as described there, then run
`consolidate-state` so the research becomes a durable blog entry, HTML report,
and meta-report. Quote frontmatter claims as complete YAML strings whenever
they contain `:`, `!`, backticks, quotes, or other YAML-significant punctuation.
If a gate blocks, address the specific feedback and rerun `consolidate-state`.
Do not close by asking the operator whether to publish, by recommending a future
publication pass, or by handing off with only prose or staging files. If
publication cannot complete, surface the concrete failing command and reason
instead of reporting success.

## Research Method

### 1. Scope The Target

If the user supplied a topic or problem, use it directly.

### Bare Invocation / Missing Topic

A bare `/ed-research` dispatch is already authorization to choose one concrete
research target. Do not end the skill by asking the operator which topic to use
when the injected runtime frame contains plausible candidates.

If no argument was supplied:

1. Inspect `delta_prerequisite`, `beat_launch_context`,
   `operator_pressure_digest`, `health_snapshot`, `claims_summary`,
   `exploration_pack`, recent pipeline failures, stale claims, and current
   git/runtime drift.
2. Infer 1-3 concrete research targets from current context friction.
3. Select the highest-leverage target with enough evidence to study now.
4. State the inferred target and why it was selected.
5. Produce and publish the research artifact through `consolidate-state`.

Ask the operator for a target only when the runtime frame contains no reasonable
candidate and any inferred research would be misleading. That should be rare.

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
The artifact is complete only after `consolidate-state` succeeds and the
generated HTML report, blog entry, and meta-report have been verified. The final
chat response should summarize the published paths and key finding; it must not
be the only place where the research exists.

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
