# edge-of-chaos v2

`edge-of-chaos` is a private mentoring runtime.

The genotype is fixed:

- preserve the mentor/mentee relationship;
- load context and delta before advising;
- continue real work through threads;
- use Feynman principles: derive before researching, explain simply, expose gaps;
- keep skills consultive by default;
- run the same straight-line rite for every beat: state load, two continuity/context/search reviews, broad search rounds, adversarial rounds, Feynman review, final report, thread processing;
- do not mutate the mentee workspace unless an explicit apply mode is added.

The phenotype lives in `agent.yaml`: who the mentee is, where work happens, what sources exist, first steps, routines, domains, paths, and heartbeat cadence.
To keep a checkout clean for fresh installs, the runtime also accepts `../agent.yaml`
or `../keys/agent.yaml` relative to the repo root, plus an explicit
`EDGE_AGENT_CONFIG=/abs/path/to/agent.yaml` override.
Non-secret model defaults live in `.env.defaults`; copy or override them in `.env`/`keys/*.env` when an instance needs a different model. Secrets stay out of the repo.

## Quick Start

```bash
cp agent.yaml.example agent.yaml
python3 tools/edge render
python3 tools/edge apply
python3 tools/edge doctor
python3 tools/edge heartbeat
python3 tools/edge discovery "What should I notice now?"
python3 tools/edge research "Interrogate the latest experiment result"
python3 tools/edge report "Summarize the current design direction"
python3 tools/edge chat-send "Check the async chat before the next beat."
python3 tools/edge chat-list --unprocessed
```

`heartbeat` is only a router. It selects a real beat kind and then runs the same common rite as `discovery`, `research`, or `report`.

Reports are written to `reports/` and mirrored into `blog/entries/`. The blog stays lightweight and static, but it also serves a minimal async chat surface at `/chat`; there is no dashboard.

```bash
python3 tools/edge blog-build
python3 tools/edge blog-serve --port 8766
```

## Core Runtime

Every beat follows the same executable sequence:

1. open a cycle in `state/events.jsonl`;
2. refresh the LLM-maintained Claude chat digest from new session deltas;
3. load state and delta sources into a context pack, including operator pressure and async chat when present;
4. deliver the context pack;
5. run continuity/context/search reviewer round 1;
6. run fresh broad search from configured providers and reviewer hints;
7. deliver evidence pack v1;
8. run continuity/context/search reviewer round 2;
9. run fresh broad search again from accumulated hints;
10. deliver evidence pack v2;
11. draft report v1;
12. run adversarial+search review;
13. run fresh broad search again from adversarial hints;
14. revise and deliver draft v2;
15. run adversarial review round 2;
16. revise and deliver draft v3;
17. run Feynman review;
18. deliver the final report;
19. classify report utility for future curation;
20. process/update threads, rebuild digests, rebuild the static blog, and close the cycle.

The orchestration is enforced by a small ledger gate, not by primitives. It only checks that the straight-line rite happened in order. Reviewers do not control `pass/fail`; their feedback feeds the next delivery.

LLM calls use the configured primary provider first and fall back to the local `claude` CLI. If neither is available, the runtime degrades to explicit local reviewers and the report records that mode.

## State

The write side is append-only:

```text
state/events.jsonl
```

Readable state is compact and regenerable:

```text
state/threads/*.md
state/digests/*.md
state/chat-digest.md
state/operator-pressure.md
state/async-chat.jsonl
state/report-utility.jsonl
reports/*.md
blog/entries/*.md
```

Threads are the continuity mechanism. A beat should continue a real thread or justify opening a new one.
`state/chat-digest.md` is the genotypic chat projection: an LLM reads the previous digest plus new Claude session deltas and writes a compact summary for the next beat. Raw chat logs are sources; the beat consumes the digest.
`state/operator-pressure.md` is the explicit operator-priority lane for the next beat. `state/async-chat.jsonl` is the durable async inbox; successful cycles acknowledge the messages they consumed.

## What Is Not In v2 Core

- primitives;
- rich dashboard;
- voice and branding;
- claims/signals/capabilities as core ontologies;
- self-healing genotype;
- mandatory public publishing;
- autonomous workspace mutation.
