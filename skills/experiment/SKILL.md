---
name: experiment
description: Technical protocol for native Edge/Episteme experiments. Use when a mentor-discovered
  uncertainty becomes testable, or when the user asks to inspect, design, run, navigate, or close an
  Experiment using Roberto's native schema: hypothesis, arms, runs, eval, observations, bearings,
  curated-first reading, and mandatory report finalization.
---
`experiment` is a technical protocol, not a second mentor. Live guidance belongs to `mentor`; this
skill supplies the rigorous experiment vocabulary and the Edge write/read contract. If the user
arrives by `/experiment` with an open-ended problem, first read `skills/mentor/SKILL.md` and conduct
as **mentor in experiment mode**: keep the natural one-question cadence, and use this skill only to
translate the uncertainty into the schema.

**Episteme placement (operator 2026-07-13):** **Mineração / Atividade expanded** how employment
enters the ledger and cortex. That does **not** dissolve experiment. An **Experiment is a subset of
Atividade** — same employment case, plus a **provenance rite** (chain of prior experiments/claims)
and a mandatory **eval** product (biased or not; still an eval) that **generates knowledge**. This
skill (`/{prefix}-experiment`) is what **manages that subset**. Ordinary Atividades (ship, fix, wayfind)
stay employment-only unless promoted into this rite. See CONTEXT.md **Experiment** and
`memory/experiment-is-atividade-with-rite-and-eval.md`.

**Entry freeze (operator 2026-07-13 — leave expansion for later):** Open or mint an Experiment
**only when the user determines it** through this skill **directly** (slash/command, “run an
experiment”, navigate/close a named exp) **or indirectly** (user accepts a mentor experiment-mode
proposal and continues under this skill). Do **not** auto-declare smokes, CI canaries, draft
`*-exp` folders, or “anything with an eval” as `expNNN`. Those stay ordinary craft/employment until
the user routes them here. Conceptual note (smoke-with-eval *can* be experiment) is deferred policy,
not current runtime duty.

## Native Contract
The contract already exists in Roberto. Treat these as normative inputs, loaded only when the task
needs implementation-level detail:
- `docs/agencia/implementacao/06-experiment-skill.md` — the user-facing purpose of `/experiment`:
  glossary, arms/runs/eval, onboarding as first experiment, and leveling through use.
- `docs/agencia/implementacao/03-A-episteme-nativo.md` — native Edge/Episteme merge: Experiment is
  a first-class scientific object; Report is the human-readable bridge.
- `docs/agencia/ontologia-cortex-v2.md` and `cortex/schema/ontologia.yaml` — nodes, edges, enums,
  controlled paths, and the native event names.

Current runtime, as of this skill:
- Reading native experiments works through `cortex.experiment_at(...)` and
  `cortex.experiments_at(...)`, folding `experiment.declared` plus `experiment.curated`.
- Declaring a native experiment works through `eventlog.declare_experiment(...)`. It assigns a stable
  canonical experiment ID (`exp001`, `exp002`, …; historical ids such as `exp40` still read) before
  the report exists. Decision-bearing **meta-experiments** also use this same global sequence with
  `kind="meta"`.
- Closing/finalizing an experiment works through `/report`: the report publishes `reports_on` plus
  `experiment_curation`, and the publisher writes `experiment.curated` in the same atomic batch.
- The ontology name `experiment_declared` corresponds to runtime `experiment.declared`. The full pen
  for `run_started` and `experiment_concluded` is still contract in the ontology, not a callable
  writer yet. Do not invent or hand-write those events until the pen exists.

## Canonical ID + disk workspace
Every new Experiment needs a stable canonical ID before it can be closed. Use the pen, never a folder
name or a prose title as identity:

```bash
tools/edge-python -c "import sys; sys.path.insert(0,'tools'); import eventlog; \
print(eventlog.declare_experiment('<title>', hypothesis='<testable uncertainty>')['payload']['experiment_id'])"
```

`declare_experiment` also seeds the **genotype workspace** under `experiments/<expNNN>-<slug>/`
(`projeto.md`, `timeline.md`, `arms/`, `runs/`, `outputs/`) unless `workspace=False`. Resolve paths
with `experiments_cfg.experiments_root()` / `experiment_dir(id)`.

Phenotype: `agent.yaml` → `experiments.root` (default `experiments` under `edge_home`). Pre-episteme
installs (e.g. Roberto `writing/exp*`) override `root` until migrated — same genotype API, different
folder; **Roberto is the acceptance phenotype** of this layout.

Use that id in all reports and artifacts: `reports_on=['expNNN']`. Non-canonical ids are rejected by
the lineage normalizer instead of being silently turned into experiments.

Numbering discipline:
- `kind="domain"` is the default for experiments about the mentee's/business/domain object.
- `kind="meta"` is for experiments about Edge itself, report quality, gates, tools, skills, or eval
  process. It still receives a global `expNNN` if it answers a decision-bearing uncertainty.
- Arms, runs, report iterations, feedback passes, and output files do **not** receive global
  experiment numbers. Record them as `arms`, future run events, artifact slugs, or `relates` entries
  under the parent Experiment.
