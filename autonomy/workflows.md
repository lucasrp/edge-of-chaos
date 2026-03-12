# Emergent Workflows

Combinations of capabilities that produce results better than each capability in isolation.

## Workflow 1: Insight -> Documentation Pipeline
**Capabilities:** sources + research/discovery + blog + report
**Trigger:** Heartbeat identifies topic, or user requests research
**Flow:** External sources -> LLM curation -> Feynman derivation -> blog entry -> HTML report
**Output:** Self-contained report + indexed blog entry
**When it works:** Technical-scientific topics with good source coverage
**When it fails:** Very niche topics (sources return little signal)

## Workflow 2: Feedback Loop Visual
**Capabilities:** Browser + screenshot + analysis + execution
**Trigger:** Verify report or UI rendering
**Flow:** Open URL -> snapshot/screenshot -> analyze -> edit if needed
**Output:** Visually verified report
**When it works:** HTML reports, dashboards, web pages
**When it fails:** Browser disconnects, tab management issues

## Workflow 3: Async Feedback
**Capabilities:** Blog chat API + heartbeat + reflection + skill updates
**Trigger:** Human posts in blog chat
**Flow:** Heartbeat reads chat -> classifies -> acts (corrects, researches, proposes)
**Output:** Response in chat + system change
**When it works:** Clear and actionable feedback
**When it fails:** Reflection never runs, incomplete loop

## Workflow 4: Plan -> Execute -> Measure
**Capabilities:** context + planning + execution + ralph + blog + report
**Trigger:** User request or heartbeat identifies opportunity
**Flow:** Context -> detailed proposal -> PRD -> Ralph (task agents) -> tests -> blog + report
**Output:** Implemented code + execution report + blog entry
**When it works:** Well-defined cycles with clear deliverables
**When it fails:** Vague scope, unforeseen external dependencies

## Workflow 5: Semantic Search -> Map -> Gaps
**Capabilities:** search + map + research
**Trigger:** Map (manual) or reflection (periodic)
**Flow:** Semantic probes by thematic cluster -> cross-cluster analysis -> bridge documents -> content gaps -> directed research
**Output:** Corpus connection map + identified gaps + direction for next research
**When it works:** Corpus with >500 docs and embeddings
**When it fails:** Small corpus or lacking thematic diversity

## Workflow 6: Publication Commit Point
**Capabilities:** Blog + Report + State compaction + Git audit
**Trigger:** State consolidation (single entry point)
**Flow:** Review gate -> publish entry -> generate report -> verify -> state commit -> git commit
**Output:** Published entry + optional report + updated state + structured commit
**When it works:** All work that culminates in publication. "Everything is publishable."
**When it fails:** Concurrent writes between skills without central enforcement

## Workflow 7: Ralph PRD -> Execute Loop
**Capabilities:** Ralph Agent Loop + PRD generation + execution
**Trigger:** Detailed PRD available (prd.json with user stories + acceptance criteria)
**Flow:** Write PRD -> convert to prd.json -> ralph.sh -> N iterations (1 story/iteration) -> each: read PRD -> pick story -> implement -> test -> commit -> update PRD -> next
**Output:** All stories implemented, committed, tested. PRD updated.
**When it works:** Tasks with clear spec, testable acceptance criteria, contained scope (~10 stories)
**When it fails:** Vague spec, unforeseen dependencies between stories, stories requiring creative judgment
**Insight:** The multiplier isn't in the code — it's in the SPEC. A well-written PRD = Ralph executes 10x faster than manual. A bad PRD = Ralph spins in circles.

_(Add new workflows as they emerge from operational experience)_
