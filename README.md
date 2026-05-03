# edge-of-chaos v2

`edge-of-chaos` is a private mentoring runtime.

The genotype is fixed:

- preserve the mentor/mentee relationship;
- load context and delta before advising;
- continue real work through threads;
- use Feynman principles: derive before researching, explain simply, expose gaps;
- keep skills consultive by default;
- run the minimum rite for every beat: broad search, adversarial review, review, Feynman review, rich report;
- do not mutate the mentee workspace unless an explicit apply mode is added.

The phenotype lives in `agent.yaml`: who the mentee is, where work happens, what sources exist, first steps, routines, domains, paths, and heartbeat cadence.

## Quick Start

```bash
cp agent.yaml.example agent.yaml
python3 tools/edge render
python3 tools/edge apply
python3 tools/edge doctor
python3 tools/edge heartbeat
python3 tools/edge discovery "What should I notice now?"
python3 tools/edge report "Summarize the current design direction"
```

Reports are written to `reports/` and mirrored into `blog/entries/`. The blog is static; there is no dashboard.

```bash
python3 tools/edge blog-build
python3 tools/edge blog-serve --port 8766
```

## Core Runtime

Every beat follows the same executable sequence:

1. open a cycle in `state/events.jsonl`;
2. observe configured context;
3. assemble a delta/preskill packet;
4. run a context readiness review with at most two attempts;
5. run broad search using configured source providers;
6. draft the mentor report;
7. run adversarial, general, and Feynman reviews;
8. finalize a rich report;
9. update thread continuity through runtime-applied state updates;
10. rebuild digests and close the cycle.

The LLM calls degrade to local deterministic reviewers when no keys are present. The report records that mode explicitly.

## State

The write side is append-only:

```text
state/events.jsonl
```

Readable state is compact and regenerable:

```text
state/threads/*.md
state/digests/*.md
reports/*.md
blog/entries/*.md
```

Threads are the continuity mechanism. A beat should continue a real thread or justify opening a new one.

## What Is Not In v2 Core

- primitives;
- rich dashboard;
- voice and branding;
- claims/signals/capabilities as core ontologies;
- self-healing genotype;
- mandatory public publishing;
- autonomous workspace mutation.
