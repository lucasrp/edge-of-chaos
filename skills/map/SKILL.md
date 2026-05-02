---
name: ed-map
description: "On-demand map of internal connections between ideas, projects, tools, claims, workflows, discoveries, and data sources. Triggers on: map, connections, what connects to, como se relaciona, mapa."
user-invocable: true
---

# Map — Internal Connection Graph

Use this skill to answer "how does this relate to that?" across the system's internal knowledge.

Map is not current status, external research, or strategic recommendation. It builds a relationship graph from internal evidence and separates proven links from plausible inferences.

## Responsibility

Map owns internal relationship modeling.

It is responsible for:

- identifying relevant nodes;
- extracting evidence-backed edges between them;
- labeling the type and strength of each connection;
- showing paths, clusters, conflicts, duplicates, gaps, and divergences;
- routing follow-up work when the map reveals stale guidance, missing evidence, or strategic decisions.

The output is a usable map of relationships, not a narrative summary.

## Boundary

Do not manage lifecycle, publication, postflight, or generic artifact rites inside this skill.

Map uses internal sources first. Use the shared source lookup protocol only when an internal relationship depends on current external facts or outside examples.

## When To Use

Use `ed-map` for:

- concept-to-project relationships;
- project-to-project dependencies;
- open-gap, thread, or workflow overlap;
- "where does this idea appear?";
- "what connects A to B?";
- taxonomy, cluster, or divergence views;
- finding duplicated or contradictory internal knowledge.

Do not use it for:

- current project status or factual inventory;
- evidence discovery: use `ed-research`;
- action prioritization: use `ed-strategy`;
- implementation planning: use `ed-planner`;
- external landscape scans: use `ed-sources` or `ed-research`.

## Query Modes

- `concept`: map all internal connections around one concept.
- `path`: explain how concept A connects to concept B.
- `cluster`: group related concepts, projects, open gaps, or workflows.
- `divergence`: show where similar processes or ideas branch.
- `coverage`: show which parts of a project or argument are covered or missing.

If the operator does not specify a mode, infer the smallest useful one.

## Internal Sources

Prefer structured or indexed sources over broad reading:

- local corpus search and workflow search;
- project notes and CLAUDE files;
- reports, blog entries, open gaps, threads, and proposals;
- memory files such as debugging, reflection, workflows, and discoveries;
- repository docs when the relationship concerns code or architecture.

Use literal search to confirm names and exact mentions. Use semantic search to find adjacent ideas that do not share keywords.

## Edge Types

Use explicit relationship labels:

- `supports`: A provides evidence or argument for B.
- `depends_on`: A needs B to work.
- `applies_to`: A can be used in B.
- `derived_from`: A came from B.
- `duplicates`: A and B represent the same idea.
- `contradicts`: A conflicts with B.
- `blocks`: A prevents B from advancing.
- `supersedes`: A replaces older guidance or a weaker version.
- `analogizes`: A is useful as an analogy for B.
- `mentions`: A only references B; weak unless supported by context.

If the connection is inferred, mark it as inferred and explain why. Do not present semantic similarity as proof.

## Strength Scale

Score each important edge:

- `strong`: explicit statement, repeated evidence, or direct dependency.
- `medium`: co-occurrence with contextual support.
- `weak`: semantic neighborhood, single mention, or plausible but unverified inference.

Weak edges are useful for exploration, not decisions.

## Method

### 1. Frame The Map

Identify the map question, mode, scope, and expected output.

Examples:

- "Map concept X across projects."
- "Find the path from X to Y."
- "Show where process A diverges from process B."

### 2. Search Internal Evidence

Run targeted internal searches for the concept, aliases, and adjacent terms. For path queries, search each endpoint separately and cross-reference overlapping artifacts.

Use exact search for names and semantic search for ideas.

### 3. Extract Nodes And Edges

For each relevant artifact, extract:

| Field | Meaning |
|---|---|
| Node | project, idea, claim, workflow, file, report, issue, or data source |
| Edge | relationship between two nodes |
| Type | one of the edge types above |
| Strength | strong, medium, or weak |
| Evidence | file, artifact, quote fragment, or search result |
| Inference | why the link is inferred, if not explicit |

### 4. Build The Shape

Depending on the mode, produce:

- shortest or strongest path;
- clusters and central nodes;
- duplicated or contradictory nodes;
- missing links and unsupported assumptions;
- divergence points between related processes or ideas.

### 5. Route Follow-Up

Route findings instead of overreaching:

- stale or contradictory guidance -> `ed-reflection`;
- stale claims or thread cleanup -> `ed-strategy`;
- evidence gap -> `ed-research`;
- implementation or project sequencing -> `ed-planner`;
- current status question -> status/read-model CLI.

## Output

Use a compact structure:

```markdown
Map Mode: <concept | path | cluster | divergence | coverage>
Scope: <what was included/excluded>

Core Map:
| From | Edge | To | Strength | Evidence |
|---|---|---|---|---|

Shape:
- central nodes:
- strongest paths:
- divergences:
- contradictions or duplicates:
- gaps:

Inferences:
- <weak or inferred connection> -> <why it is plausible, what would confirm it>

Routes:
- <finding> -> <next skill/action>
```

If a visual graph would materially clarify the answer, include a simple Mermaid or SVG diagram. Do not generate an HTML report unless the operator asks for a standalone artifact.

## Invariants

- Internal evidence first.
- Edges need labels.
- Strength and inference must be visible.
- A map can reveal action, but it does not become strategy.
- Do not turn a relationship graph into a generic report.
