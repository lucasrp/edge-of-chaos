"""experiments_cfg — genotype workspace for Experiments (disk manifestation of the rite).

Ledger identity of an Experiment is still `expNNN` in the eventlog (`declare_experiment`).
The **working directory** is the analyst's self-contained unit (projeto + timeline + arms/runs) —
the same discipline as the analysis canon (one folder per analysis), under a path the genotype
owns.

Genotype default: ``<edge_home>/experiments/``.
Phenotype override (agent.yaml):

  experiments:
    root: experiments          # relative to edge_home, or absolute / ~/…

Roberto pre-episteme used ad-hoc ``writing/exp*`` and ``drafts/*-exp``; those remain valid
*phenotype* overrides until migrated. Acceptance: Roberto runs the **same genotype** paths
API; his agent.yaml only chooses where the tree lives until he adopts ``experiments/``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import _identity

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DEFAULT_REL = "experiments"


def _cfg(agent_yaml=None):
    return _identity._cfg(agent_yaml if agent_yaml is not None else _identity.AGENT_YAML)


def experiments_root(agent_yaml=None, edge_home=None) -> Path:
    """Resolved experiments workspace root for THIS install.

    Precedence:
      1. EDGE_EXPERIMENTS_DIR env (hermetic tests / host override)
      2. agent.yaml ``experiments.root`` (phenotype)
      3. genotype default: ``<edge_home>/experiments``
    """
    raw = os.environ.get("EDGE_EXPERIMENTS_DIR")
    if raw:
        return Path(os.path.expanduser(raw)).resolve()

    cfg = _cfg(agent_yaml)
    block = cfg.get("experiments") if isinstance(cfg.get("experiments"), dict) else {}
    root_raw = block.get("root") if isinstance(block, dict) else None
    if not (isinstance(root_raw, str) and root_raw.strip()):
        root_raw = _DEFAULT_REL

    p = Path(os.path.expanduser(root_raw.strip()))
    if p.is_absolute():
        return p.resolve()

    if edge_home is None:
        try:
            home = _identity.edge_home(cfg=cfg, agent_yaml=agent_yaml or _identity.AGENT_YAML)
        except RuntimeError:
            home = str(_identity.REPO)
        edge_home = Path(os.path.expanduser(home))
    else:
        edge_home = Path(os.path.expanduser(str(edge_home)))
    return (edge_home / p).resolve()


def slugify_title(title: str, *, max_len: int = 48) -> str:
    """Filesystem-safe slug from a human title."""
    if not isinstance(title, str) or not title.strip():
        return "untitled"
    s = title.strip().lower()
    s = _SLUG_RE.sub("-", s).strip("-")
    if not s:
        return "untitled"
    return s[:max_len].rstrip("-")


def ensure_experiment_workspace(experiment_id: str, *, title=None, hypothesis=None,
                                agent_yaml=None) -> Path:
    """Create the experiment directory + stubs if missing; return the path."""
    path = experiment_dir(
        experiment_id, title=title, agent_yaml=agent_yaml, create=True,
        hypothesis=hypothesis,
    )
    return path


def experiment_dir(experiment_id: str, *, title=None, agent_yaml=None, create=False,
                   hypothesis=None) -> Path:
    """Path for one experiment's working directory: ``experiments/<expNNN>-<slug>/``.

    If a directory already exists with prefix ``<expNNN>-`` or exact ``<expNNN>``, reuse it
    (stable across title renames). When ``create`` and none exists, mint
    ``<expNNN>-<slug>/`` with projeto.md + timeline.md stubs.
    """
    import eventlog as _eventlog  # local: avoid cycle at import for tests that only resolve root

    eid = _eventlog._normalized_experiment_id(experiment_id)
    root = experiments_root(agent_yaml)
    if root.is_dir():
        exact = root / eid
        if exact.is_dir():
            return exact
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child.name == eid or child.name.startswith(f"{eid}-")):
                return child

    slug = slugify_title(title or eid)
    path = root / f"{eid}-{slug}"
    if create:
        _seed_workspace(
            path, experiment_id=eid, title=title or eid, hypothesis=hypothesis)
    return path


def _seed_workspace(path: Path, *, experiment_id: str, title: str, hypothesis=None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "arms").mkdir(exist_ok=True)
    (path / "runs").mkdir(exist_ok=True)
    (path / "outputs").mkdir(exist_ok=True)
    projeto = path / "projeto.md"
    hyp = (
        hypothesis.strip()
        if isinstance(hypothesis, str) and hypothesis.strip()
        else "(State before reading outcomes.)"
    )
    if not projeto.is_file():
        projeto.write_text(
            f"# {title}\n\n"
            f"- **experiment_id:** `{experiment_id}`\n"
            f"- **kind:** domain | meta\n\n"
            f"## Question\n\n"
            f"(What decision does this experiment change?)\n\n"
            f"## Hypothesis\n\n"
            f"{hyp}\n\n"
            f"## Not testing\n\n"
            f"(Explicit out of scope.)\n\n"
            f"## Success / eval\n\n"
            f"(Régua pré-registrada — may be imperfect; still an eval.)\n",
            encoding="utf-8",
        )
    timeline = path / "timeline.md"
    if not timeline.is_file():
        timeline.write_text(
            f"# Timeline — {experiment_id}\n\n"
            f"Living memory: what was tested, what came back, what we decided, what next.\n"
            f"Update as the experiment unfolds — not only at the end.\n\n"
            f"## Log\n\n"
            f"- _seeded workspace_\n",
            encoding="utf-8",
        )
