"""_identity — derive install identity from agent.yaml, never from a baked-in literal (#21).

agent.yaml is the SOLE identity source. The genotype carries no install literal: the graph
group, the edge_home paths, and the Neo4j password are all derived here. Two postures, matching
briefing.py (the operator's existing approach):

  - RUNTIME degrades on a missing value — `os.environ.get(...)` with NO literal default; a tool
    that can't resolve its group/password just darkens the graph leg (like briefing.graph_clusters
    returning None when EDGE_GROUP is unset). The beat never crashes on a missing identity.
  - INSTALL fails loud — `require_group` / `require_neo4j_password` raise, naming the gap, so
    edge-apply provisions a real identity rather than silently writing into a cross-tenant group.

Group precedence: EDGE_GROUP env (host override) → agent.yaml name/codename. No baked-in group
default (the cross-tenant bug, #21). Password: EDGE_NEO4J_PASSWORD env → the install's generated
secret; no literal default (CONTRACT C4)."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def identity_path(name):
    """Arquivo de identidade/doutrina (agent.yaml, memory/): num install com genótipo e home
    separados (EDGE_HOME, ex. edgesandbox) vive no HOME — o repo é genótipo puro, sem
    identidade. Sem EDGE_HOME (ou sem o arquivo no home), REPO é o legado home==repo."""
    env = os.environ.get("EDGE_HOME")
    if env:
        p = Path(os.path.expanduser(env)) / name
        if p.exists():
            return p
    return REPO / name


AGENT_YAML = identity_path("agent.yaml")


def _cfg(agent_yaml=AGENT_YAML):
    import yaml
    p = Path(agent_yaml)
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def group(agent_yaml=AGENT_YAML):
    """The graph group for THIS install. EDGE_GROUP (host override) → agent.yaml `graph_group` →
    name/codename. `graph_group` lets an install own a corpus in a group distinct from its mentor
    name without orphaning it — explicit per-install config, never a baked-in default (#21). Returns
    None when nothing resolves — the runtime degrade posture (no cross-tenant default)."""
    g = os.environ.get("EDGE_GROUP")
    if g:
        return g
    cfg = _cfg(agent_yaml)
    return cfg.get("graph_group") or cfg.get("name") or cfg.get("codename") or None


def mentee(agent_yaml=AGENT_YAML):
    """The operator/mentee THIS install serves — the `para` default's target (curadoria autoral:
    every artefato is FOR someone; absent an explicit target, the target is the mentee).
    EDGE_MENTEE env (host override) → agent.yaml `mentee` → `repo_owner` (the mentee's git
    identity — the operator name agent.yaml already carries). Returns None when nothing
    resolves — the runtime degrade posture (no default applied), never a baked-in name (#21).
    Normalized like the authored `para` (codex adversarial #2): a blank/non-string value is
    SKIPPED, never persisted — the mechanical default can't put junk in the event/graph."""
    cfg = _cfg(agent_yaml)
    for v in (os.environ.get("EDGE_MENTEE"), cfg.get("mentee"), cfg.get("repo_owner")):
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def require_group(agent_yaml=AGENT_YAML):
    """Install posture: the group MUST resolve, or fail loud (no silent cross-tenant write)."""
    g = group(agent_yaml)
    if not g:
        raise RuntimeError(
            "no graph group: set EDGE_GROUP or agent.yaml `name`/`codename` "
            "(the genotype carries no identity default — would mix tenants)")
    return g


def project_dir(agent_yaml=AGENT_YAML):
    """The mentee's Claude transcript store for THIS install (ADR-0015). EDGE_PROJECT_DIR env →
    agent.yaml `project_dir` → derived from the running $HOME per the Claude store convention
    (/home/x → ~/.claude/projects/-home-x). The agent.yaml field lets a WSL install point durably at
    the Windows store (/mnt/c/Users/<user>/.claude/projects) — the phenotype carries it, no env
    plumbing into the runtime. FAIL-LOUD: a store directory that does not exist raises — "nothing
    new" is reserved for a real store with nothing new, never for scanning a foreign or absent path
    (the roberto amnesia: a baked-in dev host path scanned nothing, silently)."""
    raw = os.environ.get("EDGE_PROJECT_DIR") or _cfg(agent_yaml).get("project_dir")
    if raw:
        p = Path(os.path.expanduser(raw))
    else:
        home = Path.home()
        p = home / ".claude" / "projects" / str(home).replace("/", "-")
    if not p.is_dir():
        raise RuntimeError(
            f"transcript store not found: {p} — set EDGE_PROJECT_DIR to this install's Claude "
            "projects dir (ADR-0015: the store derives from $HOME, never a baked-in host path; "
            "a missing store fails loud, never 'nothing new')")
    return p


def edge_home(cfg=None, agent_yaml=AGENT_YAML):
    """The install root for THIS host, from agent.yaml `edge_home` (no baked-in path literal)."""
    cfg = _cfg(agent_yaml) if cfg is None else cfg
    home = cfg.get("edge_home")
    if not home:
        raise RuntimeError("agent.yaml declares no `edge_home` (the install root)")
    return Path(os.path.expanduser(str(home)))


def state_root(agent_yaml=AGENT_YAML):
    """Raiz do ESTADO do install: EDGE_HOME env → agent.yaml `edge_home` → REPO (legado).

    Raiz do #154: state/cursors/log eram RELATIVOS AO REPO (era repo==install), então
    qualquer run com cwd num checkout de genótipo escrevia estado DENTRO do checkout —
    inclusive no ~/edge de outro install. Com EDGE_HOME declarado, o estado pousa na
    casa declarada, independente do cwd. Sem declaração nenhuma, comportamento legado."""
    env = os.environ.get("EDGE_HOME")
    if env:
        return Path(os.path.expanduser(env))
    home = _cfg(agent_yaml).get("edge_home")
    if home:
        return Path(os.path.expanduser(str(home)))
    return REPO


def _env_dir(agent_yaml=AGENT_YAML):
    """Where this install's secrets live: EDGE_SECRETS_DIR (override explícito, espelha
    onboarding.secrets_dir) → agent.yaml `env_dir` → <edge_home>/secrets → EDGE_HOME/secrets
    (pré-fenótipo: no first-run agent.yaml ainda não existe e o fallback legado ~/edge
    apontava pro lugar errado — o gap do EDGE_NEO4J_PASSWORD no onboarding, 2× edgesandbox)."""
    override = os.environ.get("EDGE_SECRETS_DIR")
    if override:
        return Path(os.path.expanduser(override))
    cfg = _cfg(agent_yaml)
    home = Path(os.path.expanduser(str(
        cfg.get("edge_home") or os.environ.get("EDGE_HOME") or "~/edge")))
    raw = cfg.get("env_dir")
    if raw:
        p = Path(os.path.expanduser(str(raw)))
        return p if p.is_absolute() else home / p    # relativo ancora no home, nunca no cwd
    return home / "secrets"


def neo4j_password(agent_yaml=AGENT_YAML):
    """The Neo4j password for THIS host. EDGE_NEO4J_PASSWORD env → the install's generated secret in
    env_dir/neo4j.env (#22), sourced lazily via _secrets.load_env. No literal default (CONTRACT C4):
    a missing password degrades the graph at runtime and fails loud at install."""
    pw = os.environ.get("EDGE_NEO4J_PASSWORD")
    if pw:
        return pw
    import _secrets
    _secrets.load_env(_env_dir(agent_yaml))     # source the install's own secrets into the env
    return os.environ.get("EDGE_NEO4J_PASSWORD") or None


def require_neo4j_password():
    """Install posture: the Neo4j password MUST be present, or fail loud (no literal default)."""
    pw = neo4j_password()
    if not pw:
        raise RuntimeError(
            "no EDGE_NEO4J_PASSWORD: the per-host Neo4j secret is unset "
            "(the genotype ships no default password — CONTRACT C4)")
    return pw


def neo4j_conn():
    """(uri, user, password) for the local graph — password from the env secret (no literal)."""
    return (os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("EDGE_NEO4J_USER", "neo4j"),
            neo4j_password())
