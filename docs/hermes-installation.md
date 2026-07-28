# Install and onboard Edge of Chaos in Hermes Agent

This runbook installs one Edge of Chaos (EoC) phenotype for a Hermes profile, completes onboarding, and verifies the first wake. The repository is the **genotype**; the directory under `~/.edge-of-chaos/` is the live **phenotype**. Do not create `agent.yaml` in a fresh clone: it is the output of onboarding.

## 1. Prerequisites

- a working Hermes Agent installation;
- Python 3 and Git;
- Docker when Neo4j is provisioned locally;
- a clone of this repository;
- the target Hermes profile and its intended EoC group.

Example paths used below:

```bash
export EDGE_REPO="$HOME/src/edge-of-chaos"
export EDGE_HOME="$HOME/.edge-of-chaos/steve"
export EDGE_GROUP="profile:default"
```

`EDGE_HOME` isolates identity, state, memory, secrets, runtime, and projections for one phenotype. `EDGE_GROUP` selects the graph/hivemind namespace. Use both variables on every EoC command; never rely on an unrelated working directory.

## 2. Choose the Hermes profile policy

Hermes resolves EoC per profile:

- missing effective `edge_group`: EoC is disabled for that profile;
- blank `edge_group`: use `profile:<profile_name>`;
- named `edge_group`: profiles with that value share one EoC hivemind.

Set the global default in Hermes `config.yaml`, then override it in a profile config only when that profile needs different behavior. See [ADR-0025](adr/0025-hermes-profiles-share-through-edge-group.md).

For an isolated default profile:

```yaml
edge_group: ""
```

This resolves to `profile:default`; it does not create a second storage layer.

## 3. Create the phenotype runtime

Keep the clone and live state separate:

```bash
mkdir -p "$EDGE_HOME"
ln -sfn "$EDGE_REPO/tools" "$EDGE_HOME/tools"
python3 -m venv "$EDGE_HOME/.venv"
"$EDGE_HOME/.venv/bin/python" -m pip install -r "$EDGE_REPO/requirements.txt"
```

If the repository does not have a requirements file for the current revision, follow `skills/setup/SKILL.md` instead of inventing another installer. All later Python commands should go through the repository wrapper:

```bash
cd "$EDGE_REPO"
tools/edge-python -c 'from tools import _identity; print(_identity.state_root())'
```

The printed state root must equal `EDGE_HOME`. During first bootstrap, identity resolution honors `EDGE_HOME` even before `agent.yaml` exists.

## 4. Run canonical onboarding

Read and execute the rite in [`skills/onboard/SKILL.md`](../skills/onboard/SKILL.md). Onboarding is a real interview and setup sequence, not a copied template. It must establish:

1. mentor identity, personality, method, and language;
2. who the mentee is and how confirmed signals enter `memory/leveling/`;
3. available local surfaces and public sources;
4. embeddings and graph requirements;
5. backfill scope, with a cost check before acquisition;
6. heartbeat policy;
7. the final `agent.yaml` written under `EDGE_HOME`.

Run setup commands with the explicit environment:

```bash
cd "$EDGE_REPO"
EDGE_HOME="$EDGE_HOME" EDGE_GROUP="$EDGE_GROUP" \
  tools/edge-python tools/edge-apply --yaml "$EDGE_HOME/agent.yaml" --home "$EDGE_HOME"
```

Do not copy credentials into `agent.yaml`, documentation, eventlog, or Git. Store local secrets under `$EDGE_HOME/secrets/` with restrictive permissions.

## 5. Provision and verify Neo4j

Use the canonical provisioner from `tools/_provision.py`; do not create a parallel graph deployment. A local Docker deployment writes its connection environment under `$EDGE_HOME/secrets/neo4j.env`.

After setup, verify the service and configuration without printing secret values:

```bash
docker ps --filter name=edge-neo4j --format '{{.Names}} {{.Status}}'
test -s "$EDGE_HOME/secrets/neo4j.env"
```

The container must be running and the environment file must exist. Never commit that file.

## 6. Install the Hermes integration

The Hermes startup plugin reconciles profile-local EoC skill wrappers. Apply the canonical provisioner from this repository rather than copying wrappers by hand:

```bash
cd "$EDGE_REPO"
EDGE_HOME="$EDGE_HOME" EDGE_GROUP="$EDGE_GROUP" \
  tools/edge-python tools/_hermes_provision.py
```