- If a meta-experiment studies another experiment, give the meta-experiment its own `expNNN` and link
  the object with `relates=[{"type":"analyzes","experiment_id":"exp070",...}]`.
- The concrete `old-edge-new-tools-exp/remote-feedback-v1` round is a `kind="meta"` Experiment over
  report quality; it should receive its own global id instead of reusing the domain experiment `exp070`.

## Read Order
Use curated-first navigation. The user should not have to dig through native experiments manually.

1. Read the current canonical interpretation:
   `tools/edge-python -c "import sys; sys.path.insert(0,'tools'); import cortex; print(cortex.experiment_at('<experiment-id>'))"`
2. If no id was given, inventory the experiments:
   `tools/edge-python -c "import sys; sys.path.insert(0,'tools'); import cortex; print(cortex.experiments_at())"`
3. Show the short curated conclusion first: `canonical.prose`, then typed fields
   `claim/scope/status/caveat/supports/excludes/next`.
4. Only pull raw inventory after the curated interpretation is interesting or insufficient. Raw
   inventory is audit material, not the first human interface.

Never ask an LLM to summarize the experiment into a new canonical reading. The canonical reading is
an explicit curation event. Conclusions stay short because the schema carries the rest.

## Translate Reality To Schema
Start from the mentee's real decision, not from a form. Preserve the wording of the lived problem,
then map it:
- `Experiment` — the decision-bearing uncertainty, hypothesis, scope, owner/context, and decision
  rule. It is the object the graph navigates.
- `Arm` — a concrete alternative being compared, including baseline/control. Use real names, not
  anonymous A/B labels when the options already have names.
- `Run` — an explicit execution of one arm with corpus/config/context/cost/actor enough to replay
  or contest it.
- `Eval` — the metric or judgment rule that decides what the run means. Prefer registered templates
  such as `delta_ci@1` when available. Qualitative evals must define criteria before reading results.
- `Observation` — observed result with metric distribution or explicit qualitative evidence, plus
  cited artifacts/sources.
- `Bearing` — the valenced relation to a live hypothesis: supports/refutes/qualifies/inconclusive.
  Computed bearings belong to the experiment pen; authored report bearings use `bears_on` and stay
  asserted/lead.
- `Report` — the human-readable HTML report that makes the experiment navigable for a person and
  links it to clusters, entities, and future work.

Cost is real cost: money, people exposed, time, risk, or opportunity cost. Tokens are only cost when
tokens are the thing being optimized.

## When To Propose An Experiment
Propose an experiment only if all three are true:
- There is a concrete uncertainty whose answer changes a decision.
- There are at least two plausible arms, or a baseline/control worth comparing against.
- There is an observable eval that can be recorded without pretending certainty.

If the uncertainty is conceptual, leave or update a falsifiable inscription instead of forcing an
experiment. If the user needs research, a map, a plan, or a report without comparative evidence, use
that skill. The experiment emerges from mentor interaction when the case reaches it.

## Cold Start
The hardest case is no existing experiment. Do not fake history, do not inventory empty folders, and
do not turn the first contact into a form. Start from the pain the user brings.

Cold-start sequence:
1. State the observed pain in ordinary language.
2. Ask one residual question that decides whether the pain is testable.
3. If it is testable, show a compact experiment card. If not, leave an inscription/hypothesis.
4. Make the first run small enough to execute now; onboarding into Episteme happens by running the
   first experiment, not by a separate setup lecture.

The compact card is the bridge between mentor and schema:

```yaml
Experiment: <decision-bearing uncertainty in the user's terms>
Arm: <candidate flow being tested, including baseline/control>
Run: <one concrete execution on one case/corpus/user>
Eval: <metric or judgment rule fixed before reading the result>
Observation: <fact format to capture, with citations/artifacts>
Report: <HTML report that will close the experiment>
```

Use this card only after the uncertainty is live. It is not a cold intake form.

## Closing Rule
An experiment is not done until a report is published.

The close path is `/report`, not a raw event append. If the experiment is done during an ongoing
conversation, hand the consolidation to the **`experiment-reporter` background subagent** with disk
pointers and the canonical `experiment_id`, so the main mentor thread can keep talking while the
report closes.

The report/subagent path:
- The report must be a human-readable HTML report produced by `skills/report/SKILL.md`.
- The report payload carries `reports_on=['<experiment-id>']`.
- The report payload carries `experiment_curation={...}` with:
  `prose` plus typed `claim/scope/status/caveat/supports/excludes/next`, and optional additional
  `canonical_artifacts`.
- The publish step injects `artefato:<slug>` as a canonical report artifact and writes
  `experiment.curated` atomically with the published Artefato.

Do not call `publisher.publish` directly. Do not append `experiment.curated` as a way to skip the
report. If a direct maintenance path is ever used, it still must point to a report Artefato; otherwise
the experiment is not closed.

## Contradictions
Preserve contradictions as chain, not overwrite. Later curations can become the current canonical
interpretation, but earlier `curation_chain` items remain. If two readings conflict and no rule
decides them, mark the relation as contested/qualifying in `relates`; do not erase the losing read.
