# `experiments/` — genotype workspace for the experimental subset of Atividade

**Ledger identity** of an Experiment remains `expNNN` in the eventlog
(`eventlog.declare_experiment`). This tree is the **disk manifestation** of the analysis
rite (one folder per experiment) so arms, runs, prompts, and outputs stay re-runnable.

## Layout (genotype)

```
experiments/
  README.md                 ← this file
  exp001-<slug>/
    projeto.md               ← hypothesis / not-testing / eval (before outcomes)
    timeline.md              ← living decision log (pivots stay visible)
    arms/                    ← optional arm materials
    runs/                    ← optional run artifacts
    outputs/                 ← optional generated outputs
```

Resolve paths via:

```bash
tools/edge-python -c "import sys; sys.path.insert(0,'tools'); import experiments_cfg as e; \
print(e.experiments_root()); print(e.ensure_experiment_workspace('exp001', title='…'))"
```

## Phenotype

`agent.yaml`:

```yaml
experiments:
  root: experiments          # default; relative to edge_home
  # root: writing            # temporary override while migrating pre-episteme trees
```

Env override for tests: `EDGE_EXPERIMENTS_DIR`.

## Roberto (acceptance phenotype)

Roberto was born **before** this genotype path: working copies lived under `writing/exp*` and
`drafts/*-exp`. That is phenotype debt, not a second ontology.

**Acceptance test of the genotype:** Roberto runs the **same** `experiments_cfg` API and
`/ed-experiment` contract. His `agent.yaml` may point `experiments.root` at a migration path
until contents move under `experiments/expNNN-slug/`. Feeling improvements happens on Roberto's
cortex + this tree — not on a parallel hardcoded layout.

## Relation to Atividade

An Experiment is an **Atividade** under a provenance rite + eval (`CONTEXT.md`). Mining may
open employment Atividades; **this directory + `/ed-experiment`** manage the experimental subset.