Restart the Hermes gateway/app after plugin installation so startup reconciliation runs. The plugin is the owner of generated wrappers; upgrading EoC should reconcile them instead of layering another copy.

Hermes `web_search` and `web_extract` are shared logical acquisition capabilities. Exa, Firecrawl, Tavily, Parallel, or SearXNG are interchangeable Hermes backends and should appear only as provenance. Do not declare each backend as another EoC source, duplicate credentials, or persist full tool payloads.

## 7. Run predispatch and the first wake

Predispatch validates the phenotype before a wake. Follow the exact command in `skills/wake/SKILL.md` for the installed revision, always exporting the phenotype identity:

```bash
export EDGE_HOME="$HOME/.edge-of-chaos/steve"
export EDGE_GROUP="profile:default"
cd "$EDGE_REPO"
# Run the predispatch command documented by skills/wake/SKILL.md.
```

Only continue when predispatch exits `0`.

A complete wake keeps four cognitions separate:

- **assemble** — consolidated state and internal orientation;
- **delta** — Mundo, Atividade, and Voz since the previous wake;
- **recall** — salient graph memory and mentee persona, without bookkeeping;
- **quente** — live threads, without taking action.

Run each leg according to its own skill contract (`skills/assemble`, `skills/delta`, `skills/recall`, and `skills/quente`). Do not concatenate their raw outputs into a fifth mega-brief. The live intersection comes from compact references and provenance across native projections.

The eventlog is the source of truth. It records useful events and references, not full web responses or complete tool transcripts. Graph, wiki, and Direction are derived projections and can be rebuilt.

## 8. Verification checklist

A successful installation satisfies all of these:

```text
[ ] EDGE_HOME resolves to the phenotype directory
[ ] EDGE_GROUP resolves to the intended profile or shared hivemind
[ ] agent.yaml exists only in the phenotype
[ ] Hermes startup plugin reconciles the EoC wrappers
[ ] Neo4j is online and its secret environment file is local only
[ ] public/local source canaries pass
[ ] predispatch exits 0
[ ] recall is not DARK and includes the confirmed mentee persona
[ ] quente exits 0
[ ] assemble, delta, recall, and quente remain separate
[ ] eventlog contains references, not duplicated full payloads
```

Focused repository regression gate:

```bash
cd "$EDGE_REPO"
python3 -m unittest \
  tests.test_hermes_pipeline \
  tests.test_hermes_provision \
  tests.test_identity_env_dir \
  tests.test_mentee_persona_brief \
  tests.test_recall_brief \
  tests.test_quente \
  tests.test_hermes_sessions
git diff --check
```

## 9. Upgrade

```bash
cd "$EDGE_REPO"
git pull --ff-only
export EDGE_HOME="$HOME/.edge-of-chaos/steve"
export EDGE_GROUP="profile:default"
tools/edge-python tools/_hermes_provision.py
```

Then rerun predispatch and the focused regression gate. Preserve `agent.yaml`, `memory/`, `state/`, `secrets/`, and the eventlog under `EDGE_HOME`; do not replace the phenotype with the repository clone.

## 10. Troubleshooting

### Identity resolves to the clone

Confirm `EDGE_HOME` is exported on the failing command. Bootstrap must resolve `$EDGE_HOME/agent.yaml` even before that file exists.

### Recall is DARK

Check Neo4j first, then `$EDGE_HOME/secrets/neo4j.env`. Do not regenerate recall repeatedly while the graph is unavailable.

### Mentee persona is empty

The canonical path is `$EDGE_HOME/memory/leveling/perfil.md`. Persona belongs to the phenotype, not the genotype clone. Add only confirmed signals; do not fabricate missing biography.

### Quente includes unrelated Hermes sessions

Check the effective `edge_group` for every Hermes profile. Tests that exercise only a local fixture must pass `hermes_dir=False` when the real Hermes surface is intentionally out of scope.

### Duplicate acquisition or inflated context

Keep `web_search`/`web_extract` as the interfaces and backend names as provenance. Store compact references in the eventlog; do not mirror full responses into briefs, graph, wiki, and Direction.

### Generated wrappers drift after an upgrade

Rerun `tools/_hermes_provision.py` and restart Hermes. Do not edit generated profile wrappers manually.
