# edge — read this before you install

## If this is a fresh clone (you are not an install yet)

This repository is **genotype without identity**: there is no `agent.yaml` here — each host
writes its own as the **output** of onboarding (the file is untracked / gitignored on purpose).

- **Do not** invent an `agent.yaml` or run `edge-apply` — that path is for a phenotype that
  **already** belongs to a live host.
- **Do** follow the guided rite in `skills/onboard/SKILL.md` — interview the operator
  (name, home folder, CLIs, adversarials, secrets/embeddings, backfill days with a **cost
  check**), run the full install while explaining each step, and hand off into the first mentor.
  `agent.yaml` is the **output** of onboarding, never the seed.

How to tell: if `state/bootstrap.json` does not exist and nobody told you this directory is a
live install, treat it as a fresh clone and ask first.

**House language:** documentation and install defaults are **en-US**. Operator session language
can still follow phenotype `agent.yaml` `language:` after install.

## If this is a live install

Normal operation — `CONTEXT.md` is the map, `CONTRACT.md` the contract, `docs/adr/` the
decisions.
